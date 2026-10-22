"""Count missed danger rows per keyword family for each run, and list rows that many runs missed.

Reads runs/*/private-v2.json and the sealed private triage file. Writes one markdown report.
Engineering shakedown only. Nothing here changes labels, rewards, or checkpoint choice.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "reward"))
import tunza_reward as reward  # noqa: E402
from danger_patterns import FAMILIES  # noqa: E402  (the app lowercases the story before matching)

RUNS = Path(r"C:\Users\hirsc\tunza-train\runs")
SEALED = Path(r"C:\Users\hirsc\tunza-train\private\triage-sealed.jsonl")
DANGER_RANK = reward.RANK["go_now"]
STOPPED_MISS = "danger_under_triage"
NO_FAMILY = "no-family"


def read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def same_file(recorded, sealed_path):
    """True when the file a run records names sealed_path. A relative record must match the path's tail."""
    if not recorded:
        return True  # older results do not record the file
    parts = [p.lower() for p in Path(str(recorded).replace("\\", "/")).parts]
    target = [p.lower() for p in Path(sealed_path).resolve().parts]
    if Path(str(recorded).replace("\\", "/")).is_absolute():
        return [p.lower() for p in Path(recorded).resolve().parts] == target
    return target[-len(parts):] == parts


def families_in(story):
    text = story.lower()
    return [name for name, pattern in FAMILIES.items() if pattern.search(text)]


def read_run(path, labels, sealed_path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"]
    if len(rows) != len(labels):
        raise ValueError(f"{path}: {len(rows)} rows, sealed file has {len(labels)}")
    missed = set()
    for index, row in enumerate(rows):
        if row["expected"] != labels[index]:
            raise ValueError(f"{path}: row {index} expected {row['expected']}, sealed says {labels[index]}")
        is_danger = reward.RANK[row["expected"]] == DANGER_RANK
        if is_danger and (row["stopped"] == STOPPED_MISS or row["predicted"] == "invalid"):
            missed.add(index)
    return {
        "name": path.parent.name,
        "missed": missed,
        "file_missed": data["danger_missed"],
        "danger_cases": data["danger_cases"],
        "same_file": same_file(data.get("file"), sealed_path),
    }


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines


def build_report(runs_dir, sealed_path, min_runs):
    sealed = read_jsonl(sealed_path)
    stories = [case["intake"]["presentation"] for case in sealed]
    labels = [case["answer"]["disposition"] for case in sealed]
    danger_rows = sum(1 for label in labels if reward.RANK[label] == DANGER_RANK)
    folders = [p for p in Path(runs_dir).iterdir() if p.is_dir()]
    run_paths = sorted(Path(runs_dir).glob("*/private-v2.json"))
    if not run_paths:
        raise ValueError(f"no */private-v2.json under {runs_dir}")
    runs = [read_run(path, labels, sealed_path) for path in run_paths]

    run_rows = []
    row_misses = Counter()
    for run in runs:
        counts = Counter()
        no_family = 0
        for index in run["missed"]:
            found = families_in(stories[index])
            counts.update(found)
            no_family += not found
        row_misses.update(run["missed"])
        check = "ok" if len(run["missed"]) == run["file_missed"] and run["danger_cases"] == danger_rows else "MISMATCH"
        if not run["same_file"]:
            check = "OTHER FILE"
        run_rows.append([run["name"], len(run["missed"]), *(counts[name] for name in FAMILIES), no_family,
                         run["file_missed"], check])

    frequent = sorted(((index, n) for index, n in row_misses.items() if n >= min_runs), key=lambda item: (-item[1], item[0]))
    story_rows = [[index, labels[index], f"{n} of {len(runs)}", ", ".join(families_in(stories[index])) or NO_FAMILY,
                   stories[index]] for index, n in frequent]

    lines = [
        "# Danger keyword misses",
        "",
        f"Run folders: {len(folders)}. Runs with private-v2.json: {len(runs)}. "
        f"Folders without it: {len(folders) - len(runs)}.",
        "",
        f"Sealed file: {sealed_path}. Sealed rows: {len(sealed)}. Danger rows: {danger_rows} (go_now or escalate). "
        "Row indexes are 0-based positions in this file only.",
        "",
        "A row counts under every family its story matches. no-family means no presentation keyword matched: "
        "the app may still flag the row from awake not_waking, breathing severe, a child not drinking, or "
        "injury wording (heavy, won't stop, a lot, nyingi). Check OTHER FILE means the run records a different "
        "sealed file.",
        "",
        "## Misses per run",
        "",
        *table(["run", "missed", *FAMILIES, NO_FAMILY, "file danger missed", "check"], run_rows),
        "",
        f"## Rows missed by {min_runs} or more runs",
        "",
        *(table(["row (index)", "expected", "runs missed", "families", "story"], story_rows) if story_rows else ["None."]),
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--sealed", type=Path, default=SEALED)
    parser.add_argument("--min-runs", type=int, default=3)
    # no default file: the report quotes private stories, so it is only written where asked
    parser.add_argument("--out", type=Path, help="also write the report here (outside the repo)")
    args = parser.parse_args()
    report = build_report(args.runs, args.sealed, args.min_runs)
    if args.out:
        # the report quotes sealed stories, so stdout gets the counts only
        args.out.write_text(report, encoding="utf-8")
        print(report.split("## Rows missed by", 1)[0] + f"Full report: {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
