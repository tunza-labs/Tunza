"""Code-owned Tunza RL reward.

Grades the model's raw disposition before reconcile() can raise it.
Does not import TypeSafe, Jev, or the dpi router. Jev supplies no reward.

Output contract (spec D4), one JSON object and nothing else:

    {"disposition": "<one of six>", "danger_facts": ["..."], "follow_up_question": "<string or null>"}

PC field binding, checked 2026-10-14 against
output/tunza-build/anti-cheating/pc-install/source/training/eval_candidate.py:
the PC schema names the question field follow_up_question, not next_question.
danger_facts is absent from that schema. The reward rules do not change, so a
PC-shaped object that omits danger_facts fails the format gate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

JEV_DERIVED = False
MINIMUM_REWARD = -1.0
MAXIMUM_REWARD = 1.0
T7_SKIP_REASON = "base outputs not yet recorded"

DISPOSITIONS = (
    "go_now",
    "get_care_today",
    "monitor_at_home",
    "need_one_more_answer",
    "escalate",
    "abstain",
)
RL_EXPECTED = (
    "go_now",
    "escalate",
    "get_care_today",
    "need_one_more_answer",
    "monitor_at_home",
)
RANK = {
    "go_now": 40,
    "escalate": 40,
    "get_care_today": 30,
    "need_one_more_answer": 20,
    "abstain": 20,
    "monitor_at_home": 10,
}
LEGACY_ALIASES = (
    "urgent",
    "see-clinic",
    "see_clinic",
    "self-care",
    "self_care",
)
PC_FIELD_BINDING = {
    "disposition": "disposition",
    "follow_up_question": "follow_up_question",
}
SPEC_ONLY_FIELDS = ("danger_facts",)
REQUIRED_FIELDS = ("disposition", "danger_facts", "follow_up_question")
ASK_QUESTION = "What else is observed?"
DANGER_TOKEN = "synthetic-danger-token"
REFERENCE_MIX_COUNTS = {
    "go_now": 4,
    "escalate": 2,
    "need_one_more_answer": 4,
    "get_care_today": 5,
    "monitor_at_home": 5,
}
# Published D6 means for well-formed constant dispositions on the 20-case mix.
# All-go_now is -0.05 only with the empty danger_facts penalty on expected-danger cases.
CONSTANT_POLICY_MEANS = {
    "go_now": -0.05,
    "get_care_today": -0.185,
    "need_one_more_answer": -0.30,
    "monitor_at_home": -0.32,
}
LANGUAGE_ALIASES = {
    "en": "en",
    "english": "en",
    "sw": "sw",
    "swahili": "sw",
    "kiswahili": "sw",
    "code-switch": "code-switch",
    "code_switch": "code-switch",
    "codeswitch": "code-switch",
}
FREE_TEXT_KEYS = ("presentation", "story", "text", "free_text", "complaint")
_RANK_BLOCK = re.compile(r"const\s+RANK\b[^=]*=\s*\{(?P<body>.*?)\};", re.S)
_RANK_ENTRY = re.compile(
    r"""(?:"(?P<quoted>[^"]+)"|'(?P<single>[^']+)'|(?P<bare>[A-Za-z_][\w-]*))\s*:\s*(?P<value>\d+)"""
)
_DECODER = json.JSONDecoder()


@dataclass(frozen=True)
class RewardResult:
    reward: float
    raw_disposition: str | None
    reconciled_disposition: str | None
    disagreement_reason: str | None
    language: str | None
    stopped: str | None
    format_error: str | None
    core: float | None
    follow_up_penalty: float
    danger_facts_penalty: float


def parse_rank_source(source: str) -> dict[str, int]:
    """Parse the RANK object from reconcile.ts text. Does not execute it."""
    match = _RANK_BLOCK.search(source)
    if not match:
        raise ValueError("RANK table not found")
    found: dict[str, int] = {}
    for entry in _RANK_ENTRY.finditer(match.group("body")):
        key = entry.group("quoted") or entry.group("single") or entry.group("bare")
        found[key] = int(entry.group("value"))
    if set(DISPOSITIONS) - set(found):
        raise ValueError("RANK table is missing a contract disposition")
    return found


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower()
    if key in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[key]
    return value.strip()


