# Ticket — medical-triage adapter

Status: **not started**. This wave does not edit
`/Users/evanmotovich/code/medical-triage`. The route, its system prompt, the
schema, and env stay untouched. No push.

Opened 2026-10-06 by host recovery, from the wave-1 contract. This is an
engineering hardening ticket. It is not a clinical approval and not a
license to train on stored cases.

## What is unsafe today

Verified by direct read of `app/api/triage/route.ts` and `lib/types.ts` on
2026-10-06. Line numbers are from that read; re-check them before editing.

- The route calls hosted Anthropic `claude-sonnet-4-5` with no timeout
  (`app/api/triage/route.ts:130`). This is a prompt lane, not owned weights.
- Parsed JSON is cast to `TriageResponse` with no runtime schema check
  (`app/api/triage/route.ts:147`).
- Parse failure logs the raw model text (`app/api/triage/route.ts:149`).
  That text can contain the symptom string that was sent in. Stop logging it.
- Persistence is best-effort and runs after inference
  (`app/api/triage/route.ts:157-185`). A database failure still returns the
  model answer. A failed safety reconciliation must not fail open into a
  downgrade.
- `redFlags` is optional on `TriageResponse` (`lib/types.ts:37`) while the
  prompt requires the array (`app/api/triage/route.ts:61`).
- Private urgency is `self-care | see-clinic | urgent`
  (`lib/types.ts:1`). Public `DecisionKind` is a different scale. Do not
  treat them as the same word.

## Required change, when this ticket opens

1. Runtime-validate `TriageResponse` before return. Reject or abstain on a
   shape miss. Do not log raw model text.
2. Map `self-care | see-clinic | urgent` onto the wave-1 disposition table
   in `lib/clinical/contract.ts`. Do not invent a fifth user-visible headline.
3. Run the same reconciler (`lib/clinical/reconcile.ts`) with `decide()` as
   the floor. A candidate below the floor is rewritten to the floor. Record
   the disagreement. Do not silently merge.
4. Record `model_id` on the disagreement and, only if a model actually ran,
   in provenance. The public demo path stays `model_id: null`.
5. Do not rewrite `SYSTEM_PROMPT` in the same change as the validator.
   Prompt edits are a separate review.

## Opening criterion

This ticket stays closed until wave-1 gates are green on
`clinical-contract-wave1` and a named owner accepts the disposition map.
Opening it does not authorize training, retrieval ingestion, or a production
cutover.
