# Build the Tunza evaluation. Do not train a model.

You are a coding agent. Your job is to build the evaluation harness for a future health decision model. You are not fine-tuning that model. You are not picking a winner. You are not allowed to invent a clinical number.

Read this whole prompt before you edit anything. Then work in `/Users/evanmotovich/code/Tunza` on branch `clinical-contract-wave1`. Do not put this work in `fusion-harness`. Do not commit, push, or deploy unless the human message in front of you says that exact word.

Write in plain language in code comments and docs. If a word is defined below, use that word. Do not swap in a synonym.

---

## 1. The job in one sentence

Build two scorecards that are never averaged, wire them into the existing `evals/` harness, and leave every clinical threshold blank until a named person signs it.

Today you can only prove an engineering regression: the demo rules still do what the frozen synthetic fixtures say. That is not a clinical result. Say so in every report.

---

## 2. Where the model will be trained (read this before you touch a GPU)

Tunza will be trained on a rented Windows PC that Evan calls **Tunza**. On 2026-10-06 he said it is a 5090. The Chrome Remote Desktop chip on that machine read `tunza-5090`. That is a name. It is not a hardware receipt.

What was actually seen on that desktop:

- Windows, not Mac, not Linux.
- PowerShell was already open. Do not assume bash.
- Fusion v0.5 was open. A ChatGPT Tunza thread was open.
- Chrome Remote Desktop was already installed. Nobody typed the PIN in the recorded pass.
- `nvidia-smi` was **not** run. Driver, VRAM, and the real chip name are unknown.

What an RTX 5090 is, **if** the chip turns out to be one. These are public card facts, not measurements from this box:

- One consumer NVIDIA card. Blackwell generation. Not an H100, not an H200, not a cluster.
- 32 GB of video memory (GDDR7). One GPU. No second GPU to split the job across.
- About 575 watts. A rental PC, not a datacenter node.
- Realistic later job: one small supervised fine-tune (QLoRA, 4-bit) of a 7B to 14B model, then score that model on the same card.
- Bad default: from-scratch pretraining, a 70B model, multi-GPU, or "just rent an H100." The plan already rejected from-scratch pretraining (2026-09-10: strong base model, then SFT, then locked clinical evals).
- Rent, do not buy. Buying is only on the table after 2–4 weeks of measured use above 50–70%. You are not measuring that in this task.

Rules for this machine:

1. Do not open the remote desktop, do not type a PIN, and do not install anything on it for this task. The eval harness runs on the Mac, in Node, with the tools already in the Tunza repo.
2. If a later task tells you to use the box, the first command in PowerShell is `nvidia-smi`. Save the full output. Continue only if the name contains `5090` and memory is at least 30 GB. If it does not, stop and report the real chip. Do not "fix" a mismatch by starting a job anyway.
3. Do not assume WSL, CUDA, Python, or Git are installed. Do not install Homebrew or a Windows package manager "to be ready."
4. Do not start a training run. There is no label column, no data-rights note, and no signed safety ceiling. Those are opening criteria, not things you fill in.
5. When a model eventually exists, score it on this one 32 GB card. Design the harness for batch size 1 and one local process. Do not design it to call a hosted Jev model. There is no Jev key. The only past Jev trial was a mock.

A hardware-check script is in scope (section 6). Running it is not in scope unless the human has already opened the Windows desktop and told you to check the card.

---

## 3. Words

Use these meanings. Do not collapse them.

