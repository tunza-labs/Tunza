# 2026-10-06 — clinical contract wave 1, host recovery

The collaboration that was supposed to write tasks 2.a–4.a stopped blocked.
The parent had already accepted test-sourced eval labels as an engineering
ruler only, with human authorship unverified.

Host recovery, in this working tree, no commit:

- Checked the child files for the contract and the frozen baseline against
  the tree. Baseline hashes for `lib/assessment.ts` and
  `tests/assessment.test.ts` matched the frozen report.
- Added encounter state, the reconciler, adversarial fixtures, release-gate
  machinery that cannot authorize a release, the pipeline, the adapter
  ticket, the wave-2 ledger, and this handoff.
- Did not edit `decide()`, decision kinds, the private route, or
  fusion-harness.
- Foreground gates: `tsc` clean, `npm test` 145 passed, lint clean, Next
  build compiled.

Still blocked: promotion, training, retrieval, guideline thresholds, push,
and any claim that the collaboration graph succeeded.
