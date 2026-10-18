#!/usr/bin/env python3
"""Pull the synthetic triage rows out of the frozen sft-v1.1 files into small train and dev files.

The public-math rows in sft-v1.1 carry no disposition and are left out. Labels in these rows come from Tunza's own
decide() rules, never from a model. Engineering shakedown data only: no clinical data, no Jev output.

  python tools/tunza-train/build_data.py --src <dir with train.jsonl and holdout.jsonl> --out tools/tunza-train/data
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def triage_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        lines = [ln for ln in handle if ln.strip()]
    for line in lines:
        row = json.loads(line)
        msgs = row["messages"]
        try:
            answer = json.loads(msgs[-1]["content"])
        except ValueError:
            continue
        if isinstance(answer, dict) and "disposition" in answer:
            rows.append({"intake": json.loads(msgs[0]["content"])["intake"], "answer": answer})
    return rows


def write(path: Path, rows: list[dict]) -> str:
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default=str(Path(__file__).with_name("data")))
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    train, dev = triage_rows(src / "train.jsonl"), triage_rows(src / "holdout.jsonl")
    manifest = {
        "schema_version": 1,
        "source": "tunza-sft-v1.1 triage rows",
        "label_source": "Tunza decide() rules (lib/assessment.ts), not a model",
        "jev_derived": False,
        "clinical_data": False,
        "files": {
            "triage-train.jsonl": {"rows": len(train), "sha256": write(out / "triage-train.jsonl", train)},
            "triage-dev.jsonl": {"rows": len(dev), "sha256": write(out / "triage-dev.jsonl", dev)},
        },
        "note": "dev is the development slice for choosing methods. The sealed test is built separately and never lives in this folder.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
