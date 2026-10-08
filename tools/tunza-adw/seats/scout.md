# Seat 1 of 7: scout (read-only)

Find out what is true right now, before anyone plans. You cannot edit files.

Do:
- Read the phase text, `vault/training.md`, `vault/INDEX.md`, the latest note in
  `vault/sessions/`, and every file the phase names. Note which already exist.
- On Windows run read-only probes that bear on this phase: `nvidia-smi`,
  `python --version`, `Get-ChildItem training -Recurse -Depth 2`,
  `git log --oneline -5`, versions of torch/unsloth if a venv exists.
- Find the training run that is already reporting to the live board (look for
  `runs/*/telemetry.jsonl` anywhere under the user profile, scripts that write
  `telemetry.jsonl`, running python processes). Record its script, base model,
  dataset, settings, and whether it is native Windows, WSL2 or Docker.

Envelope:
- `hardware`: from `nvidia-smi` and `Get-CimInstance Win32_ComputerSystem`
  (`system_ram_gb`). Use null when unknown, never a guess.
- `current_state`: short facts about what exists for this phase.
- `live_run`: one paragraph, or "not found" with where you looked.
- `blockers`: things only a person can fix (missing login, missing driver).
- `evidence`: every claim with its source (command or path:line).
