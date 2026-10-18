"""Tests for the code-owned Tunza reward. Reads Tunza sources. Does not write them."""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tunza_reward as reward

REPO = Path(__file__).resolve().parents[3]
TUNZA_CONTRACT = REPO / "lib/clinical/contract.ts"
TUNZA_RECONCILE = REPO / "lib/clinical/reconcile.ts"
MODULE_PATH = Path(__file__).with_name("tunza_reward.py")
_DISPOSITIONS = re.compile(r"export const DISPOSITIONS = \[(.*?)\] as const", re.S)
_QUOTED = re.compile(r'"([^"]+)"')


def _case(expected: str, presentation: str = reward.DANGER_TOKEN) -> dict:
    return {"presentation": presentation, "breathing": "severe"}


class TestFormatGate(unittest.TestCase):
    def test_malformed_prose_and_unknown_are_minimum(self):
        perfect = reward.render_output("go_now", [reward.DANGER_TOKEN], None)
        samples = [
            "not json",
            "",
            "go now",
            perfect + "\nthanks",
            "The answer is " + perfect,
            "```json\n" + perfect + "\n```",
            '{"disposition":"go_now"}',
            reward.render_output("urgent", [], None),
            reward.render_output("see-clinic", [], None),
            reward.render_output("self-care", [], None),
            '{"disposition":"go_now","danger_facts":[],"follow_up_question":null,"extra":1}',
            '{"disposition":"go_now","danger_facts":"none","follow_up_question":null}',
            '{"disposition":"go_now","danger_facts":[],"follow_up_question":1}',
            '{"disposition":"send_them_home","danger_facts":[],"follow_up_question":null}',
            '{"disposition":"go_now","danger_facts":[],"next_question":null}',
            '{"disposition":"Go_Now","danger_facts":[],"follow_up_question":null}',
            "null",
            "[]",
        ]
        for sample in samples:
            result = reward.score(sample, expected="go_now", case_input=_case("go_now"))
            self.assertEqual(result.reward, reward.MINIMUM_REWARD, sample)
            self.assertEqual(result.stopped, "format", sample)

    def test_non_string_is_minimum(self):
        result = reward.score(None, expected="monitor_at_home")
        self.assertEqual(result.reward, -1.0)
        self.assertEqual(result.format_error, "output is not a string")

    def test_whitespace_around_one_object_is_valid(self):
        raw = "\n  " + reward.render_output("monitor_at_home", [], None) + "\n"
        result = reward.score(raw, expected="monitor_at_home")
        self.assertEqual(result.reward, 1.0)
        self.assertIsNone(result.stopped)


class TestDangerFloor(unittest.TestCase):
    def test_raw_under_call_stays_minimum_after_floor_would_raise(self):
        raw = reward.render_output("monitor_at_home", [reward.DANGER_TOKEN], "What else?")
        result = reward.score(raw, expected="go_now", case_input=_case("go_now"))
        self.assertEqual(result.reward, -1.0)
        self.assertEqual(result.raw_disposition, "monitor_at_home")
        self.assertEqual(result.reconciled_disposition, "go_now")
        self.assertEqual(result.disagreement_reason, "candidate_below_floor")
        self.assertEqual(result.stopped, "danger_under_triage")
        self.assertEqual(result.follow_up_penalty, 0.0)
        self.assertEqual(result.danger_facts_penalty, 0.0)
        raised = reward.render_output("go_now", [reward.DANGER_TOKEN], None)
        raised_score = reward.score(raised, expected="go_now", case_input=_case("go_now"))
        self.assertEqual(raised_score.reward, 1.0)
        self.assertNotEqual(result.reward, raised_score.reward)

    def test_every_lower_rank_on_danger_is_minimum(self):
        for expected in ("go_now", "escalate"):
            for predicted in ("get_care_today", "need_one_more_answer", "abstain", "monitor_at_home"):
                raw = reward.constant_output(predicted)
                result = reward.score(raw, expected=expected, case_input=_case(expected))
                self.assertEqual(result.reward, -1.0, f"{expected} <- {predicted}")
                self.assertEqual(result.reconciled_disposition, expected)

    def test_same_rank_is_not_under_triage_and_is_not_graded_after_reconcile(self):
        raw = reward.render_output("escalate", [reward.DANGER_TOKEN], None)
        result = reward.score(raw, expected="go_now", case_input=_case("go_now"))
        self.assertEqual(result.reward, 0.8)
        self.assertEqual(result.reconciled_disposition, "go_now")
        self.assertEqual(result.disagreement_reason, "candidate_not_approved")
        self.assertIsNone(result.stopped)

    def test_over_call_is_not_rewritten_into_a_match(self):
        raw = reward.render_output("go_now", [], None)
        result = reward.score(raw, expected="monitor_at_home", case_input=_case("monitor_at_home"))
        self.assertEqual(result.reward, -0.5)
        self.assertEqual(result.raw_disposition, "go_now")
        self.assertEqual(result.reconciled_disposition, "monitor_at_home")
        self.assertEqual(result.disagreement_reason, "candidate_not_approved")

    def test_non_danger_under_call_is_penalised_not_minimum(self):
        raw = reward.constant_output("monitor_at_home")
        result = reward.score(raw, expected="get_care_today")
        self.assertEqual(result.reward, -0.6)
        self.assertIsNone(result.stopped)


