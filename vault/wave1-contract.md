# Wave 1 contract — clinical contract spine

Dated 2026-10-07. Branch `clinical-contract-wave1` (from `main` @ `2a42af2`).
This document is the agreement every wave-1 task works under. The audit that
justifies it is `vault/capability-map.md`.

## 1. Repository and branch decision

- All wave-1 work lands in **`/Users/evanmotovich/code/Tunza`** on branch
  **`clinical-contract-wave1`**. This repo owns the real gates
  (`npx tsc --noEmit`, `npm test`, `npm run lint`, `npm run build`) and the
  authoritative types, copy table, and referral lifecycle.
- **Nothing lands in `fusion-harness`.** Its tree is blocked-dirty
  (2,512 paths) and it is a harness, not a runtime. Its dirty paths
  (`adws/**`, `duckdb20_fusion_lab/lab.sql`, `extensions/self-compact/**`)
  are never touched.
- **`medical-triage` is read-only this wave.** Its route, prompt, schema, and
  env stay untouched. Hardening it is a written ticket
  (task 2.d → `vault/tickets/medical-triage-adapter.md`), not a drive-by.
- Local commits on the branch are allowed. **No push, no merge, no
  rebase, no force updates.** Publication is parent-owned and requires an
  exact-SHA harness receipt.

## 2. Wave-1 scope (what ships)

One vertical slice, no model, no corpus, no training:

1. **Contract module** `lib/clinical/contract.ts` (task 1.a, grok):
   runtime-validated `ClinicalAssessment` with ten sections — observed
   facts, retrieved evidence (empty, explicit `retrieval_status`,
   `trust_tier: "none"`), derived features, hypotheses, uncertainties,
   contradictions, required information, red flags, next action, provenance.
   Provenance on every result: `rules_version`, `model_id` (null on the
   demo path), `knowledge_version` (null), `last_sync` (null),
   `generated_at`. Append-only `ClinicalEvent`. `Contradiction` as a
   first-class, never-auto-resolved object. Disposition = the existing four
   `DecisionKind` values plus `escalate` and `abstain`, one mapping table;
   `need_one_more_answer` stays the missing-info ASK state; **no new
   user-visible headline**. Hand-rolled validators; **no new dependencies**.
   A fixture missing any section must fail validation.
2. **Eval harness v0** `evals/` (task 1.b, terra): manifest with content
   hashes and SYNTHETIC lineage tags; human-authored expected labels
   (never derived from `decide()`); runs under the existing vitest gate,
   offline, deterministic. Families measurable now: red-flag recall of
   `decide()`, abstention on incomplete cases, non-downgrade. Families not
   measurable now (clinical correctness, calibration, retrieval,
   multilingual generation, medication safety) emit explicit
   `not_measurable`. **No aggregate score field anywhere.** The frozen
   baseline table for current `decide()` is captured before any behavior
   change.
3. **Append-only patient state** `lib/clinical/state.ts` (task 2.a, terra):
   projection from `Encounter`/`AssessmentAnswers` into `ClinicalEvent`s;
   a new temperature never erases the previous one; unit normalization;
   missingness vs unknown; same-type conflicts become unresolved
   `Contradiction`s; a deterministic trend function producing structural
   deltas only ("increased over N hours", "three declining readings") with
   **no clinical cutoffs and no disposition effect**. Encounter-scoped;
   `lib/store.tsx` persistence is not replaced.
4. **Reconciler** `lib/clinical/reconcile.ts` (task 2.b, grok):
   `decide()` result (the floor) + optional candidate (nullable `model_id`)
   → reconciled disposition + disagreement record. Safer approved path wins;
   a candidate below the floor is rewritten up and the disagreement becomes
   telemetry, never a silent merge. Reconciliation failure must never fail
   open into a downgrade; persistence/telemetry failure must not block the
   safer user answer.
5. **Adversarial fixtures + release gates** `evals/adversarial/`,
   `evals/gates.ts` (task 2.c, sol): look-alikes, paraphrase bypasses,
   Kiswahili colloquial/misspelling/code-switching, prompt-injection strings
   as inert tagged data. Fail-closed gate machinery: red-flag recall ≥
   recorded baseline, no safety-critical slice regression, disposition
   distribution reported; any missing metric blocks promotion. Extends
   1.b's manifest format, never forks it.
6. **Wiring** `lib/clinical/pipeline.ts` (task 3.a, grok): `decide()` →
   reconciler → contract, fed by the state projection. Renderer maps
   sections to existing copy keys via `t()`; EN+SW parity stays
   compile-enforced (a missing Kiswahili string fails the build). Internal
   sections never collapse into one generated paragraph.
   `tests/assessment.test.ts` stays unchanged and green.
