"""Print compact dev, sealed and private evaluation summaries without exposing case rows."""

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path


METRICS = ("mean_reward", "danger_missed", "valid_json_rate")
FAMILY = re.compile(r"v\d+")


def _read(path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def _family(name):
    """The tag family from the run folder name, e.g. v2 for v2-full-sft-0.8b-s0. None when untagged."""
    head = name.split("-", 1)[0]
    return head if FAMILY.fullmatch(head) else None


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        print("| " + " | ".join(_fmt(value) for value in row) + " |")


def print_tables(runs):
    records = []
    for folder in sorted(Path(runs).iterdir()):
        if not folder.is_dir() or not any((folder / f).is_file() for f in ("results.json", "sealed.json", "private-v2.json")):
            continue
        dev = _read(folder / "results.json")
        sealed = _read(folder / "sealed.json")
        meta = _read(folder / "meta.json")
        private = _read(folder / "private-v2.json")
        records.append((folder.name, dev.get("method", meta.get("method")), meta.get("mode"),
                        dev.get("seed", meta.get("seed")), dev, sealed,
                        _family(folder.name), meta.get("size"), private))

    _table(("run", "method", "mode (lora/full)", "seed", "dev reward", "dev danger missed",
            "sealed reward", "sealed danger missed", "valid JSON"),
           ((name, method, mode, seed, dev.get("mean_reward"), dev.get("danger_missed"),
             sealed.get("mean_reward"), sealed.get("danger_missed"), dev.get("valid_json_rate"))
            for name, method, mode, seed, dev, sealed, *_ in records))
    print()
    groups = defaultdict(list)
    for record in records:
        if record[1] is not None:
            groups[record[1]].append(record)

    def summary(items, key, index):
        values = [item[index][key] for item in items if isinstance(item[index].get(key), (int, float))]
        if not values:
            return None, None
        return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0

    _table(("method", "seeds", "dev reward mean", "dev reward std", "dev danger missed mean",
            "dev danger missed std", "sealed reward mean", "sealed reward std",
            "sealed danger missed mean", "sealed danger missed std", "valid JSON mean", "valid JSON std"),
           ((method, len({item[3] for item in items if item[3] is not None}),
             *summary(items, "mean_reward", 4), *summary(items, "danger_missed", 4),
             *summary(items, "mean_reward", 5), *summary(items, "danger_missed", 5),
             *summary(items, "valid_json_rate", 4)) for method, items in sorted(groups.items())))
    print()
    families = defaultdict(list)
    for record in records:
        # a scored folder without a method still gets a row, under method "?"
        if record[1] is not None or record[8]:
            families[(record[6], record[1] or "?", record[7], record[2])].append(record)

    def scored(item):
        return isinstance(item[8].get("mean_reward"), (int, float))

    def private_summary(items, key):
        values = [item[8][key] for item in items if isinstance(item[8].get(key), (int, float))]
        if not values:
            return None, None
        return statistics.mean(values), max(values) - min(values)

    # runs: folders in the group. private runs: folders the mean and range are taken over. private seeds: their seeds.
    print("Private set (private-v2.json). Sweep variants with the same four keys are pooled.")
    _table(("family", "method", "size", "mode", "runs", "private runs", "private seeds", "private reward mean",
            "private reward range", "private danger missed mean", "private danger missed range"),
           ((family, method, size, mode, len(items), sum(1 for item in items if scored(item)),
             len({item[3] for item in items if scored(item) and item[3] is not None}),
             *private_summary(items, "mean_reward"), *private_summary(items, "danger_missed"))
            for (family, method, size, mode), items in sorted(
                families.items(), key=lambda group: tuple(str(part or "") for part in group[0]))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    print_tables(parser.parse_args().runs)