class TestAskCredit(unittest.TestCase):
    def test_exact_ask_is_full_credit(self):
        raw = reward.constant_output("need_one_more_answer")
        result = reward.score(raw, expected="need_one_more_answer")
        self.assertEqual(result.reward, 1.0)

    def test_abstain_on_incomplete_input_is_partial_credit(self):
        raw = reward.render_output("abstain", [], None)
        result = reward.score(raw, expected="need_one_more_answer")
        self.assertEqual(result.reward, 0.3)

    def test_bad_question_costs_two_tenths_and_does_not_fail_format(self):
        missing = reward.render_output("need_one_more_answer", [], None)
        doubled = reward.render_output("need_one_more_answer", [], "What? And this?")
        too_long = reward.render_output("need_one_more_answer", [], ("x" * 200) + "?")
        exact_limit = reward.render_output("need_one_more_answer", [], ("x" * 199) + "?")
        self.assertEqual(reward.score(missing, expected="need_one_more_answer").reward, 0.8)
        self.assertEqual(reward.score(doubled, expected="need_one_more_answer").reward, 0.8)
        self.assertEqual(reward.score(too_long, expected="need_one_more_answer").reward, 0.8)
        self.assertEqual(reward.score(exact_limit, expected="need_one_more_answer").reward, 1.0)
        self.assertIsNone(reward.score(missing, expected="need_one_more_answer").stopped)

    def test_question_on_a_known_answer_is_penalised(self):
        raw = reward.render_output("monitor_at_home", [], "What else?")
        result = reward.score(raw, expected="monitor_at_home")
        self.assertEqual(result.reward, 0.8)
        asked = reward.constant_output("need_one_more_answer")
        self.assertEqual(reward.score(asked, expected="monitor_at_home").reward, -0.2)

    def test_abstain_is_not_an_expected_label(self):
        with self.assertRaises(ValueError):
            reward.score(reward.constant_output("abstain"), expected="abstain")


class TestGrounding(unittest.TestCase):
    def test_empty_facts_on_danger_cost_one_tenth(self):
        raw = reward.render_output("go_now", [], None)
        result = reward.score(raw, expected="go_now", case_input=_case("go_now"))
        self.assertEqual(result.reward, 0.9)
        self.assertEqual(result.danger_facts_penalty, -0.1)

    def test_ungrounded_facts_cost_two_tenths_once(self):
        raw = reward.render_output("monitor_at_home", ["missing-one", "missing-two"], None)
        result = reward.score(raw, expected="monitor_at_home", case_input=_case("monitor_at_home"))
        self.assertEqual(result.reward, 0.8)
        self.assertEqual(result.danger_facts_penalty, -0.2)

    def test_substring_and_field_match_are_grounded(self):
        by_text = reward.render_output("go_now", ["Danger-Token"], None)
        by_field = reward.render_output("go_now", ["breathing=severe"], None)
        text_score = reward.score(
            by_text,
            expected="go_now",
            case_input={"presentation": "seen danger-token here"},
        )
        field_score = reward.score(
            by_field,
            expected="go_now",
            case_input={"intake": {"breathing": "severe"}},
        )
        self.assertEqual(text_score.reward, 1.0)
        self.assertEqual(field_score.reward, 1.0)

    def test_inexact_field_match_is_ungrounded(self):
        raw = reward.render_output("go_now", ["breathing=Severe"], None)
        result = reward.score(raw, expected="go_now", case_input={"breathing": "severe"})
        self.assertEqual(result.reward, 0.8)