7. **Docs** (tasks 2.d and 4.a, glm): the private-lane adapter ticket, the
   wave-2 deferral ledger, and the final handoff with receipts.

## 3. Deferrals — written, not silent

Each deferral names its opening criterion. None of this work starts in
wave 1:

- **No training / SFT / QLoRA / distillation / quantization.** No measured
  failure exists to fix; there is no label provenance (`Y` is undefined),
  no dataset, no data-rights basis, and no fine-tuning substrate
  (capability-map §0, §4, §5). Opens only on: a written failure analysis
  citing eval-report numbers, a named label producer, and a documented
  data-rights basis.
- **No retrieval ingestion.** No approved knowledge sources exist; there is
  nothing with jurisdiction, version, effective date, or trust tier to
  ingest. The contract reserves the empty evidence slot with
  `retrieval_status`. Opens when named approved sources with metadata exist.
- **No guideline thresholds, no IMCI/ETAT encoding.** The keyword rules are
  a floor, not a protocol. Encoding numeric clinical thresholds without a
  named clinician approving a versioned rule pack would fake clinical
  approval. Opens on a documented clinical review process.
- **No JEV reimplementation.** External hosted decision model, absent from
  this tree; not a Tunza primitive.
- **`medical-triage/` untouched.** Adapter work is ticket 2.d. Its UNSAFE
  findings (capability-map §2) are recorded, not yet fixed there.
- **PatientState stays encounter-scoped.** No cross-encounter persistence
  until the README's privacy projections (cases vs case_signals) exist;
  a richer persisted state would expand PHI exposure in localStorage.

## 4. Hygiene rules (all tasks, no exceptions)

- No PHI in code, fixtures, docs, or logs. No `.env` contents read or
  committed. Keys only ever via env.
- No verbatim guideline text vendored anywhere.
- Fixtures are tagged SYNTHETIC and are engineering fixtures — never
  described as a training set. Same-model self-grading is forbidden.
- No language anywhere claims clinical approval or validation of the
  rules or the system. The demo floor keeps its not-clinically-validated
  label; demo facilities stay labeled demo.
- No new runtime or dev dependencies; everything runs under the existing
  vitest/tsc/eslint/next toolchain.
- Prompt-injection strings in fixtures are inert data: tagged, never
  executed, never shipped as live payloads.
- Never edit: `decide()`'s rules, `lib/types.ts` decision kinds,
  `tests/assessment.test.ts`, `app/api/triage/*` in the private repo,
  anything under `adws/**` or fusion-harness.

## 5. File ownership (collision control)

| Path | Owner task | Slot |
|---|---|---|
| `lib/clinical/contract.ts` + test | 1.a | grok |
| `evals/` manifest, cases, baseline runner + test | 1.b | terra |
| `lib/clinical/state.ts` + test | 2.a | terra |
| `lib/clinical/reconcile.ts` + test | 2.b | grok |
| `evals/adversarial/`, `evals/gates.ts` + test | 2.c | sol |
| `vault/tickets/medical-triage-adapter.md`, `vault/wave2-ledger.md` | 2.d | glm |
| `lib/clinical/pipeline.ts` + test, `lib/copy.ts` additions (EN+SW) | 3.a | grok |
| `vault/wave1-handoff.md` | 4.a | glm |

`lib/types.ts` is consumed read-only by all tasks in wave 1. Shared files
(`lib/copy.ts`, `package.json`) get one writer per change, serialized by the
harness's single-writer token.

## 6. Wave-1 exit validation

Wave 1 is done when all of these hold, and nothing softer:

- Gates green in this repo: `npx tsc --noEmit`, `npm test`, `npm run lint`,
  `npm run build` (existing assessment cases unchanged, including Kiswahili
  danger keywords, child-not-drinking → `go_now`, incomplete story →
  `need_one_more_answer`).
- A contract fixture missing any of the ten sections fails validation.
- Two temperatures (37.4 then 39.2, different timestamps) both survive;
  no single authoritative temperature remains.
- Monotonic decline across three readings is a derived feature with no LLM.
- Candidate `self-care` against `decide() == go_now` reconciles to `go_now`
  with a disagreement record.
- The eval report is family-keyed; retrieval and calibration read
  `not_measurable`; no field named `score`/`accuracy` gates a release.
- `model_id` and `knowledge_version` are null on the demo path.
- No training entrypoint, dataset writer, or model-weight path was added.
- The private repo and fusion-harness are byte-identical to their pre-wave
  state.
