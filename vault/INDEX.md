# Tunza Vault

The project's second brain. Every Claude Code session reads this at start (a
SessionStart hook prints this index and the latest session note) and writes
back before finishing meaningful work. Pages are short, dated, and factual —
a wiki, not a diary.

## Protocol

- **Read**: this index arrives automatically; open the pages your task touches.
- **Write**: before ending a session that changed anything, (1) update the
  affected pages below, and (2) add a dated note to `vault/sessions/`.
- **Never store**: secrets, credentials, patient data, or personal data.

## Map

| Page | What it holds |
|---|---|
| [product.md](product.md) | The one idea, the three surfaces, the four verdicts |
| [design-system.md](design-system.md) | Tokens, the two-red discipline, type scale, research anchors |
| [architecture.md](architecture.md) | Modules, the referral machine, the copy layer, quality gates |
| [decisions.md](decisions.md) | Dated decision log, with the why |
| [backlog.md](backlog.md) | What's next, including ports from the old app |
| [capability-map.md](capability-map.md) | 16-axis audit of the public app and the private prompt lane |
| [wave1-contract.md](wave1-contract.md) | Wave-1 boundary, deferrals, and file ownership |
| [wave1-handoff.md](wave1-handoff.md) | Host-recovery receipts. Not a release. |
| [training.md](training.md) | Live training board, what a run is, how to read it, the training gate |
| [wave2-ledger.md](wave2-ledger.md) | Deferred work and the evidence required to open it |
| [workflows/2026-10-06-receipt.md](workflows/2026-10-06-receipt.md) | Actionable closeout for the 2026-10-06 agent-run receipt. Not a release. |
| [tickets/medical-triage-adapter.md](tickets/medical-triage-adapter.md) | Private-lane hardening ticket. Route not edited. |
| [claims/](claims/) | One file per active claim: which machine is on which task and paths |
| [sessions/](sessions/) | One dated note per working session |

## Current state (update when it changes)

- **2026-10-08:** `tools/tunza-adw/` runs the model build plan
  (`specs/tunza-model-build-and-gpu-utilization.html`) with seven agents and a
  red dashboard (workflows left, GPU memory and RAM right). Install on the PC:
  `irm https://raw.githubusercontent.com/tunza-labs/Tunza/main/tools/tunza-adw/install.ps1 | iex`.
  The box is an RTX 5090 (32 GB GPU memory) with 96 GB system RAM. Clinical
  training stays behind `training/OPENING-CRITERIA.json`. See `training.md`.

- **2026-10-07:** wave 1 merged to `main` (PR #8, `d3d8f84`). Five machines
  now work the repo at once through the tunza-crew mod (`tools/tunza-crew/`,
  install steps in its README) and the live crew board:
  https://claude.ai/artifact/Y4vxmNKpfqB7RPfrMfDAuC . Claim before editing;
  `.gitattributes` keeps LF so Windows checkouts pass the frozen eval hash.

- **2026-10-06:** branch `clinical-contract-wave1` holds an engineering
  contract around the existing demo floor. Host recovery wrote the remaining
  modules in the working tree and did not commit or push. Gates were green
  in that tree. This is not a clinical approval and not a model release.
  Read `wave1-handoff.md` before treating any label as reviewed.
- **Everything is merged to `main`** (through PR #5, 2026-08-27): prototype
  one (three surfaces, EN/SW, matte red finish, full-red home from the old
  app), the vault + SessionStart hook, and the voice/facility ports
  (`/api/transcribe`, `/api/facilities`, designed fallbacks). 84 tests, four
  green gates.
- Interactive walkthrough artifact (source archived at
  `docs/walkthrough.html`; opens on the English red home every load):
  https://claude.ai/code/artifact/8f8aa136-5685-4cc5-ab82-08b0e229d2ff
- The earlier production app lives in `evanmotovich1-web/medical-triage`
  (private) — the source for ports; read-only. This repo is public unless
  Evan flips it private (Settings → Danger Zone).
