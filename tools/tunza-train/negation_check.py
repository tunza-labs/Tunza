#!/usr/bin/env python3
"""Find danger keywords that sit inside a negation and compare decide()-style regex labels with the file's label.

Engineering shakedown only. Read-only on every input. Writes one review table, nothing else.

  python negation_check.py --out <folder outside the repo>/negation_table.md
  python negation_check.py --skip-private --out negation_table.md

decide() mirror: the danger stage of decide() in Tunza lib/assessment.ts (DANGER_PATTERNS, the structured
danger fields and the sleepy + difficult breathing branch). Keep this in sync if assessment.ts changes.

Status per story with at least one negated danger keyword:
  FALSE_GO  regex says go_now, file label is not go_now
  MISS      regex says not go_now, file label is go_now
  AGREE     regex and file label agree
Fire basis: negated-only (regex go_now comes only from negated keywords), mixed (a positive app keyword also present),
structured (go_now from intake fields), none (regex not go_now).

The file labels come from decide() itself, so FALSE_GO and MISS show drift between this mirror and decide(). They
cannot show that a label is clinically wrong. The line column is the 1-based line in the source file. Sources with
identical bytes (v2 and v3 sealed) are scanned once.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from danger_patterns import PATTERNS  # noqa: E402

DATA = HERE / "data"
PRIVATE_SEALED = Path(r"C:\Users\hirsc\tunza-train\private\triage-sealed.jsonl")

SPLIT_FILES = [
    ("train", "triage-train.jsonl", DATA / "triage-train.jsonl"),
    ("test", "triage-dev.jsonl", DATA / "triage-dev.jsonl"),
    ("train", "v2/triage-train.jsonl", DATA / "v2" / "triage-train.jsonl"),
    ("test", "v2/triage-sealed.jsonl", DATA / "v2" / "triage-sealed.jsonl"),
    ("train", "v3/triage-train.jsonl", DATA / "v3" / "triage-train.jsonl"),
    ("test", "v3/triage-sealed.jsonl", DATA / "v3" / "triage-sealed.jsonl"),
]

# DANGER_PATTERNS in lib/assessment.ts. Order matches the source.
DANGER_PATTERNS = PATTERNS

# Broader keyword forms, only used to find negated mentions. They never change the regex verdict.
EXTRA_PATTERNS = [
    ("dangerNotBreathing", re.compile(r"stop(?:ped|s)? breathing")),
    ("dangerSeizure", re.compile(r"\bfits\b|seizures")),
    ("dangerBlueLips", re.compile(r"bluish (?:lips|face)")),
]
KEYWORD_PATTERNS = DANGER_PATTERNS + EXTRA_PATTERNS

CUE = re.compile(
    r"not|no|never|without|none|nothing|nobody|isn't|wasn't|weren't|didn't|doesn't|don't|hasn't|haven't|hadn't"
    r"|hakuna|hana|hapana|hajakuwa|hajapata|hajaanza|hajaonyesha|bila|sina|si"
    r"|ne|není|nemá|nebyl|nebyla|bez"
)
CLAUSE_BREAK = re.compile(r"[.;,!?]|\b(?:but|however|though|lakini)\b")
WORD = re.compile(r"\w+(?:'\w+)?")
CUE_WINDOW = 4  # words before the keyword, inside the same clause


@dataclass
class Hit:
    key: str
    term: str
    start: int
    end: int
    negated: bool
    app: bool  # from DANGER_PATTERNS, not EXTRA_PATTERNS


def is_negated(low: str, start: int) -> bool:
    before = low[:start]
    breaks = list(CLAUSE_BREAK.finditer(before))
    segment = before[breaks[-1].end():] if breaks else before
    words = WORD.findall(segment)[-CUE_WINDOW:]
    return any(CUE.fullmatch(word) for word in words)


def find_hits(text: str) -> list[Hit]:
    low = text.lower()
    hits, seen = [], set()
    for index, (key, pattern) in enumerate(KEYWORD_PATTERNS):
        for m in pattern.finditer(low):
            if (key, m.start()) in seen:  # an EXTRA form overlapping an app hit, e.g. "seizures"
                continue
            seen.add((key, m.start()))
            hits.append(Hit(key, m.group(0), m.start(), m.end(), is_negated(low, m.start()), index < len(DANGER_PATTERNS)))
    return sorted(hits, key=lambda h: h.start)


def has_injury(text: str) -> bool:
    return bool(re.search(r"wound|cut|bleed|injury|burn|fall|jeraha|ajali|damu", text.lower()))


def decide_danger_keys(intake: dict) -> tuple[list[str], bool]:
    """Returns (danger keys, sleepy + difficult branch) the way decide() does before its go_now return."""
    text = str(intake.get("presentation") or "")
    low = text.lower()
    keys = [key for key, pattern in DANGER_PATTERNS if pattern.search(low)]
    if intake.get("awake") == "not_waking":
        keys.append("dangerNotWaking")
    if intake.get("breathing") == "severe":
        keys.append("dangerStrugglingBreathe")
    if intake.get("drinking") == "no" and intake.get("who") == "child":
        keys.append("dangerChildNoDrink")
    if intake.get("mainProblem") == "injury" and has_injury(text):
        if re.search(r"heavy|won'?t stop|a lot|nyingi", low):
            keys.append("dangerHeavyBleeding")
    sleepy = intake.get("breathing") == "difficult" and intake.get("awake") == "sleepy"
    return sorted(set(keys)), sleepy


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def analyse(row: dict) -> dict | None:
    intake = row.get("intake") or {}
    text = str(intake.get("presentation") or "")
    hits = find_hits(text)
    negated = [h for h in hits if h.negated]
    if not negated:
        return None
    keys, sleepy = decide_danger_keys(intake)
    presentation_keys = [key for key, pattern in DANGER_PATTERNS if pattern.search(text.lower())]
    structured = [k for k in keys if k not in presentation_keys]
    regex_go_now = bool(keys) or sleepy
    positive = any(h.app and not h.negated for h in hits)
    if not regex_go_now:
        basis = "none"
    elif structured or sleepy:
        basis = "structured"
    elif positive:
        basis = "mixed"
    else:
        basis = "negated-only"
    label_go_now = row["answer"]["disposition"] == "go_now"
    if regex_go_now and not label_go_now:
        status = "FALSE_GO"
    elif label_go_now and not regex_go_now:
        status = "MISS"
    else:
        status = "AGREE"
    first = negated[0]
    return {
        "status": status,
        "basis": basis,
        "regex_go_now": regex_go_now,
        "regex_keys": keys,
        "label": row["answer"]["disposition"],
        "negated_terms": [h.term for h in negated],
        "snippet": text.lower()[max(0, first.start - 40):first.end + 20],
    }


def md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def build(inputs: list[tuple[str, str, Path]]) -> tuple[list[dict], Counter]:
    rows_out = []
    totals: Counter = Counter()
    for split, label, path in inputs:
        rows = read_rows(path)
        totals[(label, "rows")] = len(rows)
        for index, row in enumerate(rows):
            found = analyse(row)
            if found is None:
                continue
            found.update({"split": split, "source": label, "line": index + 1})
            rows_out.append(found)
            totals[(label, "negated")] += 1
            totals[(label, found["status"])] += 1
    return rows_out, totals


def write_table(out: Path, rows_out: list[dict], totals: Counter, inputs: list[tuple[str, str, Path]]) -> None:
    order = {"FALSE_GO": 0, "MISS": 1, "AGREE": 2}
    rows_out = sorted(rows_out, key=lambda r: (order[r["status"]], r["source"], r["line"]))
    lines = [
        "# Negation check (engineering shakedown, promotion=false)",
        "",
        "Regex verdict: decide() danger stage mirror. File label: answer.disposition. Read-only. No data changed.",
        "",
        "## Summary",
        "",
        "| source | rows | negated rows | FALSE_GO | MISS | AGREE |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split, label, _ in inputs:
        lines.append(
            f"| {label} ({split}) | {totals[(label, 'rows')]} | {totals[(label, 'negated')]} "
            f"| {totals[(label, 'FALSE_GO')]} | {totals[(label, 'MISS')]} | {totals[(label, 'AGREE')]} |"
        )
    lines += [
        "",
        "## Stories with a negated danger keyword",
        "",
        "| status | basis | source | line | regex keys | file label | negated terms | snippet |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for r in rows_out:
        lines.append(
            f"| {r['status']} | {r['basis']} | {md_cell(r['source'])} | {r['line']} "
            f"| {md_cell(', '.join(r['regex_keys']) or '-')} | {r['label']} "
            f"| {md_cell(', '.join(r['negated_terms']))} | {md_cell(r['snippet'])} |"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def unique_inputs(inputs: list[tuple[str, str, Path]]) -> list[tuple[str, str, Path]]:
    """Drop a source whose bytes equal an earlier one, so a shared file is not counted twice."""
    seen, out = {}, []
    for split, label, path in inputs:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            print(f"skip {label}: same bytes as {seen[digest]}")
            continue
        seen[digest] = label
        out.append((split, label, path))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # required: the table quotes private story snippets, so it has no default inside the repo
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--private", type=Path, default=PRIVATE_SEALED)
    ap.add_argument("--skip-private", action="store_true")
    args = ap.parse_args(argv)
    inputs = list(SPLIT_FILES)
    if not args.skip_private:
        if not args.private.is_file():
            ap.error(f"private file not found: {args.private}. Pass --private <path> or --skip-private.")
        inputs.append(("private-test", "private/triage-sealed.jsonl", args.private))
    inputs = unique_inputs(inputs)
    rows_out, totals = build(inputs)
    write_table(args.out, rows_out, totals, inputs)
    counts = Counter(r["status"] for r in rows_out)
    print(f"negated rows: {len(rows_out)}  FALSE_GO: {counts['FALSE_GO']}  MISS: {counts['MISS']}  AGREE: {counts['AGREE']}")
    print(f"table: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
