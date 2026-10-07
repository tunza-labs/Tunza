# Wave-2 ledger

Dated 2026-10-06. Nothing on this page is open. Each item names the evidence
that would have to exist before work starts. Absence of that evidence is the
current state, not a placeholder to fill in.

Labels in `evals/` are an engineering regression ruler. Human authorship is
unverified. Clinical review is `not_reviewed`. They are not a label column
and not a training set.

## Deferred

### Retrieval ingestion

Blocked. No named approved source exists with publisher, jurisdiction,
document version, effective date, and review date. The contract keeps an
empty evidence bundle (`trust_tier: "none"`).

Opens only when a source list names those fields for each document, and a
person authorized to approve the source signs the list. Unverified web text
cannot enter the bundle.

### Model shadow path

Blocked. Depends on `vault/tickets/medical-triage-adapter.md`. The private
route is still cast-only, logs raw model text, and has no floor under the
model.

Opens only after that ticket is implemented and a shadow run shows
disagreement counts without changing the user-visible demo path.

### Offline / degraded depth

Blocked. Named failure states exist in the public app as UI states. There is
no local model, no queued clinical sync, and no knowledge version to mark
stale.

Opens only after a written capability list says which functions require
connectivity, and cached guidance carries `last_sync` plus a version. Stale
cache must not be marked current.

### SFT / QLoRA / distillation / quantization

Blocked. No measured failure analysis cites `evals/reports/` numbers. No
label producer is named. No data-rights basis exists. A case row is not a
training example. Same-model self-grading is forbidden.

Opens only when all three exist in writing:

1. A failure analysis that cites frozen eval-report numbers and says which
   failure training would change.
2. A named label producer and a review status other than unverified.
3. A documented data-rights basis for every row that would be used.

Until then, no training entrypoint, dataset writer, or weight path.

### Guideline thresholds and IMCI/ETAT encoding

Blocked. Encoding numeric clinical thresholds without a named clinician and
a versioned rule pack would fake approval. The keyword floor stays a floor.

Opens only on a documented clinical review that names the reviewer role,
jurisdiction, protocol version, and effective dates. This ledger cannot
supply that review.

### Cross-encounter PatientState

Blocked. State in this wave is encounter-scoped. Persisting a richer state
in localStorage before privacy projections exist would expand exposure.

Opens only when those projections exist and a privacy review accepts the
stored fields.

## Not a release

Wave 2 does not start because wave 1's engineering gates passed. Promotion
stays blocked while clinical thresholds are unsigned and required metric
families are `not_measurable`.