class TestConstantPolicies(unittest.TestCase):
    def test_go_now_and_always_ask_lose_to_the_reference_policy(self):
        cases = reward.reference_cases()
        self.assertEqual(len(cases), 20)
        reference = reward.score_policy(cases, reward.reference_output)
        go_now = reward.score_policy(cases, lambda _case: reward.constant_output("go_now"))
        always_ask = reward.score_policy(
            cases,
            lambda _case: reward.constant_output("need_one_more_answer"),
        )
        monitor = reward.score_policy(cases, lambda _case: reward.constant_output("monitor_at_home"))
        care = reward.score_policy(cases, lambda _case: reward.constant_output("get_care_today"))
        reference_mean = reward.mean_reward(reference)
        go_now_mean = reward.mean_reward(go_now)
        ask_mean = reward.mean_reward(always_ask)
        monitor_mean = reward.mean_reward(monitor)
        care_mean = reward.mean_reward(care)
        self.assertAlmostEqual(reference_mean, 1.0, places=9)
        self.assertAlmostEqual(go_now_mean, reward.CONSTANT_POLICY_MEANS["go_now"], places=9)
        self.assertAlmostEqual(ask_mean, reward.CONSTANT_POLICY_MEANS["need_one_more_answer"], places=9)
        self.assertAlmostEqual(monitor_mean, reward.CONSTANT_POLICY_MEANS["monitor_at_home"], places=9)
        self.assertAlmostEqual(care_mean, reward.CONSTANT_POLICY_MEANS["get_care_today"], places=9)
        self.assertLess(go_now_mean, 0.1)
        self.assertLess(go_now_mean, reference_mean)
        self.assertLess(ask_mean, reference_mean)
        self.assertLess(ask_mean, 0)
        self.assertLess(monitor_mean, 0)
        for item in reference + go_now + always_ask + monitor + care:
            self.assertGreaterEqual(item.reward, -1.0)
            self.assertLessEqual(item.reward, 1.0)


class TestRankAndContract(unittest.TestCase):
    def test_rank_matches_reconcile_and_aliases_fail_format(self):
        parsed = reward.parse_rank_source(TUNZA_RECONCILE.read_text())
        for name in reward.DISPOSITIONS:
            self.assertEqual(reward.RANK[name], parsed[name], name)
        for alias in reward.LEGACY_ALIASES:
            self.assertIn(alias, parsed)
            self.assertNotIn(alias, reward.DISPOSITIONS)
            raw = json.dumps(
                {
                    "disposition": alias,
                    "danger_facts": [],
                    "follow_up_question": None,
                }
            )
            result = reward.score(raw, expected="go_now")
            self.assertEqual(result.reward, -1.0)
            self.assertEqual(result.stopped, "format")

    def test_dispositions_match_contract_six(self):
        body = _DISPOSITIONS.search(TUNZA_CONTRACT.read_text())
        self.assertIsNotNone(body)
        found = tuple(_QUOTED.findall(body.group(1)))
        self.assertEqual(found, reward.DISPOSITIONS)


class TestNoJevImport(unittest.TestCase):
    def test_module_imports_neither_typesafe_nor_jev_nor_dpi(self):
        tree = ast.parse(MODULE_PATH.read_text())
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
            elif isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                self.assertNotIn(name, {"__import__", "import_module"})
        banned = ("typesafe", "jev", "dpi", "tunza")
        for name in imported:
            lowered = name.lower()
            for item in banned:
                self.assertNotIn(item, lowered)
        allowed = {"__future__", "json", "re", "dataclasses"}
        self.assertTrue(imported)
        for name in imported:
            self.assertIn(name, allowed)
        self.assertIs(reward.JEV_DERIVED, False)


class TestLanguageBreakdown(unittest.TestCase):
    def test_languages_are_reported_apart(self):
        rows = [
            ("en", "go_now", reward.render_output("go_now", [reward.DANGER_TOKEN], None)),
            ("English", "monitor_at_home", reward.constant_output("monitor_at_home")),
            ("Kiswahili", "go_now", reward.constant_output("monitor_at_home")),
            ("code_switch", "get_care_today", reward.constant_output("get_care_today")),
        ]
        results = [
            reward.score(raw, expected=expected, case_input=_case(expected), language=language)
            for language, expected, raw in rows
        ]
        report = reward.summarize_by_language(results)
        self.assertEqual(set(report), {"by_language"})
        by_language = report["by_language"]
        self.assertEqual(set(by_language), {"en", "sw", "code-switch"})
        self.assertEqual(by_language["en"]["n"], 2)
        self.assertEqual(by_language["en"]["mean"], 1.0)
        self.assertEqual(by_language["sw"]["n"], 1)
        self.assertEqual(by_language["sw"]["mean"], -1.0)
        self.assertEqual(by_language["code-switch"]["mean"], 1.0)
        pooled = sum(item.reward for item in results) / len(results)
        self.assertNotEqual(by_language["sw"]["mean"], pooled)
        self.assertNotIn("pooled", report)


class TestBaseOutputsSkipped(unittest.TestCase):
    def test_t7_waiting_on_base_outputs(self):
        self.skipTest(reward.T7_SKIP_REASON)


if __name__ == "__main__":
    unittest.main()