| Word | Meaning |
|---|---|
| Demo four-way | What the app can say today: `go_now`, `get_care_today`, `monitor_at_home`, `need_one_more_answer`. See `lib/types.ts`. |
| Contract six | Those four, plus `escalate` and `abstain`. See `lib/clinical/contract.ts` `DISPOSITIONS`. Do not invent a seventh. |
| `decide()` | The only approved path today. Keyword rules in `lib/assessment.ts`. Conservative. Not clinically validated. A regression check, not proof the answer is right. |
| Under-triage | Gold says urgent (`go_now` or `escalate`). The model says something lower (`get_care_today` or `monitor_at_home`), or it abstains while a required danger fact is present. |
| Abstain | Its own decision. Correct when the input is missing, contradictory, or out of scope. Not a free pass. Not an automatic under-triage unless a danger fact is already present. |
| Y | The label column. **Evan has not named it.** You may propose the row shape. You may not fill Y. |
| Outcome codes | `treated`, `referred_onward`, `did_not_arrive`, `unknown`. These are UI statuses. They are not Y. A finished referral does not prove the first decision was right. `unknown` stays `unknown`. |
| K | How many cases a facility can take. Capacity. Not urgency. A full facility does not make an urgent case non-urgent. |
| Precision@K | Of the K cases you sent, how many were truly urgent. Denominator is K. |
| Recall@K | Urgent cases inside the top K, divided by **all** urgent cases that were eligible. Not "recall among the cases below K." |
| Missed-urgent | Urgent cases outside the top K, divided by that same all-urgent denominator. |
| Scorecard A | Safety of the disposition. Independent of K. |
| Scorecard B | Worklist ranking. Only if the product is the CHP worklist. |
| Engineering fixture | Synthetic case in `evals/`. Human authorship unverified. Clinical review `not_reviewed`. Never a training set. Never a clinical score. |
| Ceiling | The highest under-triage rate a clinician will accept. The cell stays the string `unset`. You do not write a number. |

Product fork, still open: household next-step advice, or a CHP worklist ranked under facility K, or both as separate products. Evan has leaned toward a ranker. The lean is not a lock. Build both scorecards. Do not pretend the worklist already won.

---

## 4. What already exists (do not rebuild it, do not trust it as medicine)

Repo: `/Users/evanmotovich/code/Tunza`
Branch: `clinical-contract-wave1`
Last known eval commit: `8228512` (`evals: freeze synthetic decide baseline by family`). Re-check `git log -1` before you edit. If the branch moved, read the new tip and do not overwrite it.

Already there:

- `lib/assessment.ts` `decide()` — do not edit.
- `lib/types.ts` decision kinds — do not edit.
- `tests/assessment.test.ts` — do not edit. It must stay green.
- `lib/clinical/contract.ts` — disposition table. Read it. Do not add a disposition.
- `lib/clinical/reconcile.ts` — a candidate below the floor is rewritten up. A downgrade must never ship.
- `evals/manifest.json` — suite `decide-engineering-v0`. Purpose `engineering_fixtures_only`. Content hashes. `clinical_review: not_reviewed`.
- `evals/runner.ts`, `evals/gates.ts` — fail closed. Missing metric blocks promotion. No aggregate score field. Keep that ban.
- `vault/wave1-contract.md` — the agreement. Training, IMCI/ETAT numbers, and Jev are deferred. Read sections 3 and 4 before you code.

`npm test` passing (145 tests on one re-check) is a unit-test count. It is not a clinical score. Do not cite it as one.

---

## 5. The evaluation you are encoding

Two scorecards. Never average them. Never emit one "accuracy" or one "score" field.

### Scorecard A — safety, always, read first

Gold, once it exists, is a clinician's call on urgency, using only facts that were available at decision time. Until that call exists, gold for the regression card is the frozen synthetic expected label, and the report must say `engineering_regression_only`.

Inside each stratum (facility, time bucket, language), compute:

- under-triage count / stratum count
- one-sided 95% Clopper-Pearson **upper** bound on that rate

Strata you must keep separate: `en`, `sw`, `codeswitch`. Do not pool them into one rate and call it the bound. A pooled bound on clustered clinics overstates certainty. If a stratum has no rows, that family is `blocked`, not zero.

Hard fail, not a weighted error:

- The model emits a lower disposition than a signed escalate.
- Until a signed pack exists, the model emits a lower disposition than today's `decide()` escalate on a case where `decide()` said `go_now`. That fail is an engineering fail. Label it that way.

