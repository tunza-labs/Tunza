"""Print compact dev and sealed evaluation summaries without exposing case rows."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


METRICS = ("mean_reward", "danger_missed", "valid_json_rate")


def _read(path):
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


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
        if not folder.is_dir() or not ((folder / "results.json").is_file() or (folder / "sealed.json").is_file()):
            continue
        dev = _read(folder / "results.json")
        sealed = _read(folder / "sealed.json")
        meta = _read(folder / "meta.json")
        records.append((folder.name, dev.get("method", meta.get("method")), meta.get("mode"),
                        dev.get("seed", meta.get("seed")), dev, sealed))

    _table(("run", "method", "mode (lora/full)", "seed", "dev reward", "dev danger missed",
            "sealed reward", "sealed danger missed", "valid JSON"),
           ((name, method, mode, seed, dev.get("mean_reward"), dev.get("danger_missed"),
             sealed.get("mean_reward"), sealed.get("danger_missed"), dev.get("valid_json_rate"))
            for name, method, mode, seed, dev, sealed in records))
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    print_tables(parser.parse_args().runs)
