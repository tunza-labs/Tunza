"""Harness and server tests. Fake model and fake rules only: no GPU, no torch, no node. Stories are synthetic."""
import json
import sys
import threading
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as h  # noqa: E402
import serve_model as sm  # noqa: E402


def intake(story="My child has a fever since this morning.", **fields):
    base = {"who": "child", "presentation": story, "awake": "alert", "breathing": "fine", "drinking": "yes",
            "duration": "today", "mainProblem": "fever"}
    base.update(fields)
    return base


def out(disposition, facts=(), question=None):
    return json.dumps({"disposition": disposition, "danger_facts": list(facts), "follow_up_question": question})


def model(text):
    return lambda prompt: text


def rules(kind):
    return lambda _intake: kind


_DEFAULT = object()


def run(text_or_fn, kind, case=_DEFAULT, **kw):
    gen = text_or_fn if callable(text_or_fn) or text_or_fn is None else model(text_or_fn)
    return h.triage(intake() if case is _DEFAULT else case, generate=gen, rules=rules(kind), **kw)


class ValidAnswerTest(unittest.TestCase):
    def test_valid_answer_at_the_rules_level_is_the_model_answer(self):
        r = run(out("get_care_today"), "get_care_today")
        self.assertEqual(r["source"], "model")
        self.assertEqual(r["final"]["disposition"], "get_care_today")
        self.assertEqual(r["model_answer"]["disposition"], "get_care_today")
        self.assertEqual(r["rules_answer"]["disposition"], "get_care_today")
        self.assertFalse(r["floor"]["raised"])
        self.assertIsNone(r["fallback_reason"])

    def test_valid_answer_above_the_rules_is_kept(self):
        r = run(out("get_care_today"), "monitor_at_home")
        self.assertEqual((r["source"], r["final"]["disposition"]), ("model", "get_care_today"))

    def test_need_one_more_answer_with_a_real_question_passes(self):
        r = run(out("need_one_more_answer", question="Is the child drinking normally today?"), "monitor_at_home")
        self.assertEqual(r["source"], "model")
        self.assertEqual(r["final"]["follow_up_question"], "Is the child drinking normally today?")

    def test_prompt_is_the_training_prompt(self):
        seen = []
        run(lambda p: seen.append(p) or out("go_now"), "monitor_at_home")
        self.assertEqual(seen, [h.ev.make_prompt(intake())])


class FloorTest(unittest.TestCase):
    def test_model_lower_than_rules_is_raised_and_the_reason_recorded(self):
        r = run(out("monitor_at_home"), "get_care_today")
        self.assertEqual(r["source"], "floor_raised")
        self.assertEqual(r["final"], r["rules_answer"])
        self.assertEqual(r["model_answer"]["disposition"], "monitor_at_home")
        self.assertTrue(r["floor"]["raised"])
        self.assertIn("candidate_below_floor", r["floor"]["why"])
        self.assertIn("monitor_at_home < rules get_care_today", r["floor"]["why"])

    def test_go_now_rule_case_is_never_returned_lower(self):
        case = intake("My child is having a seizure right now.")
        outputs = [out(d) for d in h.SERVED] + [
            out("go_now", ["is having a seizure"]),
            out("need_one_more_answer", question="Is the child breathing normally now?"),
            "not json", out("escalate"), out("abstain"), "", "{}",
            out("monitor_at_home", ["a dragon"]),
        ]
        slow = _Slow()
        gens = [model(o) for o in outputs] + [None, _raises, slow.generate]
        try:
            for gen in gens:
                r = h.triage(case, generate=gen, rules=rules("go_now"), timeout_s=0.05)
                self.assertEqual(r["final"]["disposition"], "go_now", msg=repr(gen))
                self.assertEqual(r["rules_answer"]["disposition"], "go_now")
        finally:
            slow.release.set()

    def test_apply_floor_never_lowers_any_pair(self):
        for m in h.SERVED:
            for f in h.SERVED:
                final, _ = h.apply_floor({"disposition": m}, {"disposition": f})
                self.assertEqual(h.RANK[final["disposition"]], max(h.RANK[m], h.RANK[f]))


def _raises(prompt):
    raise RuntimeError("CUDA out of memory")


class _Slow:
    def __init__(self):
        self.release = threading.Event()

    def generate(self, prompt):
        self.release.wait(5)
        return out("monitor_at_home")


