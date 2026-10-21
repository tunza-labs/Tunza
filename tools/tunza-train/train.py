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
import methods as mt  # noqa: E402

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


PROBE_OPTIONS = ["go_now", "get_care_today", "need_one_more_answer", "monitor_at_home", "escalate", "abstain"]


def intake_text(intake: dict) -> str:
    """Plain text for the live page: the story first, then the structured answers."""
    facts = " · ".join(f"{k}: {intake[k]}" for k in ("who", "awake", "breathing", "drinking", "duration", "mainProblem") if intake.get(k))
    return f"{intake.get('presentation', '')}\n{facts}".strip()


def disposition_step(token_text_so_far: list[str]) -> int | None:
    """Index of the generated token where the disposition value begins, found from the text written so far."""
    running = ""
    for i, piece in enumerate(token_text_so_far):
        if running.replace(" ", "").endswith('"disposition":"'):
            return i
        running += piece
    return None


def softmax_over(logits: list[float]) -> list[float]:
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps)
    return [e / total for e in exps]


def probe_example(model, tok, row: dict, device, pad: int, im_end: int, cuda: bool, torch):
    """Run the model on one example and read its own probabilities for each disposition at the moment it writes it."""
    ids = torch.tensor([chat_prompt_ids(tok, ev.make_prompt(row["intake"]))], device=device)
    with torch.no_grad():
        out = model.generate(input_ids=ids, max_new_tokens=70, do_sample=False, output_scores=True, return_dict_in_generate=True,
                             eos_token_id=[im_end, tok.eos_token_id], pad_token_id=pad)
    gen = out.sequences[0, ids.shape[1]:].tolist()
    pieces = [tok.decode([t]) for t in gen]
    at = disposition_step(pieces)
    if at is None or at >= len(out.scores):
        return None
    first_ids = [tok(name, add_special_tokens=False)["input_ids"][0] for name in PROBE_OPTIONS]
    row_logits = out.scores[at][0].float().cpu()
    probs = softmax_over([float(row_logits[i]) for i in first_ids])
    label = PROBE_OPTIONS.index(row["answer"]["disposition"])
    return {"text": intake_text(row["intake"]), "probs": probs, "label": label, "danger": 0, "options": PROBE_OPTIONS}


RL_METHODS = ("sft_grpo", "sft_rloo", "sft_ppo")


