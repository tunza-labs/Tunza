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


def plan(methods, seeds, size, steps, runs):
    jobs = []
    for seed in seeds:
        for method in methods:
            tag = f"{method}-{size}-s{seed}"
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
    a = ap.parse_args()
    for job in plan(a.methods, a.seeds, a.size, a.steps, a.runs):
        if job["done"]:
            print(f"skip {job['tag']} (already has results)", flush=True)
            continue
        print(f"start {job['tag']}", flush=True)
        with open(f"{job['tag']}.out.txt", "w") as out, open(f"{job['tag']}.err.txt", "w") as err:
            code = subprocess.call([sys.executable, str(HERE / "train.py"), "--method", job["method"], "--model", a.model, "--runs", a.runs,
                                    "--tag", job["tag"], "--steps", str(job["steps"]), "--seed", str(job["seed"])], stdout=out, stderr=err)
        print(f"finish {job['tag']} exit {code}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