def render_output(
    disposition: str,
    danger_facts: list[str],
    follow_up_question: str | None,
) -> str:
    return json.dumps(
        {
            "disposition": disposition,
            "danger_facts": danger_facts,
            "follow_up_question": follow_up_question,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def constant_output(disposition: str) -> str:
    """Well-formed constant policy. Ask emits one question. Facts stay empty."""
    question = ASK_QUESTION if disposition == "need_one_more_answer" else None
    return render_output(disposition, [], question)


def reference_output(case: dict) -> str:
    expected = case["expected"]
    facts = [DANGER_TOKEN] if RANK[expected] == 40 else []
    question = ASK_QUESTION if expected == "need_one_more_answer" else None
    return render_output(expected, facts, question)


def reference_cases() -> list[dict]:
    """20 synthetic cases at the D6 disposition mix. Not a language-quota set."""
    cases: list[dict] = []
    index = 0
    languages = ("en", "sw", "code-switch")
    for disposition, count in REFERENCE_MIX_COUNTS.items():
        for number in range(count):
            cases.append(
                {
                    "id": f"mix-{disposition}-{number}",
                    "lineage": "SYNTHETIC",
                    "language": languages[index % 3],
                    "expected": disposition,
                    "input": {
                        "presentation": f"synthetic case {DANGER_TOKEN}",
                        "marker": f"mix-{index}",
                    },
                }
            )
            index += 1
    return cases


def score_policy(cases: list[dict], output_for) -> list[RewardResult]:
    results = []
    for case in cases:
        results.append(
            score(
                output_for(case),
                expected=case["expected"],
                case_input=case.get("input"),
                language=case.get("language"),
            )
        )
    return results


def mean_reward(results: list[RewardResult]) -> float:
    if not results:
        raise ValueError("mean_reward requires at least one result")
    return sum(item.reward for item in results) / len(results)


def summarize_by_language(results: list[RewardResult]) -> dict:
    """Per-language means. Languages are not pooled."""
    buckets: dict[str, list[float]] = {}
    for item in results:
        language = item.language if item.language is not None else "unspecified"
        buckets.setdefault(language, []).append(item.reward)
    return {
        "by_language": {
            language: {"n": len(rewards), "mean": sum(rewards) / len(rewards)}
            for language, rewards in buckets.items()
        }
    }


def score(
    raw: str,
    *,
    expected: str,
    case_input: dict | None = None,
    free_text: str = "",
    language: str | None = None,
) -> RewardResult:
    if expected not in RL_EXPECTED:
        raise ValueError(f"expected is not an RL label: {expected}")
    language = normalize_language(language)
    parsed, format_error = _parse_output(raw)
    if format_error is not None:
        return _stopped(
            expected,
            None,
            language,
            "format",
            format_error,
            "format_gate",
        )
    raw_disposition = parsed["disposition"]
    reconciled, reason = _logged_reconcile(expected, raw_disposition)
    if RANK[expected] == 40 and RANK[raw_disposition] < 40:
        return RewardResult(
            reward=MINIMUM_REWARD,
            raw_disposition=raw_disposition,
            reconciled_disposition=reconciled,
            disagreement_reason=reason,
            language=language,
            stopped="danger_under_triage",
            format_error=None,
            core=None,
            follow_up_penalty=0.0,
            danger_facts_penalty=0.0,
        )
    core = _core_score(expected, raw_disposition)
    follow_penalty = -0.2 if _follow_up_violation(raw_disposition, parsed["follow_up_question"]) else 0.0
    facts_penalty = _danger_facts_penalty(
        expected,
        parsed["danger_facts"],
        case_input,
        free_text,
    )
    return RewardResult(
        reward=_clip(core + follow_penalty + facts_penalty),
        raw_disposition=raw_disposition,
        reconciled_disposition=reconciled,
        disagreement_reason=reason,
        language=language,
        stopped=None,
        format_error=None,
        core=core,
        follow_up_penalty=follow_penalty,
        danger_facts_penalty=facts_penalty,
    )


def reward(raw: str, **kwargs) -> float:
    return score(raw, **kwargs).reward


def _stopped(
    expected: str,
    raw_disposition: str | None,
    language: str | None,
    stopped: str,
    format_error: str | None,
    reason: str,
) -> RewardResult:
    return RewardResult(
        reward=MINIMUM_REWARD,
        raw_disposition=raw_disposition,
        reconciled_disposition=expected,
        disagreement_reason=reason,
        language=language,
        stopped=stopped,
        format_error=format_error,
        core=None,
        follow_up_penalty=0.0,
        danger_facts_penalty=0.0,
    )


def _clip(value: float) -> float:
    if value > MAXIMUM_REWARD:
        return MAXIMUM_REWARD
    if value < MINIMUM_REWARD:
        return MINIMUM_REWARD
    return value


def _parse_output(raw: object) -> tuple[dict | None, str | None]:
    if not isinstance(raw, str):
        return None, "output is not a string"
    text = raw.strip()
    if not text:
        return None, "output is empty"
    try:
        value, end = _DECODER.raw_decode(text)
    except json.JSONDecodeError:
        return None, "JSON does not parse"
    if text[end:].strip():
        return None, "text outside the JSON object"
    if not isinstance(value, dict):
        return None, "JSON value is not an object"
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ValueError as exc:
        return None, str(exc)
    if set(value) != set(REQUIRED_FIELDS):
        missing = [key for key in REQUIRED_FIELDS if key not in value]
        extra = [key for key in value if key not in REQUIRED_FIELDS]
        return None, f"fields missing={missing} extra={extra}"
    disposition = value["disposition"]
    facts = value["danger_facts"]
    question = value["follow_up_question"]
    if not isinstance(disposition, str) or disposition not in DISPOSITIONS:
        return None, "disposition is not one of the six"
    if not isinstance(facts, list) or any(not isinstance(item, str) for item in facts):
        return None, "danger_facts has the wrong type"
    if question is not None and not isinstance(question, str):
        return None, "follow_up_question has the wrong type"
    return value, None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    output: dict = {}
    for key, item in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = item
    return output


def _reject_non_finite(_value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _logged_reconcile(floor: str, candidate: str) -> tuple[str, str | None]:
    """Mirror reconcile(): the floor is logged, never used as the score."""
    if candidate == floor:
        return floor, None
    if candidate not in RANK:
        return floor, "candidate_unrecognized"
    if RANK[candidate] < RANK[floor]:
        return floor, "candidate_below_floor"
    return floor, "candidate_not_approved"


def _core_score(expected: str, predicted: str) -> float:
    if predicted == expected:
        return 1.0
    expected_rank = RANK[expected]
    predicted_rank = RANK[predicted]
    if expected_rank == 40:
        if predicted_rank == 40:
            return 0.8
        return MINIMUM_REWARD
    if expected == "get_care_today":
        if predicted_rank > expected_rank:
            return -0.3
        return -0.6
    if expected == "need_one_more_answer":
        if predicted == "abstain":
            return 0.3
        if predicted_rank == 30:
            return -0.3
        if predicted_rank >= 40:
            return -0.5
        return -0.6
    if expected == "monitor_at_home":
        if predicted in ("need_one_more_answer", "abstain"):
            return -0.2
        if predicted == "get_care_today":
            return -0.3
        if predicted_rank == 40:
            return -0.5
    raise ValueError(f"unscored pair: {expected} -> {predicted}")


def _follow_up_violation(disposition: str, question: str | None) -> bool:
    if disposition == "need_one_more_answer":
        if not isinstance(question, str):
            return True
        if not question.strip():
            return True
        if len(question) > 200:
            return True
        return question.count("?") != 1
    return question is not None


def _danger_facts_penalty(
    expected: str,
    facts: list[str],
    case_input: dict | None,
    free_text: str,
) -> float:
    if not facts:
        if RANK[expected] == 40:
            return -0.1
        return 0.0
    if _any_ungrounded(facts, case_input, free_text):
        return -0.2
    return 0.0


def _any_ungrounded(facts: list[str], case_input: dict | None, free_text: str) -> bool:
    text = _free_text(case_input, free_text).casefold()
    pairs = _field_pairs(case_input)
    for fact in facts:
        if not fact.strip():
            return True
        if fact in pairs:
            continue
        if text and fact.casefold() in text:
            continue
        return True
    return False


def _free_text(case_input: dict | None, free_text: str) -> str:
    parts: list[str] = []
    if free_text:
        parts.append(free_text)

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in FREE_TEXT_KEYS and isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    if case_input is not None:
        walk(case_input)
    return "\n".join(parts)


def _field_pairs(case_input: dict | None) -> set[str]:
    pairs: set[str] = set()

    def add(key: str, value: object) -> None:
        if value is None:
            rendered = "null"
        elif isinstance(value, str):
            rendered = value
        else:
            return
        pairs.add(f"{key}={rendered}")

    def walk(value: object, prefix: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                dotted = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(item, (dict, list)):
                    walk(item, dotted)
                else:
                    add(str(key), item)
                    add(dotted, item)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}.{index}" if prefix else str(index))

    if case_input is not None:
        walk(case_input, "")
    return pairs
