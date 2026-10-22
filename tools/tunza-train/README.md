# tunza-train

Engineering shakedown only. Data is synthetic and not clinical. No run is promoted. Labels come from `decide()` in the Tunza app (`lib/assessment.ts`). Nothing in this folder uses Jev for labels, rewards, filtering, ranking or checkpoint choice.

## Files

| File | Purpose |
|---|---|
| `train.py` | One run: train, score the dev set, write the run folder. |
| `run_queue.py` | Runs `train.py` for each method and seed. Skips finished runs. |
| `methods.py` | ORPO and DPO losses, rule-built rejected answers, T7 RL gate. |
| `evaluate.py` | Grades model output with the reward and computes metrics. |
| `eval_adapter.py` | Scores a saved adapter or full fine-tune on one file, such as the sealed set. |
| `mlx_run.py` | SFT on Apple Silicon with `mlx_lm`. |
| `results_table.py` | Prints dev, sealed and per-family private tables from `runs/`. |
| `live.py` | Read-only page for plan, runs, queue, loss curves and hardware. |
| `danger_patterns.py` | The app's danger regexes, shared by the three tools below. A test checks them against `lib/assessment.ts`. |
| `keyword_report.py` | Missed danger rows per keyword family per run, from `runs/*/private-v2.json`. |
| `keyword_coverage.py` | Training rows per danger keyword alternative. Exits 1 below 15 rows. |
| `negation_check.py` | Danger keywords inside a negation, with the regex verdict against the file label. |
| `leakage_check.py` | Nearest training story and identical structure for each test row. |
| `run_tests.py` | Runs every test file without pytest. |
| `reward/tunza_reward.py` | Reward v2. |
| `gen_cases.py` | Generates `data/v2` and `data/v3`. |
| `build_data.py` | Builds the v1 files from the frozen sft-v1.1 files. |
| `m1_setup.sh` | Apple Silicon setup. Clones the repo and starts one SFT run. |
| `plan-status.json` | Phase names and checkbox counts for `live.py`. |

## Data

| Version | Folder | Train | Sealed | Built by |
|---|---|---|---|---|
| v1 | `data/` | `triage-train.jsonl`, 300 rows | none | `build_data.py` |
| v2 | `data/v2/` | 3000 rows | 450 rows | `gen_cases.py`, generator sha256 `bb5bc3...` |
| v3 | `data/v3/` | 3000 rows | 450 rows, same bytes as v2 | `gen_cases.py`, generator sha256 `60798c...` |

- Dev set: `data/triage-dev.jsonl`, 96 rows. `train.py` and `mlx_run.py` use it by default. `eval_adapter.py` scores only the `--file` it is given.
- v2 and v3 train: go_now 990, get_care_today 720, monitor_at_home 750, need_one_more_answer 540. Languages `en`, `sw` and `cs` (code-switch), 1000 each.
- Sealed: go_now 150, get_care_today 102, monitor_at_home 102, need_one_more_answer 96. 150 per language.
- v2 and v3 contain no `escalate` or `abstain` rows.
- `data/v2/triage-sealed.jsonl` is public and not sealed. `data/v2/README.md` says never train on it. The private test set lives outside this repo.
- `data/manifest.json` describes v1 only. Its note predates `data/v2` and `data/v3`.

Regenerate v3:

```
python tools/tunza-train/gen_cases.py --seed 20261018 --out tools/tunza-train/data/v3
```

- Needs Node and a local esbuild. It reads `lib/assessment.ts` from the repo root.
- The current `gen_cases.py` (sha256 `60798c...`) is the v3 generator. v2 came from revision `bb5bc3...` and does not come out of today's file.
- `gen_cases.py` writes text with the platform line ending. The manifest hashes LF files, so on Windows the output hashes differ.
- The default `--out` is `data/v2`. Running without `--out` overwrites v2.
- The manifest `command` field always reads `--out tools/tunza-train/data/v2`, even when `--out` differs.
- `decide_bundle_sha256` hashes a bundle whose entry holds the absolute path of `assessment.ts`, so it changes with the checkout path. Compare `assessment_ts_sha256` across machines instead.

## Reward v2

`reward/tunza_reward.py` sets `REWARD_VERSION = 2`. Each result records `reward_version`. Results without the field used v1. Do not compare mean reward across versions. `danger_missed` is comparable across versions.

The model must return one JSON object with exactly `disposition`, `danger_facts` and `follow_up_question`. The disposition is one of: go_now, get_care_today, monitor_at_home, need_one_more_answer, escalate, abstain.

