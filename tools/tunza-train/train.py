#!/usr/bin/env python3
"""LoRA fine-tune a small Qwen3.5 model on Tunza triage rows and score it on the development slice.

Methods in this file: sft, sft_cost (supervised, rows weighted by the reward's urgency rank). Other methods plug in beside them.
Writes the run folder that live.py reads: meta.json, telemetry.jsonl, layerstats.json, results.json, adapter/.
Engineering run only. Not clinical, never promoted, no Jev output anywhere.

  python tools/tunza-train/train.py --method sft --model Qwen/Qwen3.5-0.8B --seed 0 --steps 60
  python tools/tunza-train/train.py --method base --model Qwen/Qwen3.5-0.8B     # untuned baseline, no training
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as ev  # noqa: E402

TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj", "in_proj_qkv", "in_proj_z", "out_proj"]


def row_weights(rows: list[dict], method: str) -> list[float]:
    """sft: every row 1.0. sft_cost: urgency rank / mean rank, so a missed go_now costs most and the mean stays 1."""
    if method != "sft_cost":
        return [1.0] * len(rows)
    ranks = [ev.reward.RANK[r["answer"]["disposition"]] for r in rows]
    mean = sum(ranks) / len(ranks)
    return [x / mean for x in ranks]


def lr_at(step: int, total: int, base: float, warmup: int = 5) -> float:
    if step <= warmup:
        return base * step / max(1, warmup)
    progress = (step - warmup) / max(1, total - warmup)
    return base * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress)))


def build_example(tok, intake: dict, answer: dict, max_len: int, im_end: int) -> dict:
    """Prompt tokens are masked out of the loss; only the JSON answer and the end token are learned."""
    prompt_ids = chat_prompt_ids(tok, ev.make_prompt(intake))
    answer_ids = tok(ev.answer_text(answer), add_special_tokens=False)["input_ids"] + [im_end]
    ids = (prompt_ids + answer_ids)[:max_len]
    labels = ([-100] * len(prompt_ids) + answer_ids)[:max_len]
    return {"ids": ids, "labels": labels}


def chat_prompt_ids(tok, prompt: str) -> list[int]:
    msgs = [{"role": "user", "content": prompt}]
    try:
        out = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, enable_thinking=False)
    except TypeError:
        out = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True)
    return list(out["input_ids"]) if hasattr(out, "keys") else list(out)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def layer_rows(model, grads: dict) -> list[dict]:
    """Per layer and module: how far the adapter has moved (|B| over |A|) and its latest gradient size."""
    mods: dict[tuple[int, str], dict] = {}
    for name, p in model.named_parameters():
        m = re.search(r"layers\.(\d+)\..*?([A-Za-z_]+)\.lora_([AB])\.", name)
        if not m or not p.requires_grad:
            continue
        key = (int(m.group(1)), m.group(2))
        d = mods.setdefault(key, {"A": 0.0, "B": 0.0, "g": 0.0})
        d[m.group(3)] += float(p.detach().float().norm())
        d["g"] += grads.get(name, 0.0)
    return [{"layer": k[0], "mod": k[1], "rel_change": v["B"] / (v["A"] + 1e-8), "grad": v["g"]} for k, v in sorted(mods.items())]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["base", "sft", "sft_cost"], required=True)
    ap.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    ap.add_argument("--train", default=str(HERE / "data" / "triage-train.jsonl"))
    ap.add_argument("--dev", default=str(HERE / "data" / "triage-dev.jsonl"))
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--tag")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max_len", type=int, default=768)
    ap.add_argument("--max_new", type=int, default=100)
    a = ap.parse_args()

    size = (re.search(r"(\d+(?:\.\d+)?B)", a.model) or [None, "?"])[1].lower()
    tag = a.tag or f"{a.method}-{size}-s{a.seed}-{time.strftime('%m%d-%H%M%S')}"
    out = Path(a.runs) / tag
    out.mkdir(parents=True, exist_ok=True)
    train_rows, dev_rows = ev.read_rows(Path(a.train)), ev.read_rows(Path(a.dev))
    meta = {"method": a.method, "seed": a.seed, "size": size, "mode": "lora", "model": a.model, "total_steps": a.steps if a.method != "base" else 1,
            "pid": os.getpid(), "train_sha256": sha256_file(Path(a.train)), "dev_sha256": sha256_file(Path(a.dev)),
            "engineering_only": True, "jev_derived": False, "clinical_data": False, "started": time.time()}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    random.seed(a.seed)
    import torch
    cuda = torch.cuda.is_available()
    if cuda:
        from unsloth import FastLanguageModel  # must load before transformers
    torch.manual_seed(a.seed)
    if cuda:
        model, tok = FastLanguageModel.from_pretrained(a.model, max_seq_length=a.max_len, dtype=torch.bfloat16, load_in_4bit=False)
        if a.method != "base":
            model = FastLanguageModel.get_peft_model(model, r=a.rank, target_modules=TARGETS, lora_alpha=a.rank * 2, lora_dropout=0.0,
                                                     bias="none", use_gradient_checkpointing="unsloth", random_state=a.seed)
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import LoraConfig, get_peft_model
        tok = AutoTokenizer.from_pretrained(a.model)
        model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.float32)
        if a.method != "base":
            model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=a.rank * 2, target_modules=TARGETS, task_type="CAUSAL_LM"))
    tok = getattr(tok, "tokenizer", tok)  # Qwen3.5 loads as a multimodal processor; the text tokenizer is inside
    device = next(model.parameters()).device
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    pad = tok.pad_token_id if tok.pad_token_id is not None else im_end
    start = time.time()

    if a.method != "base":
        examples = [build_example(tok, r["intake"], r["answer"], a.max_len, im_end) for r in train_rows]
        weights = row_weights(train_rows, a.method)
        params = [p for p in model.parameters() if p.requires_grad]
        opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
        if cuda:
            FastLanguageModel.for_training(model)
        model.train()
        order, seen, tok_count = [], 0, 0
        tele = (out / "telemetry.jsonl").open("a", buffering=1)
        for step in range(1, a.steps + 1):
            for g in opt.param_groups:
                g["lr"] = lr_at(step, a.steps, a.lr)
            total_loss, t0 = 0.0, time.time()
            for _ in range(a.accum):
                if len(order) < a.batch:
                    order += random.sample(range(len(examples)), len(examples))
                idx, order = order[:a.batch], order[a.batch:]
                width = max(len(examples[i]["ids"]) for i in idx)
                ids = torch.tensor([examples[i]["ids"] + [pad] * (width - len(examples[i]["ids"])) for i in idx], device=device)
                lab = torch.tensor([examples[i]["labels"] + [-100] * (width - len(examples[i]["labels"])) for i in idx], device=device)
                att = torch.tensor([[1] * len(examples[i]["ids"]) + [0] * (width - len(examples[i]["ids"])) for i in idx], device=device)
                w = torch.tensor([weights[i] for i in idx], device=device, dtype=torch.float32)
                logits = model(input_ids=ids, attention_mask=att).logits[:, :-1].float()
                tgt = lab[:, 1:]
                ce = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.size(-1)), tgt.reshape(-1), ignore_index=-100, reduction="none").view(tgt.shape)
                mask = (tgt != -100).float()
                per_row = (ce * mask).sum(1) / mask.sum(1).clamp(min=1)
                loss = (per_row * w).mean() / a.accum
                loss.backward()
                total_loss += float(loss)
                seen += len(idx)
                tok_count += int(att.sum())
            grads = {n: float(p.grad.detach().float().norm()) for n, p in model.named_parameters() if p.requires_grad and p.grad is not None}
            gnorm = float(torch.nn.utils.clip_grad_norm_(params, 1.0))
            opt.step()
            opt.zero_grad(set_to_none=True)
            elapsed = time.time() - start
            tele.write(json.dumps({"step": step, "total_steps": a.steps, "loss": total_loss, "lr": lr_at(step, a.steps, a.lr), "grad_norm": gnorm,
                                   "tok_per_s": tok_count / max(1e-9, elapsed), "examples_seen": seen, "elapsed_s": elapsed,
                                   "gpu_mem_gb": (torch.cuda.max_memory_allocated() / 2**30) if cuda else None}) + "\n")
            if step % 3 == 0 or step == a.steps:
                (out / "layerstats.json.tmp").write_text(json.dumps({"step": step, "steps": a.steps, "loss": total_loss, "rows": layer_rows(model, grads), "recent": []}))
                (out / "layerstats.json.tmp").replace(out / "layerstats.json")
        model.save_pretrained(out / "adapter")
        model.eval()
        if cuda:
            FastLanguageModel.for_inference(model)
    else:
        model.eval()
        (out / "telemetry.jsonl").write_text(json.dumps({"step": 1, "total_steps": 1, "loss": None, "elapsed_s": 0}) + "\n")

    @torch.no_grad()
    def generate(prompt: str) -> str:
        ids = torch.tensor([chat_prompt_ids(tok, prompt)], device=device)
        res = model.generate(input_ids=ids, max_new_tokens=a.max_new, do_sample=False, eos_token_id=[im_end, tok.eos_token_id], pad_token_id=pad)
        return tok.decode(res[0, ids.shape[1]:], skip_special_tokens=True).strip()

    result = ev.evaluate(dev_rows, generate)
    result["constant_baselines"] = ev.constant_baselines(dev_rows)
    result["train_seconds"] = time.time() - start
    result.update({"method": a.method, "seed": a.seed, "model": a.model})
    (out / "results.json").write_text(json.dumps(result, indent=2))
    meta["done"] = True
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: result[k] for k in ("n", "valid_json_rate", "mean_reward", "danger_cases", "danger_missed", "danger_miss_rate")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
