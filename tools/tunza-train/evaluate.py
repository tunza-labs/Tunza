"""Score model answers on Tunza triage rows with the code-owned reward. The model's raw answer is graded before any floor rule.

Used by train.py after a run and for the untuned baseline. Nothing here calls TypeSafe or Jev.
"""
from __future__ import annotations

import json
import re
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
LANGUAGES = ("en", "sw", "code-switch")
DATA_DIR = Path(__file__).resolve().parent / "data"
_STORY_KEYS = ("presentation", "story", "text", "free_text", "complaint")
_LANG_FIELDS = ("language", "lang")
_MARKER = re.compile(r"^(?:lang=)?(en|sw|cs|code-switch)\|", re.I)
_WORD = re.compile(r"[A-Za-z']+")
_story_index: dict[str, str] | None = None
_lexicon: dict[str, set[str]] | None = None


def make_prompt(intake: dict) -> str:
    return SYSTEM + "\n\n" + json.dumps({"intake": intake}, ensure_ascii=False)


def answer_text(answer: dict) -> str:
    return reward.render_output(answer["disposition"], list(answer.get("danger_facts") or []), answer.get("follow_up_question"))


def read_rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def canonical_language(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip().lower()
    if key in ("cs", "code-switch", "code_switch", "codeswitch"):
        return "code-switch"
    normalized = reward.normalize_language(key)
    if normalized in LANGUAGES:
        return normalized
    return None


def story_text(row: dict) -> str:
    intake = row.get("intake") if isinstance(row.get("intake"), dict) else {}
    for source in (intake, row):
        for key in _STORY_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _load_story_index() -> tuple[dict[str, str], dict[str, set[str]]]:
    """Map story text to language using the language marker stored beside each data-file row."""
    index: dict[str, set[str]] = {}
    lexicon: dict[str, set[str]] = {lang: set() for lang in ("en", "sw", "cs")}
    families_path = DATA_DIR / "v2" / "families.json"
    if families_path.is_file():
        families = json.loads(families_path.read_text(encoding="utf-8"))
        for split, name in (("train", "triage-train.jsonl"), ("sealed", "triage-sealed.jsonl")):
            path = DATA_DIR / "v2" / name
            if not path.is_file() or split not in families:
                continue
            rows = read_rows(path)
            for row, fam in zip(rows, families[split]):
                lang = fam.get("lang") or str(fam.get("family", "")).split("|", 1)[0]
                if lang not in lexicon:
                    continue
                text = story_text(row)
                if text.strip():
                    index.setdefault(text, set()).add(lang)
                    lexicon[lang].update(w.lower() for w in _WORD.findall(text))
    for path in DATA_DIR.rglob("*.jsonl"):
        for row in read_rows(path):
            lang = _explicit_language(row)
            text = story_text(row)
            if lang and text.strip():
                short = {"en": "en", "sw": "sw", "code-switch": "cs"}[lang]
                index.setdefault(text, set()).add(short)
                lexicon[short].update(w.lower() for w in _WORD.findall(text))
    unique = {text: next(iter(langs)) for text, langs in index.items() if len(langs) == 1}
    return unique, lexicon


def _indexes() -> tuple[dict[str, str], dict[str, set[str]]]:
    global _story_index, _lexicon
    if _story_index is None or _lexicon is None:
        _story_index, _lexicon = _load_story_index()
    return _story_index, _lexicon


def _explicit_language(row: dict) -> str | None:
    intake = row.get("intake") if isinstance(row.get("intake"), dict) else {}
    answer = row.get("answer") if isinstance(row.get("answer"), dict) else {}
    for source in (row, intake, answer):
        for key in _LANG_FIELDS:
            found = canonical_language(source.get(key))
            if found:
                return found
    family = row.get("family") if isinstance(row.get("family"), str) else ""
    return canonical_language(family.split("|", 1)[0]) if family else None


def _lexicon_language(text: str, lexicon: dict[str, set[str]]) -> str | None:
    words = {w.lower() for w in _WORD.findall(text)}
    if not words:
        return None
    en, sw = lexicon["en"], lexicon["sw"]
    en_hits = len(words & (en - sw))
    sw_hits = len(words & (sw - en))
    if en_hits and sw_hits:
        return "code-switch"
    if sw_hits and not en_hits:
        return "sw"
    if en_hits and not sw_hits:
        return "en"
    return None


def row_language(row: dict) -> str | None:
    """Use a language field when the row has one. Otherwise read the story's language marker from data files."""
    found = _explicit_language(row)
    if found:
        return found
    text = story_text(row)
    marker = _MARKER.match(text.strip())
    if marker:
        return canonical_language(marker.group(1))
    index, lexicon = _indexes()
    tagged = index.get(text)
    if tagged:
        return canonical_language(tagged)
    return _lexicon_language(text, lexicon)


def _language_block(buckets: dict[str, dict]) -> dict:
    out = {}
    for lang in LANGUAGES:
        bucket = buckets[lang]
        n = bucket["n"]
        out[lang] = {
            "n": n,
            "mean_reward": sum(bucket["rewards"]) / n if n else 0.0,
            "danger_cases": bucket["danger_cases"],
            "danger_missed": bucket["danger_missed"],
        }
    return out


def evaluate(rows: list[dict], generate) -> dict:
    """generate(prompt) -> raw model text. Returns metrics and per-row results."""
    results, confusion, per_row = [], Counter(), []
    danger_total = danger_missed = 0
    buckets = {lang: {"n": 0, "rewards": [], "danger_cases": 0, "danger_missed": 0} for lang in LANGUAGES}
    for row in rows:
        expected = row["answer"]["disposition"]
        raw = generate(make_prompt(row["intake"]))
        res = reward.score(raw, expected=expected, case_input=row["intake"])
        results.append(res)
        predicted = res.raw_disposition or "invalid"
        confusion[(expected, predicted)] += 1
        is_danger = reward.RANK[expected] == 40
        missed = False
        if is_danger:
            danger_total += 1
            if res.stopped == "danger_under_triage" or res.raw_disposition is None:
                danger_missed += 1
                missed = True
        per_row.append({"expected": expected, "predicted": predicted, "reward": res.reward, "stopped": res.stopped})
        lang = row_language(row)
        if lang in buckets:
            bucket = buckets[lang]
            bucket["n"] += 1
            bucket["rewards"].append(res.reward)
            if is_danger:
                bucket["danger_cases"] += 1
                if missed:
                    bucket["danger_missed"] += 1
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
        "by_language": _language_block(buckets),
    }


def constant_baselines(rows: list[dict]) -> dict:
    out = {}
    for disp in ("go_now", "get_care_today", "need_one_more_answer", "monitor_at_home"):
        out[disp] = evaluate(rows, lambda _prompt, d=disp: reward.constant_output(d))["mean_reward"]
    return out