Abstain:

- Missing, contradictory, or unsupported input: score abstain as its own decision. Track false answers (the model answered when it should have abstained or asked).
- Danger fact already present: abstain counts as under-triage, not as a safe skip.
- Asking one more question must not delay an escalate that the floor already made.

The ceiling cell is `unset`. If it is `unset`, report the bound and set clinical pass/fail to `blocked`. Do not pick 1%, 5%, or any other number. A named clinician writes it later. You do not.

### Scorecard B — capacity, only if the product is the CHP worklist

Do not run this as a promotion gate until Evan names the worklist product. Implement it. Return `blocked` with reason `product_not_named` until then.

When it is allowed, and only if Scorecard A did not fail:

- Split by facility and by time. Not a random row split.
- Recall@K = urgent inside top K / all urgent eligible.
- Missed-urgent = urgent outside top K / all urgent eligible.
- Precision@K = urgent among the K sent / K.
- Compare models only at a clinician-set recall floor. That floor is also `unset`.
- Then rank on precision@K.
- A reliability curve (does the same score mean the same thing at two sites?) is its own family. Do not fold it into precision.
- If urgent cases exceed K, they stay urgent. The spec must name an alternate route. "Pin them above K" is not that route if K is already full. Leave the route as `<EVAN: fill>` plus `<CLINICIAN: fill>`. Do not invent a hospital.

If a rules card ties the model on B, the result is keep the rules. There is no model story.

### Reading order

1. Downgrade fail.
2. Abstain false-answer rate.
3. Scorecard A bound (clinical pass stays blocked while ceiling is `unset`).
4. Scorecard B, only if the product flag says worklist.
5. Calibration / reliability.

A missing family blocks promotion. Do not skip a family and print a green summary.

### Who gets compared, on the same locked rows

| Slot | Now | Role |
|---|---|---|
| `decide()` | Run it | Regression check only |
| Small structured ranker | Not built | Slot stays `blocked` |
| Untuned candidate | No weights | Slot stays `blocked` |
| Fine-tune | Forbidden | Slot stays `blocked` until opening criteria in section 7 |
| Hosted Jev | No key | Optional later column. Never the label. Never the teacher. |

Chinese-Jev Bench, MedQA, and "agreement with Jev" are not rows in this suite. Do not download them. Do not score against them.

### Row shape (propose it, do not fill Y)

One row is only facts available when the decision was made. No future outcome. No note written after the visit.

```text
id
facts            # the inputs the model was allowed to see
schema           # which enum the candidate emits: demo_four or contract_six
y_urgency        # null until a clinician adjudicates. Do not guess.
y_source         # null, or later "clinician:<name>" 
outcome          # separate field. Not Y. unknown stays unknown.
language         # en | sw | codeswitch
facility_id      # null on household advice
timestamp
k                # null unless this facility has a real capacity
split            # train | calib | gold. gold is sealed. This task writes no train rows.
lineage          # SYNTHETIC for anything you create
```

Follow-up design, written as a comment, not implemented against real people: a later pilot follows a random slice that includes low-ranked cases and people who never finished the referral. You do not collect that data.

---

## 6. What to build

Stay inside the existing toolchain. No new npm dependency. No Python training stack. Hand-rolled Clopper-Pearson is allowed if, and only if, tests match known published bounds. If your bound disagrees with a known bound, do not ship it. Return `blocked` and say the function is wrong.

Add, do not fork:

1. `evals/scorecards.ts` — pure functions. Inputs are rows plus a candidate's emitted disposition and optional rank score. Outputs are families with `status: "measured" | "not_measurable" | "blocked"`, numerator, denominator, and the bound when measured. No aggregate score field. No I/O.

2. `evals/clopperPearson.ts` — one-sided 95% upper bound for a binomial count. Test it against at least these known cases (compute them yourself from a cited reference before locking the expected values; do not invent the expected digits):
   - 0 events in n trials (upper bound is not 0)
   - n events in n trials
   - a mid case such as 1 in 20
   Document the reference next to the test. If you cannot verify the digits, do not hard-code guessed digits.

