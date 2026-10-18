"""Loss functions and helpers for the preference and reinforcement methods. Standard library plus torch passed in by the caller.

orpo: supervised loss plus an odds-ratio term that pushes the correct answer above a worse one (no reference model).
dpo:  direct preference optimisation against the model with its adapter switched off, plus a supervised term to keep the JSON format stable.
rejected_text: a plausible wrong answer for a case, built from the rules (never from a model, never from Jev).
rl_gate: the reward's own T7 rule. Reinforcement learning from the untuned model is blocked while the untuned model scores below "always go_now".
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import evaluate as ev

FOUR = ("go_now", "get_care_today", "need_one_more_answer", "monitor_at_home")


def rejected_text(row: dict, rng: random.Random) -> str:
    """A worse answer for the same case: for a danger case any lower urgency (a missed danger); otherwise too urgent or too relaxed."""
    expected = row["answer"]["disposition"]
    rank = ev.reward.RANK[expected]
    if rank == 40:
        pool = [d for d in FOUR if ev.reward.RANK[d] < 40]
    else:
        pool = ["go_now"] + [d for d in FOUR if d != expected and ev.reward.RANK[d] != rank]
    pick = rng.choice(pool)
    question = ev.reward.ASK_QUESTION if pick == "need_one_more_answer" else None
    return ev.reward.render_output(pick, [], question)


def seq_logprobs(model, ids, lab, att, torch):
    """Sum of token log-probabilities of the labelled tokens, and the count, per row."""
    logits = model(input_ids=ids, attention_mask=att).logits[:, :-1].float()
    tgt = lab[:, 1:]
    mask = (tgt != -100).float()
    logp = torch.log_softmax(logits, dim=-1).gather(2, tgt.clamp(min=0).unsqueeze(-1)).squeeze(-1)
    return (logp * mask).sum(1), mask.sum(1).clamp(min=1)


def orpo_loss(lp_c, n_c, lp_r, n_r, torch, lam: float = 0.5):
    mc, mr = lp_c / n_c, lp_r / n_r
    eps = 1e-6

    def log_odds(m):
        p = torch.exp(m).clamp(max=1 - eps)
        return m - torch.log1p(-p)

    margin = log_odds(mc) - log_odds(mr)
    return (-mc - lam * torch.nn.functional.logsigmoid(margin)).mean()


def dpo_loss(lp_c, lp_r, ref_c, ref_r, n_c, torch, beta: float = 0.1, nll_weight: float = 1.0):
    margin = beta * ((lp_c - ref_c) - (lp_r - ref_r))
    return (-torch.nn.functional.logsigmoid(margin) + nll_weight * (-(lp_c / n_c))).mean()


def rl_gate(runs: Path, method: str, seed: int, prefix: str = "") -> tuple[bool, str]:
    """T7: block reinforcement learning from the untuned model when always-go_now beats it. sft_grpo needs a finished SFT run that beats go_now."""
    def load(tag):
        p = Path(runs) / tag / "results.json"
        return json.loads(p.read_text()) if p.is_file() else None

    base = load("base-0.8b")
    if method == "grpo":
        if base is None:
            return False, "T7: no untuned baseline recorded, so RL from base is blocked"
        go_now = base["constant_baselines"]["go_now"]
        if base["mean_reward"] <= go_now:
            return False, f"T7: untuned model scores {base['mean_reward']:.3f}, not above always-go_now {go_now:.3f}; RL from base is blocked"
        return True, "T7 passed"
    sft = load(f"{prefix}sft-0.8b-s{seed}")
    if sft is None:
        return False, f"no finished {prefix}sft-0.8b-s{seed} to start RL from"
    go_now = sft["constant_baselines"]["go_now"]
    if sft["mean_reward"] <= go_now:
        return False, f"SFT checkpoint scores {sft['mean_reward']:.3f}, not above always-go_now {go_now:.3f}"
    return True, f"SFT checkpoint {sft['mean_reward']:.3f} beats always-go_now {go_now:.3f}"
