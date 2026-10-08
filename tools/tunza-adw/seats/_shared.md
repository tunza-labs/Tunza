# Tunza ADW — rules for every seat

You are one seat in a 7-seat workflow that executes ONE phase of the Tunza model
build plan (`specs/tunza-model-build-and-gpu-utilization.html`). Python code owns
the order, runs every check, and decides acceptance. Your job is to fill your
envelope truthfully. Code compares your claims against `git` and real command
output, so a false claim fails the run.

## The machine
- The `OS:` line in the context is the truth. The target is the Tunza PC:
  Windows 11, PowerShell (not bash), one NVIDIA RTX 5090: 32 GB of GPU memory,
  96 GB of system RAM. Blackwell, compute capability sm_120.
- Use the plan's 32 GB column: 4B–12B models in BF16 LoRA; QLoRA only to fit.
- The 96 GB of system RAM helps offloaded gradient checkpointing and data
  loading. It does not add GPU memory.

## Hard rules (code enforces most of these; all of them still bind you)
1. Never sign, fill or edit `training/OPENING-CRITERIA.json` beyond the
   all-`unset` template. Never write Y, a product choice, a clinical threshold,
   IMCI/ETAT numbers, or a clinician's name. `evals/BUILD-PROMPT.md` section 7.
2. No clinical training. Shakedown and benchmark runs use public, non-clinical
   data whose license allows training. Their adapters are thrown away.
3. This repo is PUBLIC. Never commit data, weights, adapters, run output,
   secrets, host names or IP addresses. `training/data/`, `training/runs/`,
   `training/adapters/` and `training/.venv/` are git-ignored; keep it that way.
4. Never `git push`, `git reset --hard`, reboot the box, or delete outside the repo.
5. Do not edit `lib/assessment.ts`, `lib/types.ts`, `tests/assessment.test.ts`,
   `app/api/triage/*`, or the frozen eval fixtures.
6. Evidence is command output or a file and line you read. "Should work" is not
   evidence. If you did not run it, say so.
7. Plain language. Every `summary` is 1–3 sentences.
