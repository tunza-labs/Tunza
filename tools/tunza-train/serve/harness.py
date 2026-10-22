"""Deployment harness for the Tunza triage model. Pure functions plus one orchestrator, no model and no torch.

The rules answer from decide() is the safety floor. The model answer may be raised to it, never lowered below it.
If the model output is invalid, or the model call fails or times out, the rules answer is returned alone.
If the rules answer cannot be computed, triage() raises RulesUnavailable and nothing is returned.

    rules = DecideRules()                                   # decide() through gen_cases.Decider (node + esbuild)
    result = triage(intake, generate=my_model, rules=rules, timeout_s=20)
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path.insert(0, str(TOOLS))
import evaluate as ev  # noqa: E402
import gen_cases  # noqa: E402

reward = ev.reward

HARNESS_VERSION = 1
SERVED = ("go_now", "get_care_today", "need_one_more_answer", "monitor_at_home")
RANK = {d: reward.RANK[d] for d in SERVED}  # go_now 40 > get_care_today 30 > need_one_more_answer 20 > monitor_at_home 10
LANGS = ("en", "sw", "cs")
INTAKE_ENUMS = {
    "who": ("self", "household_adult", "child", "unknown"),
    "awake": ("alert", "sleepy", "not_waking", "unknown"),
    "breathing": ("fine", "difficult", "severe", "unknown"),
    "drinking": ("yes", "little", "no", "unknown"),
    "duration": ("today", "two_days", "longer", "unknown"),
    "mainProblem": ("breathing", "fever", "injury", "stomach", "other", "unknown"),
}
INTAKE_KEYS = ("who", "presentation", "awake", "breathing", "drinking", "duration", "mainProblem")
MAX_PRESENTATION_CHARS = 2000
DEFAULT_REPO = Path(os.environ.get("TUNZA_REPO", r"C:\Users\hirsc\tunza-train"))


class IntakeError(ValueError):
    """The request intake is malformed. The caller gets a 400, no answer."""


class RulesUnavailable(RuntimeError):
    """decide() could not run. There is no safety floor, so no answer is returned."""


# ---------------------------------------------------------------------------
# Intake and prompt
# ---------------------------------------------------------------------------


def validate_intake(intake: object) -> dict:
    """Return the intake with every key present (missing enum fields become null). Raise IntakeError otherwise."""
    if not isinstance(intake, dict):
        raise IntakeError("intake must be a JSON object")
    extra = sorted(set(intake) - set(INTAKE_KEYS))
    if extra:
        raise IntakeError(f"unknown intake fields: {extra}")
    story = intake.get("presentation")
    if not isinstance(story, str):
        raise IntakeError("presentation must be a string (it may be blank)")
    if len(story) > MAX_PRESENTATION_CHARS:
        raise IntakeError(f"presentation is longer than {MAX_PRESENTATION_CHARS} characters")
    out = {}
    for key in INTAKE_KEYS:
        value = intake.get(key)
        if key != "presentation" and value is not None and value not in INTAKE_ENUMS[key]:
            raise IntakeError(f"{key} must be null or one of {list(INTAKE_ENUMS[key])}")
        out[key] = value
    return out


def build_prompt(intake: dict) -> str:
    """The exact prompt text the model was trained and evaluated on (evaluate.make_prompt)."""
    return ev.make_prompt(intake)


# ---------------------------------------------------------------------------
# Model output
# ---------------------------------------------------------------------------


def parse_model_output(raw: object, intake: dict) -> tuple[dict | None, str | None]:
    """Return (answer, None) for a valid answer or (None, reason) for a rejected one.

    Format rules are the reward's format gate. On top of it: the disposition must be one of the four served
    dispositions, every danger fact must be grounded in the intake (a whole phrase of the story, or a field pair
    such as awake=not_waking that is true in the intake), and follow_up_question must be one real question for
    need_one_more_answer and null otherwise.
    """
    parsed, error = reward._parse_output(raw)
    if error is not None:
        return None, f"format: {error}"
    disposition = parsed["disposition"]
    if disposition not in SERVED:
        return None, f"disposition not served: {disposition}"
    facts = parsed["danger_facts"]
    if facts and reward._any_ungrounded(facts, intake, ""):
        return None, "danger_facts not grounded in the intake"
    if reward._follow_up_violation(disposition, parsed["follow_up_question"]):
        return None, "follow_up_question is not one real question for need_one_more_answer, or is set for another disposition"
    return {"disposition": disposition, "danger_facts": list(facts), "follow_up_question": parsed["follow_up_question"]}, None


# ---------------------------------------------------------------------------
# Rules and floor
# ---------------------------------------------------------------------------


def rules_answer(intake: dict, kind: str, language: str = "en") -> dict:
    """The rules answer in the model's contract, built the same way the training labels are (gen_cases.make_answer)."""
    if kind not in SERVED:
        raise RulesUnavailable(f"decide() returned an unknown kind: {kind!r}")
    return gen_cases.make_answer(language, intake, kind)


