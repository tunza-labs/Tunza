# Tunza capability map — wave 1 baseline audit

Dated 2026-10-07. Branch `clinical-contract-wave1` (from `main` @ `2a42af2`).
Status labels: EXISTING / PARTIAL / MISSING / UNSAFE / DUPLICATED / DEPRECATED.
Evidence is file:line in one of two repos:

- **PUBLIC** = `/Users/evanmotovich/code/Tunza` (paths relative to repo root)
- **PRIVATE** = `/Users/evanmotovich/code/medical-triage` (the "clone model" lane)

Code is truth. README claims are reconciled in §17. No PHI, no keys, no
verbatim guideline text appear in this document.

## 0. What the "clone model" actually is

**There are no owned weights, no adapter, no fine-tune artifacts, and no
training dataset in either tree.** The "existing Tunza clone model" is the
PRIVATE lane: a system prompt in front of Anthropic's API
(`app/api/triage/route.ts:28-61`, `:130`). It is a hosted-model integration,
not a clone. Every directive section that assumes an evolvable model
(fine-tuning §19-23, distillation, quantization, champion weights) has no
substrate to act on yet. This is a measured finding, not an opinion.

The PUBLIC app has no model at all: its decisions come from the deterministic
function `decide()` (`lib/assessment.ts:91`), explicitly commented
"**Not clinically validated**" (`lib/assessment.ts:33`).

## 1. Architecture — EXISTING (public), DUPLICATED at product level

- PUBLIC: one Next.js 16 App Router app, React 19, client-side and
  deterministic, no backend beyond three stateless routes
  (`vault/architecture.md`, `package.json:13-17` — runtime deps are only
  next/react/react-dom).
- Three roles on one referral object: household, CHP, facility
  (`lib/types.ts:3` Role; grants enforced in the store reducer).
- PRIVATE: a second, older full app (Next 14 + Supabase + Anthropic + web
  push). Two triage products exist. Wave 1 treats PRIVATE as read-only; any
  merge is a later adapter task (see `vault/wave1-contract.md`).

## 2. Inference paths — EXISTING (public, deterministic) / EXISTING-UNSAFE (private)

- PUBLIC: `decide(answers) → Decision` (`lib/assessment.ts:91`), pure and
  synchronous. Question flow `nextQuestion`/`shouldStopForDecision`
  (`lib/assessment.ts` after `decide`), fixed order `QUESTION_ORDER`
  (`lib/assessment.ts:21`).
- PRIVATE: `app/api/triage/route.ts` — measured gaps, all UNSAFE:
  - model hardcoded `"claude-sonnet-4-5"` (`:130`); only `max_tokens: 1024`
    (`:131`); **no timeout / AbortSignal anywhere in the route**.
  - response `JSON.parse(...) as TriageResponse` — a cast, not runtime
    validation (`:147`).
  - on parse failure it logs the raw model text (`console.error` at `:149`) —
    model output mixed with patient-submitted symptoms is a log-exposure risk.
  - `redFlags` is optional in the type (`lib/types.ts:37`) while the prompt
    demands it always (`route.ts:61`); nothing enforces the contract at
    runtime.
  - persistence is best-effort: insert failure is logged and the response is
    still returned (`:177-182`); inference can finish with no durable record.
  - No deterministic floor sits under the model: nothing stops the private
    lane answering `self-care` in a presentation where the public rules would
    say `go_now`. The two paths are not connected.

## 3. Retrieval paths — MISSING (both repos)

No retrieval, RAG, reranker, evidence bundle, or knowledge-source code exists
in either tree. Nothing to extend; wave 1 only reserves the contract slot
(empty evidence section with explicit `retrieval_status`).

## 4. Datasets — MISSING (both repos)

No training or evaluation datasets exist. The PRIVATE `cases` table
(`supabase/migrations/0001_initial_schema.sql:7-18`) is operational storage of
individual submissions, not a dataset: a case row is not a training example,
carries no label provenance, no review status, and no data-rights basis for
reuse. eCHIS access, where it exists, is not a training license.

## 5. Fine-tuning infrastructure — MISSING

No trainer, no adapter, no dataset writer, no lineage metadata anywhere. The
2026-09-10 "strong base + SFT + locked evals" intent was never executed.
Wave 1 adds **no** training entrypoint (see `vault/wave1-contract.md`).

## 6. Evaluation infrastructure — PARTIAL (public engineering tests only)