class FallbackTest(unittest.TestCase):
    def assertFallback(self, r, reason_part):
        self.assertEqual(r["source"], "fallback")
        self.assertEqual(r["final"], r["rules_answer"])
        self.assertIsNone(r["model_answer"])
        self.assertIn(reason_part, r["fallback_reason"])

    def test_invalid_json_falls_back(self):
        self.assertFallback(run("disposition: go_now", "get_care_today"), "format: JSON does not parse")

    def test_text_outside_the_json_falls_back(self):
        self.assertFallback(run(out("get_care_today") + " because fever", "get_care_today"), "text outside")

    def test_missing_field_falls_back(self):
        self.assertFallback(run('{"disposition": "go_now", "danger_facts": []}', "get_care_today"), "fields missing")

    def test_unknown_disposition_falls_back(self):
        self.assertFallback(run(out("urgent"), "get_care_today"), "format: disposition is not one of the six")
        self.assertFallback(run(out("escalate"), "get_care_today"), "disposition not served: escalate")

    def test_follow_up_that_is_not_a_question_falls_back(self):
        self.assertFallback(run(out("need_one_more_answer", question="Tell me more."), "monitor_at_home"), "follow_up_question")
        self.assertFallback(run(out("monitor_at_home", question="Is it bad?"), "monitor_at_home"), "follow_up_question")

    def test_timeout_falls_back(self):
        slow = _Slow()
        try:
            r = run(slow.generate, "get_care_today", timeout_s=0.05)
        finally:
            slow.release.set()
        self.assertFallback(r, "model_timeout")

    def test_model_exception_falls_back(self):
        self.assertFallback(run(_raises, "get_care_today"), "model_error: RuntimeError")

    def test_no_model_loaded_falls_back(self):
        self.assertFallback(run(None, "monitor_at_home"), "model_unavailable")


class DangerFactsTest(unittest.TestCase):
    def test_danger_fact_not_in_the_story_is_rejected(self):
        r = run(out("go_now", ["is having a seizure"]), "get_care_today")
        self.assertEqual(r["source"], "fallback")
        self.assertIn("danger_facts not grounded", r["fallback_reason"])

    def test_fact_inside_a_longer_word_is_rejected(self):
        r = run(out("go_now", ["ever"]), "get_care_today")  # "ever" only appears inside "fever"
        self.assertEqual(r["source"], "fallback")

    def test_fact_quoted_from_the_story_passes(self):
        r = run(out("go_now", ["has a fever"]), "get_care_today")
        self.assertEqual((r["source"], r["final"]["danger_facts"]), ("model", ["has a fever"]))

    def test_true_field_pair_passes_and_false_one_is_rejected(self):
        case = intake(awake="not_waking")
        self.assertEqual(run(out("go_now", ["awake=not_waking"]), "go_now", case)["source"], "model")
        self.assertEqual(run(out("go_now", ["breathing=severe"]), "go_now", case)["source"], "fallback")


class RulesAndIntakeTest(unittest.TestCase):
    def test_rules_failure_returns_no_answer(self):
        def broken(_):
            raise SystemExit("esbuild not found")
        with self.assertRaises(h.RulesUnavailable):
            h.triage(intake(), generate=model(out("go_now")), rules=broken)

    def test_unknown_rules_kind_returns_no_answer(self):
        with self.assertRaises(h.RulesUnavailable):
            run(out("go_now"), "maybe")

    def test_bad_intake_is_rejected(self):
        for bad in (None, [], {"presentation": 3}, intake(awake="dead"), {**intake(), "name": "x"}):
            with self.assertRaises(h.IntakeError):
                run(out("go_now"), "go_now", bad)
        with self.assertRaises(h.IntakeError):
            run(out("go_now"), "go_now", language="fr")

    def test_rules_answer_uses_the_training_label_builder(self):
        case = intake("Is unwell.", awake="unknown", breathing="unknown")
        r = run(None, "need_one_more_answer", case, language="sw")
        self.assertEqual(r["rules_answer"], h.gen_cases.make_answer("sw", h.validate_intake(case), "need_one_more_answer"))


class ServerTest(unittest.TestCase):
    def test_import_loads_no_model_and_no_torch(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("eval_adapter", sys.modules)
        lazy = sm.LazyModel("adapter", None, loader=lambda: self.fail("loaded early"))
        self.assertEqual(lazy.state, "not_loaded")

    def test_no_gpu_gives_a_clear_message_and_the_rules_answer(self):
        fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False),
                                           backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)))
        lazy = sm.LazyModel("adapter", None)
        with mock.patch.dict(sys.modules, {"torch": fake_torch}):
            r = h.triage(intake(), generate=lazy, rules=rules("get_care_today"))
        self.assertEqual(r["source"], "fallback")
        self.assertIn("no GPU visible", r["fallback_reason"])
        self.assertEqual((lazy.state, lazy.error.startswith("NoGPU: no GPU visible")), ("failed", True))

    def test_http_health_and_triage(self):
        server = sm.make_server(model(out("monitor_at_home")), rules("get_care_today"), timeout_s=2, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            health = json.loads(urllib.request.urlopen(base + "/health", timeout=5).read())
            self.assertEqual((health["status"], health["batch_size"]), ("ok", 1))
            req = urllib.request.Request(base + "/v1/triage", data=json.dumps({"intake": intake()}).encode(),
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=5).read())
            self.assertEqual((r["source"], r["final"]["disposition"]), ("floor_raised", "get_care_today"))
            bad = urllib.request.Request(base + "/v1/triage", data=b"{not json")
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(err.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            server.model_executor.shutdown(wait=False)

    def test_http_rules_failure_is_503(self):
        def broken(_):
            raise SystemExit("esbuild not found")
        server = sm.make_server(model(out("go_now")), broken, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/v1/triage",
                                         data=json.dumps({"intake": intake()}).encode())
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(err.exception.code, 503)
        finally:
            server.shutdown()
            server.server_close()
            server.model_executor.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
