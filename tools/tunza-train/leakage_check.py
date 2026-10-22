"""Check a test file for leakage against a training file.

For each test row, find the training row with the most similar story (character n-gram Jaccard) and check for identical structured rows. Prints a summary. Engineering check only: nothing here labels, ranks or filters rows.

  python leakage_check.py --train data/v3/triage-train.jsonl --test <test.jsonl> [--n 3] [--threshold 0.8] [--out report.json]

Structure means the intake fields other than the story, plus the answer. A row whose intake has no field besides the
story is never an identical structure. Identical answer means the answer block alone matches, with danger_facts
compared as a sorted list.

A near duplicate is similarity >= threshold, the same boundary gen_cases.py uses. The metric differs on purpose:
gen_cases.py uses 5-word shingles, this uses character n-grams, which also catch reworded stories.
The report records the sha256 of both files and warns when the test file is not a sealed file named in a manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as ev  # noqa: E402

DEFAULT_N = 3
DEFAULT_THRESHOLD = 0.8
STORY_KEYS = ev._STORY_KEYS  # the same keys evaluate.story_text reads


def normalise(text: str) -> str:
    return " ".join(text.lower().split())


def char_grams(text: str, n: int) -> frozenset[str]:
    text = normalise(text)
    if not text:
        return frozenset()
    if len(text) < n:
        return frozenset([text])
    return frozenset(text[i:i + n] for i in range(len(text) - n + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _answer(row: dict):
    answer = row.get("answer")
    if isinstance(answer, dict) and isinstance(answer.get("danger_facts"), list):
        answer = {**answer, "danger_facts": sorted(map(str, answer["danger_facts"]))}
    return answer


def structure_key(row: dict) -> str | None:
    """None when the intake has no field besides the story: an empty structure would match every such row."""
    intake = row.get("intake") if isinstance(row.get("intake"), dict) else {}
    structure = {k: v for k, v in intake.items() if k not in STORY_KEYS}
    if not structure:
        return None
    return json.dumps({"intake": structure, "answer": _answer(row)}, sort_keys=True, ensure_ascii=False)


def answer_key(row: dict) -> str:
    return json.dumps(_answer(row), sort_keys=True, ensure_ascii=False)


def whitespace_story(row: dict) -> bool:
    """A story field that is present but only whitespace: a data fault, unlike an empty story."""
    intake = row.get("intake") if isinstance(row.get("intake"), dict) else {}
    values = [source.get(k) for source in (intake, row) for k in STORY_KEYS]
    return any(isinstance(v, str) and v and not v.strip() for v in values) and not ev.story_text(row)


def check(train_rows: list[dict], test_rows: list[dict], n: int = DEFAULT_N, threshold: float = DEFAULT_THRESHOLD) -> dict:
    train_grams = [char_grams(ev.story_text(row), n) for row in train_rows]
    train_structures = {structure_key(row) for row in train_rows} - {None}
    train_answers = {answer_key(row) for row in train_rows}
    results = []
    for index, row in enumerate(test_rows):
        grams = char_grams(ev.story_text(row), n)
        best_index, best = None, 0.0
        for j, candidate in enumerate(train_grams):
            score = jaccard(grams, candidate)
            if score > best:
                best_index, best = j, score
        reason = None
        if best_index is None:
            reason = "blank_story" if not grams else "no_match"
        results.append({
            "test_index": index,
            "nearest_train_index": best_index,
            "no_nearest_reason": reason,
            "similarity": round(best, 4),
            "near_duplicate": best_index is not None and best >= threshold,
            "identical_structure": structure_key(row) in train_structures,
            "identical_answer": answer_key(row) in train_answers,
        })
    total = len(results)

    def share(key: str) -> float | None:
        return round(sum(r[key] for r in results) / total, 4) if total else None

    return {
        "n_train": len(train_rows),
        "n_test": total,
        "n": n,
        "threshold": threshold,
        "blank_story_test_rows": sum(1 for row in test_rows if not ev.story_text(row).strip()),
        "whitespace_story_test_rows": sum(1 for row in test_rows if whitespace_story(row)),
        "near_duplicate_rows": sum(r["near_duplicate"] for r in results),
        "share_near_duplicate": share("near_duplicate"),
        "share_identical_structure": share("identical_structure"),
        "share_identical_answer": share("identical_answer"),
        "rows": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Story and structure leakage between a test file and a training file.")
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="character n-gram size")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="near duplicate when similarity is at or above this")
    parser.add_argument("--out", type=Path, help="write the full report with per-row results")
    args = parser.parse_args(argv)
    if args.n < 1:
        parser.error("--n must be at least 1")
    if not 0.0 < args.threshold <= 1.0:
        parser.error("--threshold must be in (0, 1]")
    report = check(ev.read_rows(args.train), ev.read_rows(args.test), args.n, args.threshold)
    head = {"train": str(args.train), "test": str(args.test),
            "train_sha256": sha256_file(args.train), "test_sha256": sha256_file(args.test)}
    sealed = manifest_sealed_hashes()
    head["test_in_manifest"] = head["test_sha256"] in sealed
    if not head["test_in_manifest"]:
        print(f"warning: {args.test} (sha256 {head['test_sha256'][:12]}) is not a sealed file named in "
              f"{', '.join(sorted(sealed.values())) or 'any data manifest'}", file=sys.stderr)
    if args.out:
        args.out.write_text(json.dumps({**head, **report}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "rows"}
    print(json.dumps({**head, **summary}, indent=2, ensure_ascii=False))
    return 0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_sealed_hashes(data_dir: Path = Path(__file__).resolve().parent / "data") -> dict[str, str]:
    """sha256 -> manifest path, for every triage-sealed.jsonl a data manifest records."""
    found = {}
    for manifest in sorted(data_dir.glob("*/manifest.json")):
        files = json.loads(manifest.read_text(encoding="utf-8")).get("files", {})
        sha = files.get("triage-sealed.jsonl", {}).get("sha256")
        if sha:
            found.setdefault(sha, str(manifest.relative_to(data_dir.parent)))
    return found


if __name__ == "__main__":
    sys.exit(main())
