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
| [wave2-ledger.md](wave2-ledger.md) | Deferred work and the evidence required to open it |
| [workflows/2026-10-06-receipt.md](workflows/2026-10-06-receipt.md) | Actionable closeout for the 2026-10-06 agent-run receipt. Not a release. |
| [tickets/medical-triage-adapter.md](tickets/medical-triage-adapter.md) | Private-lane hardening ticket. Route not edited. |
| [sessions/](sessions/) | One dated note per working session |

## Current state (update when it changes)

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