`score()` applies these steps in order:

1. Format. Output that is not one strict JSON object scores -1.0.
2. Danger floor. For an expected go_now or escalate, a raw disposition below rank 40 scores -1.0 (`danger_under_triage`). The raw answer is graded. `reconcile()` is only logged.
3. Core score. Exact match scores 1.0. Another rank-40 answer for a danger case scores 0.8. Other pairs use the table in `_core_score()`.
4. Penalties.
   - A follow-up question on an answer other than need_one_more_answer, or an invalid question on it, costs -0.2.
   - Empty `danger_facts` on a danger case costs -0.3.
   - Any ungrounded danger fact costs -0.2, once. A fact is grounded when it is 3+ characters and appears as a whole word or phrase in the story, or equals a `field=value` pair from the intake.
5. The total is clipped to [-1.0, 1.0].

`evaluate.evaluate()` returns: `n`, `reward_version`, `mean_reward`, `valid_json_rate`, `danger_cases`, `danger_missed`, `danger_miss_rate`, `confusion`, `rows` and `by_language`. The callers (`train.py`, `mlx_run.py`, `eval_adapter.py`) add `constant_baselines`. `results.json` keeps `rows`. The sealed block drops it. `danger_missed` counts danger cases that were under-triaged or had no parsable disposition. A row without a language field uses its story marker, then a word-list guess.

## Methods

`train.py --method`:

| Method | Training signal |
|---|---|
| `base` | None. Scores the untuned model. |
| `sft` | Every row, equal weight. |
| `sft_cost` | Every row, weighted by urgency rank. Mean weight is 1. |
| `orpo` | Correct answer over a rule-built wrong answer. No reference model. |
| `dpo` | Correct answer over a rule-built wrong answer, against the model with the adapter off. Adds an NLL term. |
| `sft_grpo` | SFT, then GRPO on the reward. Blocked unless the SFT checkpoint's mean reward beats always-go_now (T7). |
| `sft_rloo` | SFT, then RLOO: the reward minus the leave-one-out mean of its group. Same T7 gate. |
| `sft_ppo` | SFT, then clipped PPO over each sampled batch. Same T7 gate. |

- `--full` trains every weight. It needs a 24 GB+ GPU.
- `--ppo_epochs` (default 2) and `--clip` (default 0.2) apply to `sft_ppo` only. `--attn flash2` asks for FlashAttention-2 and needs `flash_attn` installed. The default is off.
- The T7 gate looks for `runs/{prefix}sft-{size}-s{seed}/results.json`, then `runs/{prefix}lora-sft-{size}-s{seed}/results.json`. `size` comes from `--model`, and `prefix` is the part of the tag before the method name. An RL run whose tag does not contain the method name gets an empty prefix.
- `mlx_run.py` runs SFT only.
- Defaults: LoRA rank 16, alpha 32, lr 2e-4, 60 steps, batch 4, accumulation 4, max length 768. Model `Qwen/Qwen3.5-0.8B`.
- `run_queue.py` overrides ORPO to batch 1, accumulation 16, lr 1e-4. DPO uses lr 5e-5.
- Not implemented: `rft`, `kto`, `gspo`, `grpo` and `sft_full` appear in the `live.py` method list, but `train.py` does not accept them. `methods.rl_gate` has a `grpo` branch that `train.py` cannot reach.

## Run a queue

```
python tools/tunza-train/run_queue.py --methods sft sft_cost --seeds 0 1 2 --steps 80 --train tools/tunza-train/data/v3/triage-train.jsonl
```

- Pass `--train` explicitly. If omitted, `train.py` uses `data/triage-train.jsonl` (v1, 300 rows).
- Order: seed outer loop, method inner loop.
- Tag: `{prefix}{method}-{size}-s{seed}`. `--size` (default `0.8b`) fills the tag. Set it to match `--model`.
- A job is skipped when `runs/<tag>/results.json` exists. Re-run the same command to resume.
- A failed job does not stop the queue. Output goes to `<tag>.out.txt` and `<tag>.err.txt` in the current folder.
- `--sealed` scores the sealed file after each run. It is slow.

Each run folder holds `meta.json`, `telemetry.jsonl`, `layerstats.json`, `results.json` and `adapter/`. A `--method base` run writes only `meta.json`, `telemetry.jsonl` and `results.json`. The live page then shows placeholder rows in the layer panel.

Score a saved adapter on the sealed file:

```
python tools/tunza-train/eval_adapter.py --adapter runs/<tag>/adapter --file tools/tunza-train/data/v3/triage-sealed.jsonl --out runs/<tag>/sealed.json
```

