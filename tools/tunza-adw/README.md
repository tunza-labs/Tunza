# tunza-adw

A 7-agent workflow that executes the model build plan,
`specs/tunza-model-build-and-gpu-utilization.html`, one phase at a time on the
Tunza PC (Windows, RTX 5090 with 32 GB of GPU memory, 96 GB of system RAM).

## Install on the Tunza PC (one line)

Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/tunza-labs/Tunza/main/tools/tunza-adw/install.ps1 | iex
```

It installs uv and the native Claude Code CLI if they are missing, finds or
clones the Tunza checkout, adds a `tunza-adw` command and a **Tunza ADW**
desktop icon, then runs `tunza-adw doctor`. If Claude Code is new on the
machine, run `claude` once and log in.

## Prove it works on this machine

Press **Self-test** in the dashboard (or run `tunza-adw selftest`). It builds a
throwaway repo with a one-step toy phase and runs it through all seven agents
on this PC: real Claude seats, Codex as reviewer, the PowerShell checks, the GPU
reading, the commit. It costs about $0.05 to $0.10 and ends with
`SELF-TEST PASSED` and a table of every seat's engine, model, tokens, tool calls
and cost. Run it before the first real phase and after any change to the box.

## Use it

Double-click **Tunza ADW** on the desktop (or run `tunza-adw ui`). The red
dashboard opens at `http://127.0.0.1:8787`:

- **Top:** the run, its status and the current step, total tokens in (and how
  many were cached), tokens out, tool calls, cost and elapsed time.
- **Left:** Self-test, run the next phase / one phase / all; the **step by step**
  list of every code check and agent with its tools, tokens, cost and time;
  the plan's phase markers.
- **Middle:** the selected agent, followed live: its model, its exact tool list,
  token and cost tiles, its **system prompt**, its **task prompt**, its final
  **envelope**, and every tool call as it happens with the input it sent and
  the output it got back. Code steps show each validation command with its
  exit code and output.
- **Right:** live GPU memory used by the model against the 32 GB card, with
  the 85–92% target band, GPU busy %, power, clocks, system RAM, a 10-minute
  history, and a one-line verdict on whether the model uses the card fully.

Terminal: `tunza-adw status`, `tunza-adw run --next`, `tunza-adw run --phase 3`,
`tunza-adw run --all`, `--dry-run` to see the steps without calling a model,
`--push` to push the `adw/` branch once a phase is accepted.

## How each agent runs

Every seat is a fresh headless session with its own system prompt
(`seats/_shared.md` + `seats/<seat>.md`), exactly the tools listed for it in
`config.json`, no MCP servers, and no user hooks or plugins, so nothing else
installed on the machine leaks into its context. Its events stream into
`.tunza-adw/runs/<run>/events.jsonl` (one line per tool call, result, message
and token update), next to `<seat>.system.md`, `<seat>.prompt.md`,
`<seat>.json` (the envelope) and `receipt.json` (steps, totals, cost).

## How a phase runs

Python code owns the order and the verdict. Agents fill typed envelopes, and
code checks every claim against `git` and real command output.

| Step | Who | What |
|---|---|---|
| preflight | code | `nvidia-smi` receipt, clinical gate state, branch |
| gate | code | A gated phase (clinical SFT) stops here unless people signed `training/OPENING-CRITERIA.json` |
| 1 scout | agent, read-only | What exists now, the hardware, the run already on the board |
| 2 planner | agent | Steps, plus commands that prove every plan check (code rejects gaps) |
| 3 builder | agent | Implements; repairs from verbatim failures, at most 3 rounds |
| diff + tests | code | Claimed files must equal changed files; no data, weights or secrets; every validation command must pass |
| 4 tuner | agent, GPU phases | Measures tok/s, MFU, GPU busy, memory; may tune configs only |
| 5 gatekeeper | agent, read-only | Clinical gate, public-repo hygiene, protected files |
| 6 reviewer | agent, read-only | Codex if installed (a second model family), else Claude; checks each plan item against evidence |
| accept | code | Tests green AND gatekeeper pass AND reviewer approved |
| 7 documenter | agent | `vault/training.md` and a session note; code sets the plan markers |
| commit | code | Local commit on the `adw/` branch; push only with `--push` |

Read-only seats that edit a file fail the run. Each phase has a dollar budget
(`config.json`, default $40), and every run writes a receipt to
`.tunza-adw/runs/<id>/receipt.json`.

## What it will not do

Sign or fill the opening criteria, write clinical labels or thresholds, train
on clinical data before the gate opens, commit data, weights or run output to
this public repo, `git push` without `--push`, or reboot the box.

## Tests

```
uv run --with pytest python -m pytest tools/tunza-adw/tests -q
```

The tests run the whole pipeline in a throwaway repo with stand-in agents and
check the live trace, the Claude and Codex event parsers,
the happy path, the gate, read-only violations, false file claims, the repair
limit, uncovered plan checks, reviewer and documenter refusals, the budget,
and the tuner's file limits.
