# Training

What we know about Tunza model training, and what we do not. Update when a
run starts, ends, or the opening criteria change.

## The live board

- **Tunza Training Live Board**: https://claude.ai/artifact/WZGgHZji5yxo778XfhboKG
  (claude.ai artifact with a shared database, owned by the training host's
  organization).
- The training host reads every `runs/<tag>/telemetry.jsonl` and pushes one
  document per run into the board's `runs` collection. The board marks a run
  `stale` when nothing has been written for 5 minutes, and `done` when the
  host sets `done`.
- Fields per telemetry point: `step`, `loss`, `lr`, `grad_norm` (before
  clipping), `lora_B_norm`, `tok_per_s`, `tokens_seen`, `examples_seen`,
  `gpu_mem_gb`, `elapsed_s`. Per run: `tag`, `total_steps`, `done`,
  `records_total`, `updated_epoch`.
- Loss is shown as a 20-step moving average on a log scale.

## What the board's design says about the run

- **It is a LoRA fine-tune.** The "LoRA B norm (starts at 0)" panel only
  exists for LoRA adapters, whose B matrix starts at zero. A B norm still at 0
  after many steps means the adapter is not learning.
- **Gradient clipping is on.** Grad norm is logged before clipping.
- This matches the plan: a strong base model plus supervised fine-tuning, no
  from-scratch pretraining (2026-09-10). `evals/BUILD-PROMPT.md` sizes the
  realistic job for one 32 GB card as a 4-bit QLoRA of a 7B to 14B model.

## Not known yet (the board's code does not carry it)

Base model, dataset and its source, LoRA rank and target modules, learning
rate schedule, run count, current loss, and the training script itself. The
training code is not in this repo on any branch as of 2026-10-08. It lives
only on the training host.

## How to read the curves

- Loss should fall and flatten. A spike or NaN means the learning rate is too
  high or a bad batch got in.
- Grad norm spiking above the clip value again and again means unstable
  training.
- LoRA B norm should rise from 0 and level off.
- GPU memory should sit flat under 32 GB. Creeping up means a leak.

## The gate (still closed on paper)

`evals/BUILD-PROMPT.md` section 7 keeps the fine-tune slot `blocked` until a
person writes all five: Evan names Y; Evan names the product
(`household_advice`, `chp_worklist`, or `both_separate`); a named clinician
signs the protocol pack; a data-rights note allows training on the data; a
sealed held-out gold set exists before any weight update. None of these is
recorded in this vault as of 2026-10-08. A run on the board is therefore an
engineering run, not a clinical model, until those exist. Its weights must
not be promoted or shown to users.

## Hardware (2026-10-08, from Evan)

RTX 5090: 32 GB of GPU memory. The PC has 96 GB of system RAM. Use the plan's
32 GB column. Phase 0 still saves the `nvidia-smi` receipt.

## Build plan (2026-10-08)

`specs/tunza-model-build-and-gpu-utilization.html` covers the build and the GPU
plan: a hardware receipt first (an RTX 5090 has 32 GB, a 96 GB card is the
RTX PRO 6000, and the plan branches on which one this is); a pinned Blackwell
stack; MFU and daily busy-percent telemetry; throughput tuning one lever at a
time; a one-GPU job queue; an untuned 4B–12B base-model bake-off on our own
scorecards; and a data pipeline with the gate in code. Clinical SFT runs only
after the five opening criteria are signed, and ships to shadow mode first.

## tunza-adw (2026-10-08)

`tools/tunza-adw/` runs the build plan one phase at a time with seven agents
(scout, planner, builder, tuner, gatekeeper, reviewer, documenter). Python code
owns the order and the verdict: claimed files must equal changed files, every
plan check needs a passing command, read-only seats may not edit, the reviewer
is Codex when installed, and a gated phase stops until people sign
`training/OPENING-CRITERIA.json`. Install on the PC:
`irm https://raw.githubusercontent.com/tunza-labs/Tunza/main/tools/tunza-adw/install.ps1 | iex`.
The red dashboard (`tunza-adw ui`, or the desktop icon) runs workflows on the
left and shows live GPU memory, GPU busy, power and system RAM on the right,
with a verdict on whether the model is using the card fully (target 85–92%).
Verified on a Mac: 21 pipeline tests, and a live toy run where real Claude
seats and a Codex reviewer built, checked, reviewed and committed one phase.
Not yet run on the PC itself.