- PUBLIC: 7 vitest files (`tests/`): copy parity EN/SW, canonical referral
  lifecycle, per-role locked phrases, component renders in both languages,
  WCAG contrast token parsing, assessment cases, places/facilities, API
  routes. `vitest.config.ts` includes `tests/**/*.test.{ts,tsx}`.
  These are regression tests, not clinical evaluation: no frozen corpora,
  no metric families, no slice reporting, no release gates, no
  champion/challenger.
- PRIVATE: no evaluation code beyond the build.
- MISSING everywhere: the directive's eval families (clinical correctness,
  safety, triage, abstention, grounding, retrieval, multilingual,
  longitudinal, contradiction, medication safety, robustness, security,
  latency, cost).

## 7. Prompts / system instructions — PARTIAL, DUPLICATED vocabulary

- PRIVATE system prompt lives inline in the route (`route.ts:28-61`):
  conservative-escalation instruction (`:34`), vitals handling (`:39`),
  language rule (`:41`), JSON shape with three-level urgency
  `self-care | see-clinic | urgent` (`:59`) and mandatory red flags (`:61`).
- PUBLIC needs no prompt (deterministic), but the **urgency vocabularies
  disagree**: private 3-level enum vs public 4 `DecisionKind`s
  (`lib/types.ts:28-32`). Not the same scale. A disposition mapping table is
  required before the lanes ever meet; wave 1 freezes it inside the contract
  module.

## 8. Patient-context handling — PARTIAL

- PUBLIC: `AssessmentAnswers` = 7 questions, last-write-wins
  (`lib/types.ts:65-80`). No per-field source, timestamp, confidence, or
  provenance; conflicting values overwrite silently. `Encounter`
  (`lib/types.ts:114`) holds one answer snapshot.
- PRIVATE: one submission snapshot per case; `vitals` is a single `jsonb`
  blob (`0001_initial_schema.sql:15`), so a 37.4→39.2 C rise cannot be
  computed from storage. The route builds its prompt from the current request
  only; no longitudinal history is loaded.
- No `PatientState` with append-only events exists anywhere. Wave 1 adds the
  event/state layer, encounter-scoped.

## 9. Persistence / storage — PARTIAL, DUPLICATED

- PUBLIC: browser localStorage `tunza.v2.care` (`lib/store.tsx:33`, read
  `:348`, write `:436`). Device-local, single-state, no event log.
- PRIVATE: Supabase Postgres, 5 migrations (cases, nearby_cases, doctors,
  doctor_notifications, push_subscriptions), own-row RLS.
- Neither is an append-only clinical event store; neither supports
  longitudinal reasoning. Two competing persistence models remain until an
  adapter decision is made (wave 2+, ticketed).

## 10. API boundaries — EXISTING (public), degrade-by-design

- `app/api/access` — worker gate; env codes `CHP_ACCESS_CODE` /
  `FACILITY_ACCESS_CODE`, well-known demo codes otherwise, and GET reports
  demo mode so the UI can say so (`app/api/access/route.ts:8-22,25`).
- `app/api/facilities` — stateless Google Places proxy; receives only the
  coarse geohash cell center, mandatory field mask, key never leaves the
  server, raw provider errors never forwarded (`app/api/facilities/route.ts:8-9,19-24`).
- `app/api/transcribe` — Whisper proxy; 503 when `OPENAI_API_KEY` absent,
  capability probe via GET (`app/api/transcribe/route.ts:10,29-32,41`).
- `.env.example`: every key optional; each route degrades by design.
- PRIVATE: `triage`, `transcribe`, `facilities`, `push-dispatch` routes; the
  triage boundary's gaps are in §2.

## 11. Observability — MISSING (public), UNSAFE (private)

- PUBLIC: none beyond tests; no telemetry, no disagreement records.
- PRIVATE: `console.error` only — including raw model text at
  `route.ts:149` (see §2). No structured telemetry, no version stamps on
  results, no rule/model disagreement capture.
- Wave 1 introduces provenance on every result (`rules_version`,
  `model_id` null on demo path, `knowledge_version` null, `last_sync` null,
  `generated_at`) and disagreement records in the reconciler.

## 12. Safety mechanisms — PARTIAL, with one UNSAFE junction

- PUBLIC floor: conservative demo rules; danger keywords EN/SW
  (`lib/assessment.ts:36-46`), abstention via `need_one_more_answer`
  (`lib/assessment.ts:134,143,195,203`), stop-early on danger
  (`shouldStopForDecision`), on-screen disclaimer copy in both languages.
  Named failure states (`lib/types.ts:20-26`, `lib/failures.ts`) are honest
  UI degrade states.
