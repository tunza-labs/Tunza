#!/usr/bin/env python3
"""LoRA fine-tune on Apple Silicon with MLX (much lighter on memory than PyTorch MPS, so it fits an 8 GB M1), then score on the dev slice.

It runs `mlx_lm lora` as a subprocess, copies its progress lines into the same run folder the live page reads (meta.json, telemetry.jsonl),
then scores the adapter with the code-owned reward and writes results.json. Engineering run only. No Jev, no clinical data.

  python tools/tunza-train/mlx_run.py --tag v2-mlx-sft-0.8b-s2 --iters 800 --batch 4
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as ev  # noqa: E402

REPORT = re.compile(r"Iter (\d+): Train loss ([0-9.]+), Learning Rate ([0-9.e+-]+), It/sec ([0-9.]+), Tokens/sec ([0-9.]+), Trained Tokens (\d+), Peak mem ([0-9.]+) GB")


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TABLE = re.compile(r"^\s*(\d+)\s+([0-9.]+)\s*[▲▼=]?\s+(\d+)\s+([0-9.]+)k\s*$")


def to_messages(row: dict) -> dict:
    """One training row in mlx-lm chat format: the same prompt as every other method, and the JSON answer."""
    return {"messages": [{"role": "user", "content": ev.make_prompt(row["intake"])},
                         {"role": "assistant", "content": ev.answer_text(row["answer"])}]}


def write_split(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(to_messages(r), ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def parse_report(line: str) -> dict | None:
    m = REPORT.search(line)
    if not m:
        t = TABLE.match(ANSI.sub("", line).strip("\r\n "))
        if not t:
            return None
        return {"step": int(t[1]), "loss": float(t[2]), "lr": 0.0, "it_per_s": 0.0, "tok_per_s": float(t[3]),
                "tokens_seen": int(float(t[4]) * 1000), "gpu_mem_gb": 0.0}
    return {"step": int(m[1]), "loss": float(m[2]), "lr": float(m[3]), "it_per_s": float(m[4]), "tok_per_s": float(m[5]),
            "tokens_seen": int(m[6]), "gpu_mem_gb": float(m[7])}


def clean_answer(text: str) -> str:
    """Drop any thinking block the chat template asks the model to open, keeping what follows."""
    return text.split("</think>")[-1].strip() if "</think>" in text else text.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    ap.add_argument("--train", default=str(HERE / "data" / "v2" / "triage-train.jsonl"))
    ap.add_argument("--dev", default=str(HERE / "data" / "triage-dev.jsonl"))
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--iters", type=int, default=800)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--max_len", type=int, default=512)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--num_layers", type=int, default=-1)
    ap.add_argument("--report", type=int, default=5)
    a = ap.parse_args()

    out = Path(a.runs) / a.tag
    (out / "mlxdata").mkdir(parents=True, exist_ok=True)
    train_rows, dev_rows = ev.read_rows(Path(a.train)), ev.read_rows(Path(a.dev))
    write_split(out / "mlxdata" / "train.jsonl", train_rows)
    write_split(out / "mlxdata" / "valid.jsonl", dev_rows)
    meta = {"method": "sft", "seed": a.seed, "size": "0.8b", "mode": "lora", "backend": "mlx", "model": a.model, "total_steps": a.iters,
            "pid": os.getpid(), "engineering_only": True, "jev_derived": False, "clinical_data": False, "started": time.time()}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    tele = (out / "telemetry.jsonl").open("a", buffering=1)

    cmd = [sys.executable, "-m", "mlx_lm", "lora", "--model", a.model, "--train", "--data", str(out / "mlxdata"), "--batch-size", str(a.batch),
           "--iters", str(a.iters), "--learning-rate", str(a.lr), "--num-layers", str(a.num_layers), "--mask-prompt", "--grad-checkpoint",
           "--max-seq-length", str(a.max_len), "--adapter-path", str(out / "adapter"), "--steps-per-report", str(a.report),
           "--steps-per-eval", str(a.iters + 1), "--save-every", "100", "--seed", str(a.seed)]
    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    with (out / "mlx.log").open("w") as log:
        for line in proc.stdout:
            log.write(line)
            log.flush()
            rep = parse_report(line)
            if rep:
                rep.update({"total_steps": a.iters, "elapsed_s": time.time() - start, "examples_seen": rep["step"] * a.batch})
                tele.write(json.dumps(rep) + "\n")
    code = proc.wait()
    if code != 0:
        meta["failed"] = True
        meta["note"] = f"mlx_lm lora exited {code}; see mlx.log"
        (out / "meta.json").write_text(json.dumps(meta, indent=2))
        return code

    from mlx_lm import generate, load
    model, tok = load(a.model, adapter_path=str(out / "adapter"))
    tk = getattr(tok, "_tokenizer", tok)

    def gen(prompt: str) -> str:
        try:
            text = tk.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True, tokenize=False, enable_thinking=False)
        except TypeError:
            text = tk.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True, tokenize=False)
        return clean_answer(generate(model, tok, prompt=text, max_tokens=100, verbose=False))

    result = ev.evaluate(dev_rows, gen)
    result["constant_baselines"] = ev.constant_baselines(dev_rows)
    result.update({"method": "sft", "seed": a.seed, "model": a.model, "backend": "mlx", "train_seconds": time.time() - start})
    (out / "results.json").write_text(json.dumps(result, indent=2))
    meta["done"] = True
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: result[k] for k in ("n", "valid_json_rate", "mean_reward", "danger_cases", "danger_missed", "danger_miss_rate")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
