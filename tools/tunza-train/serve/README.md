# Tunza triage serving harness

First deployment harness for the Tunza triage model. Engineering shakedown only. Not promoted and never shown to users.

The rules answer from `decide()` (lib/assessment.ts) is the safety layer. The model answer may be raised to the rules answer but is never returned below it. If the model output is invalid, or the model call fails or times out, the rules answer is returned alone. If the rules cannot run, the server returns 503 and no answer.

## Files

- `harness.py` holds the pure pieces: `validate_intake`, `build_prompt` (the training prompt, `evaluate.make_prompt`), `parse_model_output`, `rules_answer` (`gen_cases.make_answer`), `apply_floor`, `call_model` (timeout), `triage` (one request), and `DecideRules` (decide() through `gen_cases.Decider`).
- `serve_model.py` is a stdlib HTTP server. The model loads lazily through `eval_adapter.resolve_base` and `eval_adapter.load_model`.
- `test_harness.py` holds unittest tests with a fake model and fake rules. They need no GPU, torch or node.

## Run

```
# tests
C:\Users\hirsc\tunza-train\.venv-train\Scripts\python.exe -m unittest discover -s serve -p test_harness.py

# server (loads the model on the first POST, not at start)
python serve/serve_model.py --adapter runs/<tag>/adapter --repo <checkout with lib/assessment.ts and node_modules/.bin/esbuild>
```

Options: `--model` (base; default is the base in `adapter_config.json`), `--host 127.0.0.1`, `--port 8765`, `--timeout 20` (seconds per model call, queue wait included), `--max_new 100`, `--allow-cpu`. If `--adapter` is omitted, every request gets the rules fallback.

Without CUDA or MPS the model is not loaded. `/health` shows `model: failed` with the message `no GPU visible ...`, and every request gets the rules fallback with that reason. `--allow-cpu` overrides this.

Rules need node plus esbuild in `--repo` (env `TUNZA_REPO`, default `C:\Users\hirsc\tunza-train`). That default checkout has no `node_modules`, so pass a checkout that has them.

## Request

`POST /v1/triage`

```json
{"intake": {"who": "child", "presentation": "My child is having a seizure right now.", "awake": "alert",
            "breathing": "fine", "drinking": "yes", "duration": "today", "mainProblem": "other"},
 "language": "en"}
```

- `presentation` is a required string. It may be blank and is capped at 2000 characters.
- `who`, `awake`, `breathing`, `drinking`, `duration` and `mainProblem` are null or one of the `lib/types.ts` values. Unknown fields are rejected.
- `language` is `en`, `sw` or `cs`, default `en`. It only selects the language of the rules follow-up question.
- The body may be at most 16 KB.

## Response

```json
{"final": {"disposition": "go_now", "danger_facts": ["My child is having a seizure right now."], "follow_up_question": null},
 "source": "floor_raised",
 "rules_answer": {"disposition": "go_now", "danger_facts": ["My child is having a seizure right now."], "follow_up_question": null},
 "model_answer": {"disposition": "get_care_today", "danger_facts": [], "follow_up_question": null},
 "floor": {"raised": true, "why": "candidate_below_floor: model get_care_today < rules go_now"},
 "fallback_reason": null,
 "harness_version": 1}
```

- `source` is `model` when the valid model answer is at or above the rules answer and is returned as is. It is `floor_raised` when the valid model answer was below the rules answer and the rules answer is returned. It is `fallback` when the model was invalid, failed, timed out or is not loaded, and the rules answer is returned. In that case `model_answer` is null and `fallback_reason` says why.
- Rank: go_now 40 > get_care_today 30 > need_one_more_answer 20 > monitor_at_home 10.
- A model answer is rejected (fallback) if any of these hold:
  - It fails the reward's format gate (one JSON object, exactly the three keys, no duplicate keys, nothing outside the object).
  - Its disposition is not one of the four above. `escalate` and `abstain` are rejected too.
  - A danger fact is not a whole phrase of 3+ characters from the story, or a field pair such as `awake=not_waking` that is true in the intake.
  - `follow_up_question` is not exactly one question of 3+ words for `need_one_more_answer`, or is not null for any other disposition.
- Status codes: 400 for a malformed body or intake, 503 when decide() cannot run (no floor, so no answer), 404 for other paths.

`GET /health` returns `{"status": "ok", "batch_size": 1, "timeout_s": 20, "model": "not_loaded|loading|ready|failed", "model_error": ..., "adapter": ...}`.

## Behaviour to know

- Batch size is 1. One worker thread runs one generation at a time, and other requests queue behind it. The timeout includes queue time.
- A timed-out generation cannot be stopped. It holds the worker until it ends, so requests behind it also time out and fall back.
- The first request triggers the load inside the worker. Requests during the load fall back.
- If the load fails, the error is kept and the load is not retried until restart.
- decide() runs as one `node` subprocess per request.
- `lib/clinical/reconcile.ts` keeps the floor even when the candidate is higher (`candidate_not_approved`). This harness returns a higher model answer as asked (final = the higher of model and rules). The two differ for model answers above the rules. Decide which is intended before anything is wired to the app.

## Not built

- Clinic or eCHIS hand-off.
- Auth. The server binds 127.0.0.1 by default and has no access control.
- Rate limits.
- Logging without patient data. Only the stdlib request line (method, path, status) goes to stderr. There is no structured audit log, and the disagreement record is returned but not stored.
- Monitoring and alerting.
- TLS, multi-worker serving and a request ID.

## Capacity

Throughput and latency are not measured. No real model was loaded for this build. The numbers depend on the base size, the GPU, `max_new`, and the GPU being shared with training. Measure them on the target machine before stating any capacity.