def grpo_phase(model, tok, rows, a, out, tele, step0, device, pad, im_end, cuda, torch, FastLM, start, recent):
    """Group-relative policy gradient with the code-owned reward. Each step: sample answers for a danger case and another case,
    score them with the reward, and move toward the answers that beat their group's average. loss in telemetry is the negative mean reward."""
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.grpo_lr, weight_decay=0.0)
    rng = random.Random(a.seed + 1)
    danger = [r for r in rows if ev.reward.RANK[r["answer"]["disposition"]] == 40]
    other = [r for r in rows if ev.reward.RANK[r["answer"]["disposition"]] != 40]
    stop_ids = {im_end, tok.eos_token_id}
    for g in range(1, a.grpo_steps + 1):
        picks = [rng.choice(danger), rng.choice(other)]
        if cuda:
            FastLM.for_inference(model)
        model.eval()
        samples, rewards, misses = [], [], 0
        for row in picks:
            pids = chat_prompt_ids(tok, ev.make_prompt(row["intake"]))
            ids = torch.tensor([pids] * a.group, device=device)
            with torch.no_grad():
                res = model.generate(input_ids=ids, max_new_tokens=70, do_sample=True, temperature=1.0, top_p=0.95,
                                     eos_token_id=[im_end, tok.eos_token_id], pad_token_id=pad)
            group = []
            for k in range(a.group):
                c = res[k, len(pids):].tolist()
                for i, t in enumerate(c):
                    if t in stop_ids:
                        c = c[:i + 1]
                        break
                text = tok.decode([t for t in c if t not in stop_ids]).strip()
                result = ev.reward.score(text, expected=row["answer"]["disposition"], case_input=row["intake"])
                group.append((c, result.reward))
                rewards.append(result.reward)
                if result.stopped == "danger_under_triage":
                    misses += 1
            mean = sum(r for _, r in group) / len(group)
            std = (sum((r - mean) ** 2 for _, r in group) / len(group)) ** 0.5
            gsum = sum(r for _, r in group)
            for c, r in group:
                if a.method == "sft_rloo":  # leave-one-out baseline, no std scaling
                    adv = r - (gsum - r) / max(1, len(group) - 1)
                else:
                    adv = 0.0 if std < 1e-6 else (r - mean) / (std + 1e-4)
                samples.append((pids, c, adv))
        if cuda:
            torch.cuda.empty_cache()
            FastLM.for_training(model)
        model.train()
        opt.zero_grad(set_to_none=True)
        total, used = 0.0, 0

        def seq_lp(pids, c):
            ids = torch.tensor([pids + c], device=device)
            logits = model(input_ids=ids).logits[0, len(pids) - 1:-1].float()
            return torch.log_softmax(logits, dim=-1).gather(1, torch.tensor(c, device=device)[:, None])[:, 0]

        old_lp = {}
        if a.method == "sft_ppo":  # sampling policy's token log-probs, fixed for the clipped ratio
            with torch.no_grad():
                for i, (pids, c, adv) in enumerate(samples):
                    if adv != 0.0 and c:
                        old_lp[i] = seq_lp(pids, c).detach()
        for ep in range(a.ppo_epochs if a.method == "sft_ppo" else 1):
            if ep:
                opt.zero_grad(set_to_none=True)
            for i, (pids, c, adv) in enumerate(samples):
                if adv == 0.0 or not c:
                    continue
                lp = seq_lp(pids, c)
                if a.method == "sft_ppo":
                    ratio = torch.exp(lp - old_lp[i])
                    adv_t = torch.tensor(adv, device=device)
                    loss = -torch.minimum(ratio * adv_t, torch.clamp(ratio, 1 - a.clip, 1 + a.clip) * adv_t).mean() / max(1, len(samples))
                else:
                    loss = -(adv * lp.mean()) / max(1, len(samples))
                loss.backward()
                total += float(loss)
                used += 1
            if a.method == "sft_ppo" and ep + 1 < a.ppo_epochs:
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                opt.step()
        grads = {n: float(p.grad.detach().float().norm()) for n, p in model.named_parameters() if p.requires_grad and p.grad is not None}
        gnorm = float(torch.nn.utils.clip_grad_norm_(params, 1.0)) if used else 0.0
        if used:
            opt.step()
        opt.zero_grad(set_to_none=True)
        mean_reward = sum(rewards) / len(rewards)
        step = step0 + g
        tele.write(json.dumps({"step": step, "total_steps": a.steps + a.grpo_steps, "loss": -mean_reward, "reward_mean": mean_reward,
                               "danger_miss_frac": misses / len(rewards), "grad_norm": gnorm, "lr": a.grpo_lr, "tok_per_s": None,
                               "examples_seen": g * len(picks), "elapsed_s": time.time() - start,
                               "gpu_mem_gb": (torch.cuda.max_memory_allocated() / 2**30) if cuda else None}) + "\n")
        if g % 3 == 0 or g == a.grpo_steps:
            (out / "layerstats.json.tmp").write_text(json.dumps({"step": step, "steps": a.steps + a.grpo_steps, "loss": -mean_reward,
                                                                 "rows": layer_rows(model, grads), "recent": recent}))
            (out / "layerstats.json.tmp").replace(out / "layerstats.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["base", "sft", "sft_cost", "orpo", "dpo", "sft_grpo", "sft_rloo", "sft_ppo"], required=True)
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
    ap.add_argument("--grpo_steps", type=int, default=40)
    ap.add_argument("--grpo_lr", type=float, default=1e-5)
    ap.add_argument("--group", type=int, default=6)
    ap.add_argument("--ppo_epochs", type=int, default=2, help="sft_ppo: gradient passes over each sampled batch")
    ap.add_argument("--clip", type=float, default=0.2, help="sft_ppo: ratio clip")
    ap.add_argument("--sealed", default=None, help="also score this sealed test file after training (slow; use for finalists)")
    ap.add_argument("--grad_ckpt", action="store_true", help="trade speed for memory on the Apple Silicon path (8 GB Macs)")
    ap.add_argument("--full", action="store_true", help="full fine-tune: train every weight, no LoRA (needs a 24 GB+ GPU such as Jacob's RTX 5090)")
    ap.add_argument("--no_probe", action="store_true", help="skip the live example probe on the page")
    a = ap.parse_args()

    size = (re.search(r"(\d+(?:\.\d+)?B)", a.model) or [None, "?"])[1].lower()
    tag = a.tag or f"{a.method}-{size}-s{a.seed}-{time.strftime('%m%d-%H%M%S')}"
    out = Path(a.runs) / tag
    out.mkdir(parents=True, exist_ok=True)
    train_rows, dev_rows = ev.read_rows(Path(a.train)), ev.read_rows(Path(a.dev))
    meta = {"method": a.method, "seed": a.seed, "size": size, "mode": "full" if a.full else "lora", "model": a.model, "total_steps": (a.steps + (a.grpo_steps if a.method in RL_METHODS else 0)) if a.method != "base" else 1,
            "pid": os.getpid(), "train_sha256": sha256_file(Path(a.train)), "dev_sha256": sha256_file(Path(a.dev)),
            "engineering_only": True, "jev_derived": False, "clinical_data": False, "started": time.time()}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    if a.method in RL_METHODS:
        ok, why = mt.rl_gate(Path(a.runs), a.method, a.seed, prefix=tag[:tag.index(a.method)] if a.method in tag else "", size=size)
        meta["rl_gate"] = why
        (out / "meta.json").write_text(json.dumps(meta, indent=2))
        if not ok:
            print("BLOCKED:", why, flush=True)
            return 3
    random.seed(a.seed)
    import torch
    cuda = torch.cuda.is_available()
    if cuda:
        from unsloth import FastLanguageModel  # must load before transformers
    torch.manual_seed(a.seed)
    if cuda:
        model, tok = FastLanguageModel.from_pretrained(a.model, max_seq_length=a.max_len, dtype=torch.bfloat16, load_in_4bit=False, **({"full_finetuning": True} if a.full else {}))
        if a.method != "base" and not a.full:
            model = FastLanguageModel.get_peft_model(model, r=a.rank, target_modules=TARGETS, lora_alpha=a.rank * 2, lora_dropout=0.0,
                                                     bias="none", use_gradient_checkpointing="unsloth", random_state=a.seed)
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import LoraConfig, get_peft_model
        # Apple Silicon (MPS) path: no Unsloth, plain transformers and peft. CPU is the last resort.
        mps = torch.backends.mps.is_available()
        tok = AutoTokenizer.from_pretrained(a.model)
        model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.bfloat16 if mps else torch.float32)
        if a.grad_ckpt:
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
            model.enable_input_require_grads()
        if a.method != "base":
            model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=a.rank * 2, target_modules=TARGETS, task_type="CAUSAL_LM"))
        if mps:
            model = model.to("mps")
    processor = tok  # kept whole so a full fine-tune can save the tokenizer files next to the weights
    tok = getattr(tok, "tokenizer", tok)  # Qwen3.5 loads as a multimodal processor; the text tokenizer is inside
    device = next(model.parameters()).device
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    pad = tok.pad_token_id if tok.pad_token_id is not None else im_end
    start = time.time()

    if a.method != "base":
        examples = [build_example(tok, r["intake"], r["answer"], a.max_len, im_end) for r in train_rows]
        weights = row_weights(train_rows, a.method)
        rej_rng = random.Random(a.seed + 7)
        rej_examples = ([build_example(tok, r['intake'], json.loads(mt.rejected_text(r, rej_rng)), a.max_len, im_end) for r in train_rows]
                        if a.method in ("orpo", "dpo") else None)
        params = [p for p in model.parameters() if p.requires_grad]
        opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
        if cuda:
            FastLanguageModel.for_training(model)
        model.train()
        order, seen, tok_count = [], 0, 0
        recent: list[dict] = []
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
                if a.method in ("orpo", "dpo"):
                    rw = max(len(rej_examples[i]["ids"]) for i in idx)
                    rids = torch.tensor([rej_examples[i]["ids"] + [pad] * (rw - len(rej_examples[i]["ids"])) for i in idx], device=device)
                    rlab = torch.tensor([rej_examples[i]["labels"] + [-100] * (rw - len(rej_examples[i]["labels"])) for i in idx], device=device)
                    ratt = torch.tensor([[1] * len(rej_examples[i]["ids"]) + [0] * (rw - len(rej_examples[i]["ids"])) for i in idx], device=device)
                    lp_c, n_c = mt.seq_logprobs(model, ids, lab, att, torch)
                    lp_r, n_r = mt.seq_logprobs(model, rids, rlab, ratt, torch)
                    if a.method == "orpo":
                        loss = mt.orpo_loss(lp_c, n_c, lp_r, n_r, torch) / a.accum
                    else:
                        with torch.no_grad(), model.disable_adapter():
                            ref_c, _ = mt.seq_logprobs(model, ids, lab, att, torch)
                            ref_r, _ = mt.seq_logprobs(model, rids, rlab, ratt, torch)
                        loss = mt.dpo_loss(lp_c, lp_r, ref_c, ref_r, n_c, torch) / a.accum
                else:
                    logits = model(input_ids=ids, attention_mask=att).logits[:, :-1].float()
                    tgt = lab[:, 1:]
                    ce = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.size(-1)), tgt.reshape(-1), ignore_index=-100, reduction="none").view(tgt.shape)
                    mask = (tgt != -100).float()
                    per_row = (ce * mask).sum(1) / mask.sum(1).clamp(min=1)
                    w = torch.tensor([weights[i] for i in idx], device=device, dtype=torch.float32)
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
                rows_now = layer_rows(model, grads)
                if not a.no_probe:
                    try:
                        model.eval()
                        if cuda:
                            FastLanguageModel.for_inference(model)
                        ex = probe_example(model, tok, dev_rows[(step // 3) % len(dev_rows)], device, pad, im_end, cuda, torch)
                        if ex:
                            recent = (recent + [ex])[-10:]
                    except Exception as exc:  # the probe is for the page only; never stop training for it
                        print("probe skipped:", repr(exc)[:200], flush=True)
                    finally:
                        try:
                            if cuda:
                                torch.cuda.empty_cache()  # give the probe's memory back so the card does not spill into system RAM
                                FastLanguageModel.for_training(model)
                            model.train()
                        except Exception as exc:
                            print("could not return to training mode:", repr(exc)[:200], flush=True)
                            raise
                (out / "layerstats.json.tmp").write_text(json.dumps({"step": step, "steps": a.steps, "loss": total_loss, "rows": rows_now, "recent": recent}))
                (out / "layerstats.json.tmp").replace(out / "layerstats.json")
        if a.method in RL_METHODS:
            grpo_phase(model, tok, train_rows, a, out, tele, a.steps, device, pad, im_end, cuda, torch, FastLanguageModel if cuda else None, start, recent)
        model.save_pretrained(out / "adapter")
        if a.full:
            processor.save_pretrained(out / "adapter")  # without these files the saved model cannot be reloaded for scoring
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
    if a.sealed:
        sealed_rows = ev.read_rows(Path(a.sealed))
        sealed = ev.evaluate(sealed_rows, generate)
        sealed.pop("rows", None)
        sealed["constant_baselines"] = ev.constant_baselines(sealed_rows)
        result["sealed"] = sealed
    result["train_seconds"] = time.time() - start
    result.update({"method": a.method, "seed": a.seed, "model": a.model})
    (out / "results.json").write_text(json.dumps(result, indent=2))
    meta["done"] = True
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: result[k] for k in ("n", "valid_json_rate", "mean_reward", "danger_cases", "danger_missed", "danger_miss_rate")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
