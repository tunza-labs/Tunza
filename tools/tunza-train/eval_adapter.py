#!/usr/bin/env python3
"""Score a saved adapter on a file of cases (for example the sealed test) with the code-owned reward. Read once per candidate.

  python tools/tunza-train/eval_adapter.py --adapter runs/v2-sft-0.8b-s0/adapter --file tools/tunza-train/data/v2/triage-sealed.jsonl --out runs/v2-sft-0.8b-s0/sealed.json

Without --model the base is the one recorded in the adapter's adapter_config.json. A full fine-tune
(no adapter_config.json) is loaded from the folder itself. A folder with neither file is an error. The --out
JSON records the base the scores came from under "base".
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate as ev  # noqa: E402
from train import chat_prompt_ids  # noqa: E402

DEFAULT_BASE = "Qwen/Qwen3.5-0.8B"


def recorded_base(adapter: Path) -> str | None:
    cfg = adapter / "adapter_config.json"
    if not cfg.exists():
        return None
    try:
        return json.loads(cfg.read_text(encoding="utf-8")).get("base_model_name_or_path")
    except (OSError, ValueError) as exc:
        print(f"warning: cannot read {cfg}: {exc}", file=sys.stderr)
        return None


def resolve_base(adapter: Path, model: str | None) -> str:
    # --model wins. Without it, use the base the adapter was trained on.
    recorded = recorded_base(adapter)
    if model is None:
        if recorded is None:
            print(f"warning: no base recorded in {adapter}; using {DEFAULT_BASE}", file=sys.stderr)
        return recorded or DEFAULT_BASE
    if recorded and recorded != model:
        print(f"warning: --model {model} differs from the adapter's base {recorded}", file=sys.stderr)
    return model


def base_used(base: str, adapter: str, cuda: bool) -> str:
    """The weights the run is scored on: the folder for a full fine-tune, else the base load_model attaches to."""
    recorded = recorded_base(Path(adapter))
    if not (Path(adapter) / "adapter_config.json").exists():
        return adapter
    return (recorded or base) if cuda else base


def load_model(base: str, adapter: str, cuda: bool):
    import torch
    if cuda:
        # unsloth reads the base from adapter_config.json itself and also loads a full fine-tune folder
        from unsloth import FastLanguageModel
        if recorded_base(Path(adapter)) not in (None, base):
            print(f"warning: on CUDA the adapter's own base is used; {base} is ignored", file=sys.stderr)
        model, tok = FastLanguageModel.from_pretrained(adapter, max_seq_length=768, dtype=torch.bfloat16, load_in_4bit=False)
        FastLanguageModel.for_inference(model)
        return model, tok
    from transformers import AutoModelForCausalLM, AutoTokenizer
    dtype = torch.bfloat16 if torch.backends.mps.is_available() else torch.float32
    if (Path(adapter) / "adapter_config.json").exists():
        from peft import PeftModel
        tok = AutoTokenizer.from_pretrained(base)
        model = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(base, torch_dtype=dtype), adapter)
    else:
        tok = AutoTokenizer.from_pretrained(adapter)
        model = AutoModelForCausalLM.from_pretrained(adapter, torch_dtype=dtype)
    if torch.backends.mps.is_available():
        model = model.to("mps")
    return model, tok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--model", default=None, help="base model; default: the base recorded in the adapter's adapter_config.json")
    ap.add_argument("--file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_new", type=int, default=100)
    a = ap.parse_args()
    folder = Path(a.adapter)
    if not ((folder / "adapter_config.json").is_file() or (folder / "config.json").is_file()):
        ap.error(f"{a.adapter} holds neither adapter_config.json (LoRA) nor config.json (full fine-tune); pass runs/<tag>/adapter")
    import torch
    cuda = torch.cuda.is_available()
    base = resolve_base(folder, a.model)
    model, tok = load_model(base, a.adapter, cuda)
    tok = getattr(tok, "tokenizer", tok)
    model.eval()
    device = next(model.parameters()).device
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    pad = tok.pad_token_id if tok.pad_token_id is not None else im_end

    @torch.no_grad()
    def generate(prompt: str) -> str:
        ids = torch.tensor([chat_prompt_ids(tok, prompt)], device=device)
        res = model.generate(input_ids=ids, max_new_tokens=a.max_new, do_sample=False, eos_token_id=[im_end, tok.eos_token_id], pad_token_id=pad)
        return tok.decode(res[0, ids.shape[1]:], skip_special_tokens=True).strip()

    rows = ev.read_rows(Path(a.file))
    start = time.time()
    result = ev.evaluate(rows, generate)
    result["constant_baselines"] = ev.constant_baselines(rows)
    result.update({"adapter": a.adapter, "base": base_used(base, a.adapter, cuda), "file": a.file, "seconds": time.time() - start})
    Path(a.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("n", "valid_json_rate", "mean_reward", "danger_cases", "danger_missed", "danger_miss_rate")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