- Without `--model`, the CPU/MPS path uses the base recorded in `adapter_config.json`. A folder without it is a full fine-tune and loads as a model. A folder with neither `adapter_config.json` nor `config.json` is an error.
- On CUDA, unsloth loads the folder itself, so `--model` is ignored there. A conflicting `--model` prints a warning.
- The output records the base the scores came from under `base`.

Print the tables:

```
python tools/tunza-train/results_table.py --runs runs
```

`results_table.py` reads `results.json` and `sealed.json`. It does not read the `sealed` key that `train.py --sealed` writes into `results.json`. Use `eval_adapter.py` for the sealed table.

The third table groups runs by family (tag prefix `v2`, `v3`), method, size and mode, with the mean and range of `private-v2.json` reward and danger missed. `runs` counts every folder in the group, `private runs` the folders the mean is taken over, and `private seeds` their distinct seeds. A scored folder without a method is listed under `?`. Sweep variants with the same four keys are pooled into one row.

## Live page

```
python tools/tunza-train/live.py --runs runs --port 8790
```

Open http://127.0.0.1:8790. The page is read-only. If the GPU cannot be read, the hardware panel shows "GPU: no reading" and the error appears in the status line. On Windows a failed `nvidia-smi` falls back to a driver reading, with the error in its driver field.

The Queue panel counts run folders by method and state (done, running, queued, stalled, failed). Jobs the supervisor has not reached have no folder and are not shown. It reads tags launched, attempts and retries from `supervisor.log` next to `--runs` (UTF-16 or UTF-8). `--log` sets another path. A `training=<n>` reading older than 10 minutes is marked stale.

`live.py` lists `sft_rloo` and `sft_ppo` only in the Queue panel. The method grid and loss legend do not have them.

## Data checks

All read-only. Outputs that quote private stories have no default path inside the repo.

```
python tools/tunza-train/keyword_coverage.py --train tools/tunza-train/data/v3/triage-train.jsonl
python tools/tunza-train/keyword_report.py --out <outside the repo>/keyword_report.md
python tools/tunza-train/negation_check.py --out <outside the repo>/negation_table.md
python tools/tunza-train/leakage_check.py --train tools/tunza-train/data/v3/triage-train.jsonl --test <test.jsonl>
```

## Danger rules

These are the Tunza app's `DANGER_PATTERNS` in `lib/assessment.ts`, copied in `danger_patterns.py`. They match lowercased text. The app describes them as demonstration rules that are not clinically validated.

| Sign | Pattern |
|---|---|
| Not waking | `unconscious\|not waking\|won'?t wake\|hajitambui\|haamki` |
| Seizure | `seizure\|convulsion\|fitting\|kifafa\|degedege` |
| Not breathing | `not breathing\|stopped breathing\|hapumui` |
| Blue lips | `blue lips\|blue face\|midomo ya bluu` |
| Heavy bleeding | `bleeding (a lot\|heavily\|won'?t stop)\|heavy bleeding\|damu nyingi` |

`won'?t` matches both "won't" and "wont". The model prompt (`evaluate.SYSTEM`) tells the model never to choose lower urgency when a danger sign is present. The danger floor in the reward enforces it.

## Setup on Apple Silicon

`m1_setup.sh` clones `tunza-labs/Tunza` (branch `train/choice-model-live`) into `~/code/tunza-train`, builds `.venv-train`, runs the tests, opens the live page and starts one run. It stops under 12 GB of RAM unless `FORCE=1`. Environment variables: `METHOD`, `STEPS` (80), `SEED`, `BATCH` (1), `ACCUM` (16) and `TAG`.

## Tests

`python tools/tunza-train/run_tests.py` runs every test file, unittest and pytest style, without pytest. Add words to run only matching files, for example `run_tests.py test_live`.

- It hides the GPU from torch and stubs `live.gpu_info`, so no test queries the card.
- The reward tests read `lib/clinical/` and `test_gen_cases.py` bundles `lib/assessment.ts` from the repo root. Set `TUNZA_REPO` when this folder is not at `<repo>/tools/tunza-train`. `ESBUILD` sets the esbuild binary.
- `test_gen_cases.py` needs Node and esbuild. Its determinism test compares against `data/v2`, which the current generator no longer reproduces, so that test fails.
- `python -m unittest test_x` runs only unittest classes. The pytest-style files (`test_train`, `test_methods`, `test_evaluate`, `test_live`, `test_gen_cases`, `reward/test_tunza_reward` partly) need `run_tests.py` or pytest.
