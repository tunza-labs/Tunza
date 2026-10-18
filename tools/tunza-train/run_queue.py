#!/usr/bin/env python3
"""Run training jobs one after another on this machine, skipping any run that already has results.json.

Re-running the same command after a crash or restart picks up with the first run that is not finished.

  python tools/tunza-train/run_queue.py --methods sft sft_cost --seeds 1 2 --steps 80
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Preference methods run two answers per case, so they use a smaller batch on an 8 GB card, and a gentler learning rate.
EXTRA = {"orpo": ["--batch", "1", "--accum", "16", "--lr", "1e-4"], "dpo": ["--batch", "1", "--accum", "16", "--lr", "5e-5"]}


def plan(methods, seeds, size, steps, runs, prefix=""):
    jobs = []
    for seed in seeds:
        for method in methods:
            tag = f"{prefix}{method}-{size}-s{seed}"
            jobs.append({"method": method, "seed": seed, "tag": tag, "steps": steps,
                         "done": (Path(runs) / tag / "results.json").is_file()})
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", nargs="+", required=True)
    ap.add_argument("--seeds", nargs="+", type=int, required=True)
    ap.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    ap.add_argument("--size", default="0.8b")
    ap.add_argument("--steps", type=int, default=80)
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--prefix", default="", help="tag prefix, e.g. v2-")
    ap.add_argument("--train", default=None)
    ap.add_argument("--dev", default=None)
    ap.add_argument("--sealed", default=None)
    ap.add_argument("--grpo_steps", type=int, default=None)
    a = ap.parse_args()
    for job in plan(a.methods, a.seeds, a.size, a.steps, a.runs, a.prefix):
        if job["done"]:
            print(f"skip {job['tag']} (already has results)", flush=True)
            continue
        print(f"start {job['tag']}", flush=True)
        extra = EXTRA.get(job["method"], [])
        opt = [x for flag, val in (("--train", a.train), ("--dev", a.dev), ("--sealed", a.sealed), ("--grpo_steps", a.grpo_steps)) if val is not None for x in (flag, str(val))]
        with open(f"{job['tag']}.out.txt", "w") as out, open(f"{job['tag']}.err.txt", "w") as err:
            code = subprocess.call([sys.executable, str(HERE / "train.py"), "--method", job["method"], "--model", a.model, "--runs", a.runs,
                                    "--tag", job["tag"], "--steps", str(job["steps"]), "--seed", str(job["seed"]), *extra, *opt], stdout=out, stderr=err)
        print(f"finish {job['tag']} exit {code}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