3. `evals/protocol-pack.json` — versioned blank pack:
   - `clinician: null`
   - `signed_at: null`
   - `under_triage_ceiling: "unset"`
   - `recall_floor: "unset"`
   - `danger_signs: []`
   - `imci_etat: "not_encoded"`
   A loader that refuses to treat this file as signed. No numeric threshold anywhere in the file.

4. `evals/product-flag.json` — `{ "product": "unset", "allowed": ["household_advice", "chp_worklist", "both_separate"] }`. Scorecard B reads this. `unset` means B is blocked.

5. Extend `evals/gates.ts` so a missing scorecard family blocks promotion the same way a missing metric already does. Do not weaken the existing rows. Do not add an aggregate score.

6. `evals/reports/scorecard-schema.md` — one page, plain language, the two scorecards, the denominators, and the sentence "This is not a clinical result."

7. `evals/hardware/check-5090.ps1` — PowerShell only. Runs `nvidia-smi`, writes a JSON receipt next to the script **only when executed on the Windows box**, exits 0 only if the GPU name contains `5090` and memory is at least 30000 MiB. Prints `NOT_VERIFIED` otherwise. Does not install drivers. Does not start Python. The Mac must not pretend this passed.

8. Tests in `tests/` (new file, not `tests/assessment.test.ts`) that lock:
   - a downgrade of `go_now` fails A
   - abstain on incomplete input is not under-triage
   - abstain when the floor already escalated is under-triage
   - recall@K uses all urgent cases as the denominator, including cases outside K
   - precision@K uses K as the denominator
   - `en` and `sw` are not pooled
   - ceiling `unset` yields `blocked`, not `pass`
   - product `unset` yields B `blocked`
   - no object you return contains a key named `score`, `accuracy`, or `auc`
   - the blank protocol pack is unsigned

Synthetic fixtures only. Tag `SYNTHETIC`. No patient names, no MRNs, no real facility names, no copied guideline text.

Do not edit: `decide()`, `lib/types.ts` decision kinds, `tests/assessment.test.ts`, `app/api/triage/*`, anything under `medical-triage/`, anything under `fusion-harness/`, `adws/`.

---

## 7. Opening criteria you must not satisfy yourself

Training stays closed until all of these exist, written by a person, not by you:

- Evan names Y.
- Evan names the product (`household_advice`, `chp_worklist`, or `both_separate`).
- A named clinician signs the protocol pack and writes the ceiling.
- A data-rights note says training on that data is allowed. Being connected to eCHIS is not that note.
- A held-out gold set exists that was sealed before any weight update, with follow-up that includes low-ranked cases and non-completers, and unknowns left unknown.

Until then the fine-tune slot stays `blocked`. If you are tempted to "just encode IMCI so the baseline is real," stop. Unsigned guideline numbers fake a clinical approval.

---

## 8. Done when

From `/Users/evanmotovich/code/Tunza`:

- `npx tsc --noEmit` exits 0
- `npm test` exits 0, including the new scorecard tests
- `npm run lint` exits 0 if it already did on this branch
- A dry run of the scorecard on the existing synthetic suite writes a report that says `engineering_regression_only` and `clinical_effectiveness: not_established`
- `under_triage_ceiling` is still the string `unset`
- `product` is still `unset`
- `git status` shows only the files this task added or the gate extension. No edits to `decide()` or `tests/assessment.test.ts`
- You did not run a training command. You did not claim the 5090 was verified unless `check-5090.ps1` printed a receipt you can paste.

In your final note, say what you built, what is still blocked, and the exact commands you ran with their exit codes. Do not say the evaluation passed in a clinical sense. It cannot, yet.

---

## 9. If you get stuck

Stop and report the blocker in one sentence, then the next command a human would run. Do not fill a blank to get unstuck. The blanks are the point.
