# Wave-1 handoff

Dated 2026-10-06 (local). Branch `clinical-contract-wave1` in
`/Users/evanmotovich/code/Tunza`. Head of the last child commit is
`8228512`. Host recovery added the remaining files in the working tree and
did **not** commit, push, or merge.

The collaboration graph is not successful. Tasks 0.a and 1.a were executed
by children and checked against the files. Task 1.b was executed by a child;
its label question was decided by the parent, not by a child report. Tasks
2.a–4.a never ran as child writes. The host wrote those modules after
reading the current tree. Child reports are evidence, not acceptance.

This slice is an engineering contract around the existing demo floor. It is
not a clinical approval, not a device claim, and not a model release.

## Label decision

Parent decision, applied here: accept the test-sourced labels for
engineering-only regression, with human authorship explicitly unverified.

Recorded on `evals/manifest.json` as `label_authorship_decision`, and
required by `loadSuite`. The field is excluded from the frozen measurement
hash (`measurementManifest` in `evals/runner.ts`) so
`evals/reports/baseline-decide.json` stays the unchanged baseline. That
exclusion is a host amendment. It does not turn the labels into reviewed
labels.

Wave 2 must not read these labels as clinical truth. Families that are not
measurable stay `not_measurable`.

## What is in the tree

| Path | Role |
|---|---|
| `vault/capability-map.md`, `vault/wave1-contract.md` | Child 0.a audit and boundary. Host did not rewrite them. |
| `lib/clinical/contract.ts` | Child 1.a ten-section contract. Host did not edit it. |
| `evals/manifest.json`, `evals/runner.ts`, `evals/reports/baseline-decide.json` | Child 1.b harness. Host added the authorship decision and hash exclusion only. Baseline file unchanged. |
| `lib/clinical/state.ts` | Host. Append-only encounter projection, unit normalization, unresolved same-type conflicts, structural trends. No disposition effect. |
| `lib/clinical/reconcile.ts` | Host. Demo floor wins. Lower candidate rewritten up. Unapproved higher candidate not applied. Telemetry failure does not change the answer. |
| `evals/adversarial/`, `evals/gates.ts` | Host. Same manifest shape as 1.b. Injection strings are inert data. Promotion function cannot authorize release. |
| `lib/clinical/pipeline.ts`, `lib/copy.ts` section labels | Host. `decide()` → reconciler → contract. EN and SW labels. No new headline. |
| `evals/reports/wave1-pipeline.json` | Host comparison. Does not replace the frozen baseline. |
| `vault/tickets/medical-triage-adapter.md`, `vault/wave2-ledger.md` | Host. Docs only. Private route not edited. |

`decide()`, `lib/types.ts` decision kinds, and `tests/assessment.test.ts`
were not edited. `medical-triage` and `fusion-harness` were not edited.
Pre-existing dirt in those repos was left as found.

## Receipts

Gates run in the foreground on 2026-10-06, after the host files existed:

- `npx tsc --noEmit`: exit 0.
- `npm test`: 145 passed, 13 files. Includes the previous assessment tests.
- `npm run lint`: exit 0.
- `npm run build`: Next.js 16.3.3 compiled; static pages generated.

Frozen baseline vs pipeline (`evals/reports/wave1-pipeline.json`):

- `frozen_baseline_replaced`: false
- `ship_gate`: none
- `comparison.families_equal`: true
- `red_flag_recall`: measured 3/3
- `abstention`: measured 3/3
- `non_downgrade`: measured 3/3
- `clinical_correctness`, `calibration`, `retrieval`,
  `multilingual_generation`, `medication_safety`: `not_measurable`

No field named `score` or `accuracy` is a ship gate. The pipeline report's
`ship_gate` is `none`.

Release-gate table on the identical baseline and pipeline family results
(`evaluateReleaseGate`, asserted in `tests/eval-gates.test.ts`):

| Row | Status |
|---|---|
| red-flag recall ≥ baseline | pass |
| no safety-critical language-slice regression | pass |
| ANSWER/ASK/ABSTAIN/ESCALATE distribution reported | pass for the fixture expected labels (0 / 3 / 0 / 6) |
| clinical thresholds signed | blocked |
| required metric families measured | blocked (`not_measurable` families) |
| promotion | blocked |
| release authorization | none |
| clinical effectiveness | not established |

Champion/challenger on the frozen engineering inputs agrees 9/9 between
fixture expected labels and `decide()`, and still returns promotion blocked.
Agreement on an engineering ruler is not a promotion.

## Invariants checked

- A contract fixture missing any of the ten sections fails validation
  (`tests/clinical-contract.test.ts`, "fails when any section is missing").
- Temperatures 37.4 then 39.2, different timestamps, both remain. The state
  object has no `temperature` field (`tests/clinical-state.test.ts`).
- Three declining readings become the derived feature
  `three declining readings`. `lib/clinical/state.ts` does not call
  `decide()` or a model (`tests/clinical-state.test.ts`).
- Candidate `self-care` against `decide() == go_now` reconciles to `go_now`
  with a disagreement record (`tests/clinical-reconcile.test.ts`,
  `tests/clinical-pipeline.test.ts`).
- `monitor_at_home` is still rejected when critical answers are unknown and
  there is no story. Pipeline disposition matches `decide()`.
- Demo-path `model_id` and `knowledge_version` are null. Evidence bundle
  stays empty with `trust_tier: "none"`.
- No training entrypoint, dataset writer, or model-weight path was added.
- Adversarial observations, not ship gates: `passed out`, `degdege`, and
  `haamuki` do not hit the keyword floor (`need_one_more_answer`). The inert
  instruction marker beside `unconscious` does not change the floor
  (`go_now`) and is not executed. `fitting` in "The shirt is fitting loosely"
  overlaps the keyword pattern and the floor returns `go_now`; no clinical
  label was assigned to that look-alike.

## Blocked

- Promotion. Unsigned clinical thresholds and `not_measurable` families.
- Training, retrieval ingestion, guideline thresholds, JEV, private-route
  edits, cross-encounter persistence. Opening criteria are in
  `vault/wave2-ledger.md`.
- Push, merge, publication, and any live or release validation. Not
  authorized.
- Verified human authorship of labels. Explicitly unresolved. Accepted only
  as an engineering ruler.
- The collaboration graph. Do not mark it accepted or successful.

## Wave 2 opens only when the ledger's evidence exists

Retrieval needs named approved sources with jurisdiction, version, and
effective dates. The shadow model path needs the adapter ticket done and a
shadow run that does not change the demo answer. SFT needs a written failure
analysis citing `evals/reports/` numbers, a named label producer, and a
data-rights basis. None of those exist today.
