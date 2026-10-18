#!/usr/bin/env python3
"""Score a saved adapter on a file of cases (for example the sealed test) with the code-owned reward. Read once per candidate.

  python tools/tunza-train/eval_adapter.py --adapter runs/v2-sft-0.8b-s0/adapter --file tools/tunza-train/data/v2/triage-sealed.jsonl --out runs/v2-sft-0.8b-s0/sealed.json
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    ap.add_argument("--file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_new", type=int, default=100)
    a = ap.parse_args()
    import torch
    cuda = torch.cuda.is_available()
    if cuda:
        from unsloth import FastLanguageModel
        model, tok = FastLanguageModel.from_pretrained(a.adapter, max_seq_length=768, dtype=torch.bfloat16, load_in_4bit=False)
        FastLanguageModel.for_inference(model)
    else:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(a.model)
        base = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.bfloat16 if torch.backends.mps.is_available() else torch.float32)
        model = PeftModel.from_pretrained(base, a.adapter)
        if torch.backends.mps.is_available():
            model = model.to("mps")
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
    result.update({"adapter": a.adapter, "file": a.file, "seconds": time.time() - start})
    Path(a.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("n", "valid_json_rate", "mean_reward", "danger_cases", "danger_missed", "danger_miss_rate")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
