"""Count training rows that contain each danger keyword alternative. Exit 1 when any has fewer than MIN_ROWS.

  python tools/tunza-train/keyword_coverage.py [--train data/v3/triage-train.jsonl]

The alternatives are the app's own regexes (danger_patterns.py), matched like presentationDangerSigns(): on the
lowercased presentation only. decide()'s structured danger paths (awake not_waking, breathing severe, a child not
drinking, injury wording) are not counted. Counts are over the whole file, not per language.

This reports a gap. It does not add rows: filling a gap means new generator stories, which are out of scope here.
Do not lower MIN_ROWS to pass.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from danger_patterns import ALTERNATIVES  # noqa: E402

TRAIN_PATH = HERE / "data" / "v3" / "triage-train.jsonl"
MIN_ROWS = 15
_COMPILED = [(group, alt, re.compile(alt)) for group, alt in ALTERNATIVES]


def read_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def presentation(row):
    # the app matches DANGER_PATTERNS against answers.presentation.toLowerCase()
    return str((row.get("intake") or {}).get("presentation") or "").lower()


def count_alternatives(rows):
    counts = Counter()
    for row in rows:
        text = presentation(row)
        for _, alt, pattern in _COMPILED:
            if pattern.search(text):
                counts[alt] += 1
    return {(group, alt): counts[alt] for group, alt in ALTERNATIVES}


def thin_alternatives(rows, min_rows=MIN_ROWS):
    return [(group, alt, n) for (group, alt), n in count_alternatives(rows).items() if n < min_rows]


def format_thin(thin):
    return "\n".join(f"  {group:<15} {alt:<36} {n:>4} rows" for group, alt, n in thin)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Danger keyword coverage of a training file.")
    ap.add_argument("--train", type=Path, default=TRAIN_PATH)
    a = ap.parse_args(argv)
    if not a.train.is_file():
        print(f"No such file: {a.train}")
        return 2
    rows = read_rows(a.train)
    if not rows:
        print(f"No rows in {a.train}")
        return 1
    thin = thin_alternatives(rows)
    if not thin:
        print(f"All danger alternatives have at least {MIN_ROWS} rows in {a.train}.")
        return 0
    print(f"Thin danger alternatives in {a.train} (need {MIN_ROWS} rows each):\n{format_thin(thin)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
