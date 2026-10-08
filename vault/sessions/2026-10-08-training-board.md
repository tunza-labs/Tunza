# 2026-10-08 — training board read (machine: evan-mac)

## Changed

- `vault/training.md`: new page for the live training board, what the run
  is, how to read the curves, and the training gate.
- `vault/INDEX.md`: map row for it.

## Verified

- Board code read in full. It is a LoRA fine-tune dashboard fed from
  `runs/<tag>/telemetry.jsonl`.
- No training code on any branch of this repo (`git grep` for LoRA, peft and
  telemetry across all branches, 2026-10-08).

## Not verified

- Live numbers. The board's data is blocked from this Mac: the owning
  organization does not let Claude Code read artifact data, even for an
  editor. Chrome screen capture also failed here.

## Next

- From the training host: add the base model, dataset, LoRA settings and the
  training script path to `vault/training.md`.