def apply_floor(model: dict, rules: dict) -> tuple[dict, dict]:
    """final = the higher of model and rules. Returns (final, floor record)."""
    if RANK[model["disposition"]] < RANK[rules["disposition"]]:
        why = f"candidate_below_floor: model {model['disposition']} < rules {rules['disposition']}"
        return rules, {"raised": True, "why": why}
    return model, {"raised": False, "why": None}


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------


def call_model(generate, prompt: str, timeout_s: float, executor: cf.Executor | None = None) -> tuple[str | None, str | None]:
    """Run generate(prompt) with a timeout. Returns (raw text, None) or (None, failure reason).

    The timeout covers time spent queued behind an earlier call on a shared executor. A timed-out generation
    cannot be killed; it keeps its worker until it ends and its result is discarded.
    """
    own = executor is None
    pool = cf.ThreadPoolExecutor(max_workers=1) if own else executor
    future = pool.submit(generate, prompt)
    try:
        return future.result(timeout=timeout_s), None
    except cf.TimeoutError:
        future.cancel()
        return None, f"model_timeout: no answer within {timeout_s}s"
    except Exception as exc:  # noqa: BLE001  any model failure falls back to the rules
        return None, f"model_error: {type(exc).__name__}: {exc}"
    finally:
        if own:
            pool.shutdown(wait=False, cancel_futures=True)


def triage(intake: object, *, generate, rules, timeout_s: float = 20.0, language: str = "en",
           executor: cf.Executor | None = None) -> dict:
    """One request. rules(intake) -> decide() kind. generate(prompt) -> raw model text, or None when no model is loaded.

    Every response carries final, source (model, floor_raised or fallback), rules_answer and model_answer.
    """
    clean = validate_intake(intake)
    if language not in LANGS:
        raise IntakeError(f"language must be one of {list(LANGS)}")
    try:
        kind = rules(clean)
    except BaseException as exc:  # gen_cases.Decider raises SystemExit on failure
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise RulesUnavailable(f"decide() failed: {type(exc).__name__}: {exc}") from None
    floor_answer = rules_answer(clean, kind, language)

    model_answer, fallback_reason = None, None
    if generate is None:
        fallback_reason = "model_unavailable"
    else:
        raw, fallback_reason = call_model(generate, build_prompt(clean), timeout_s, executor)
        if fallback_reason is None:
            model_answer, fallback_reason = parse_model_output(raw, clean)

    if model_answer is None:
        final, source, floor = floor_answer, "fallback", {"raised": False, "why": None}
    else:
        final, floor = apply_floor(model_answer, floor_answer)
        source = "floor_raised" if floor["raised"] else "model"
    if RANK[final["disposition"]] < RANK[floor_answer["disposition"]]:
        raise RuntimeError("floor violated; refusing to answer")
    return {
        "final": final,
        "source": source,
        "rules_answer": floor_answer,
        "model_answer": model_answer,
        "floor": floor,
        "fallback_reason": fallback_reason,
        "harness_version": HARNESS_VERSION,
    }


# ---------------------------------------------------------------------------
# Real rules: decide() from lib/assessment.ts through gen_cases.Decider
# ---------------------------------------------------------------------------


class DecideRules:
    """Callable intake -> decide() kind. Builds the esbuild bundle on first use, under a lock.

    gen_cases resolves the repo from its own folder, which is wrong for this copy, so the paths are set here.
    Set TUNZA_REPO to the checkout that holds lib/assessment.ts and node_modules/.bin/esbuild.
    """

    def __init__(self, repo: Path = DEFAULT_REPO) -> None:
        self.repo = Path(repo)
        self._decider = None
        self._lock = threading.Lock()

    def _get(self):
        with self._lock:
            if self._decider is None:
                gen_cases.ASSESSMENT_TS = self.repo / "lib" / "assessment.ts"
                names = ("esbuild.cmd", "esbuild") if os.name == "nt" else ("esbuild",)  # the bare shim cannot be spawned on Windows
                gen_cases.ESBUILD_CANDIDATES = [self.repo / "node_modules" / ".bin" / n for n in names]
                self._decider = gen_cases.Decider()
            return self._decider

    def __call__(self, intake: dict) -> str:
        return self._get().decide([intake])[0]["kind"]

    def close(self) -> None:
        if self._decider is not None:
            self._decider.close()


def dumps(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)
