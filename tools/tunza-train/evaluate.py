"""Score model answers on Tunza triage rows with the code-owned reward. The model's raw answer is graded before any floor rule.

Used by train.py after a run and for the untuned baseline. Nothing here calls TypeSafe or Jev.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "reward"))
import tunza_reward as reward  # noqa: E402

DISPOSITIONS = reward.DISPOSITIONS
SYSTEM = (
    "You are a triage decision model for community health. Read the intake and answer with exactly one JSON object and "
    "nothing else, with keys disposition, danger_facts and follow_up_question. disposition is one of: go_now, "
    "get_care_today, monitor_at_home, need_one_more_answer, escalate, abstain. danger_facts lists the danger signs "
    "that justify go_now, copied from the intake, and is empty otherwise. follow_up_question is one question when more "
    "information is needed, otherwise null. Never choose a lower urgency when a danger sign is present."
)


def make_prompt(intake: dict) -> str:
    return SYSTEM + "\n\n" + json.dumps({"intake": intake}, ensure_ascii=False)


def answer_text(answer: dict) -> str:
    return reward.render_output(answer["disposition"], list(answer.get("danger_facts") or []), answer.get("follow_up_question"))


def read_rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evaluate(rows: list[dict], generate) -> dict:
    """generate(prompt) -> raw model text. Returns metrics and per-row results."""
    results, confusion, per_row = [], Counter(), []
    danger_total = danger_missed = 0
    for row in rows:
        expected = row["answer"]["disposition"]
        raw = generate(make_prompt(row["intake"]))
        res = reward.score(raw, expected=expected, case_input=row["intake"])
        results.append(res)
        predicted = res.raw_disposition or "invalid"
        confusion[(expected, predicted)] += 1
        is_danger = reward.RANK[expected] == 40
        if is_danger:
            danger_total += 1
            if res.stopped == "danger_under_triage" or res.raw_disposition is None:
                danger_missed += 1
        per_row.append({"expected": expected, "predicted": predicted, "reward": res.reward, "stopped": res.stopped})
    n = len(rows)
    valid = sum(1 for r in results if r.format_error is None)
    return {
        "n": n,
        "valid_json_rate": valid / n if n else 0.0,
        "mean_reward": sum(r.reward for r in results) / n if n else 0.0,
        "danger_cases": danger_total,
        "danger_missed": danger_missed,
        "danger_miss_rate": danger_missed / danger_total if danger_total else None,
        "confusion": {f"{e}->{p}": c for (e, p), c in sorted(confusion.items())},
        "rows": per_row,
    }


def constant_baselines(rows: list[dict]) -> dict:
    out = {}
    for disp in ("go_now", "get_care_today", "need_one_more_answer", "monitor_at_home"):
        out[disp] = evaluate(rows, lambda _prompt, d=disp: reward.constant_output(d))["mean_reward"]
    return out