- UNSAFE junction: the private model path has no floor under it (§2) and no
  output validation; the lanes are unreconciled.
- Keyword rules are bypassable by paraphrase and by any language outside the
  EN/SW patterns. They are a floor, not a clinical protocol. Do not encode
  IMCI/ETAT numeric thresholds in wave 1 — that would fake clinical approval
  (see `vault/wave1-contract.md` deferrals).

## 13. Clinical rules — PARTIAL (demo only, unversioned)

- One unversioned rule set (`lib/assessment.ts` DANGER_PATTERNS + `decide`
  branches). No rule-pack versioning, no effective dates, no clinical review
  trail, no change log. Marked not clinically validated in-file (`:33`) and
  in `vault/backlog.md` ("clinical review required before real use").
- Wave 1 adds `rules_version` provenance and a reconciler that makes the
  floor non-downgradable; it does **not** author new clinical content.

## 14. Model / version management — MISSING

- PRIVATE: hardcoded model string (`route.ts:130`); no registry, no
  champion/challenger, no reproducibility metadata (base model, adapter,
  data versions, config).
- PUBLIC: nothing to manage yet.
- Wave 1 lays the provenance fields; registries are wave 2+.

## 15. Authentication / authorization boundaries — PARTIAL

- PUBLIC: worker gate is a placeholder for real identity — demo codes until
  env set (`app/api/access/route.ts`), grants held in client state,
  enforced in the reducer; "Start over" clears grants.
- PRIVATE: anonymous Supabase sessions; middleware refreshes cookies and
  **fails open** (passthrough) if Supabase is unconfigured
  (`middleware.ts:4-12`) — deliberate availability choice, acceptable only
  because persistence, not clinical access, hangs off it.
- No clinician credential verification exists in either tree (README's
  "verified-clinician workflows" is not code; see §17).

## 16. Duplicated / competing primitives

| Primitive | PUBLIC | PRIVATE | Disposition |
|---|---|---|---|
| Triage decision | `decide()` 4 kinds (`lib/types.ts:28-32`) | prompt 3 levels (`route.ts:59`) | freeze disposition table in wave-1 contract; adapter maps private onto it |
| Persistence | localStorage `tunza.v2.care` | Supabase `cases` | keep separate this wave; event-store design must fit both later |
| i18n | `lib/copy.ts` typed EN/SW (`:362,691`) | `lib/i18n.ts` | PUBLIC table is authoritative pattern; missing SW string is a compile error |
| Facility data | demo list (`lib/facilities.ts:3-4` "Clearly fake") + Places nearby | Places port (origin of the pattern) | nearby = Places via location-blind proxy; referral stays demo until capability truth exists |
| Voice | degrade chain server→on-device→type | server Whisper | PUBLIC chain is authoritative |

Nothing is DEPRECATED in the public tree. The private lane as a whole is a
deprecated-in-waiting surface: it is the adapter target, not the trunk.

## 17. README claims vs code (reconciliation)

Imported from the fusion-harness fact sheet
(`prompts/tunza-vision-2026-09-23/fact-sheet.md`, verified against this tree)
and re-verified here. The public README's "What exists today" list includes
capabilities the public code does not have; several describe the private lane
or intent:

- Optional vitals: no `vitals` match in public `*.ts/tsx` — MISSING in public
  (private has the jsonb blob only).
- Case history for signed-in users, community case signals, outbreak signal,
  verified-clinician workflows, clinician notifications, web push, PWA: all
  README bullets without public-code support (`vault/backlog.md` lists them
  as backlog).
- Image input is a boolean attachment; the rules do not read the image.
- Referral uses demo facilities, not live Places results.
- The deterministic safety layer replacing the demo rules is backlog, with
  clinical review required.

Rule for wave 1 and beyond: **code is truth**; the README is intent. The
capability map, not the README, is the baseline future waves are measured
against.

## 18. Hygiene observations (no action this wave)

- PRIVATE contains a stray accidental file named
  `.env.local moto@Evans-MacBook-Pro medical-triage % nano .env.local`
  (a pasted shell command that became a filename). Not read, not touched.
  Delete it in the adapter wave; it must never be committed anywhere.
- No PHI or credentials were read or copied during this audit. `.env.local`
  files in both repos were not opened.
