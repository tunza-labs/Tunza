import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import negation_check as nc


def row(presentation: str, disposition: str, **intake) -> dict:
    base = {"awake": "alert", "breathing": "fine", "drinking": "yes", "duration": "today",
            "mainProblem": "other", "presentation": presentation, "who": "household_adult"}
    base.update(intake)
    return {"answer": {"disposition": disposition, "danger_facts": [], "follow_up_question": None}, "intake": base}


class NegationCueTests(unittest.TestCase):
    def negated(self, text: str, term: str) -> bool:
        hits = [h for h in nc.find_hits(text) if h.term == term]
        self.assertTrue(hits, f"no hit for {term!r} in {text!r}")
        return hits[0].negated

    def test_english_negations(self):
        self.assertTrue(self.negated("no seizure today", "seizure"))
        self.assertTrue(self.negated("not fitting at all", "fitting"))
        self.assertTrue(self.negated("did not stop breathing", "stop breathing"))
        self.assertTrue(self.negated("has never had a seizure", "seizure"))

    def test_swahili_negations(self):
        self.assertTrue(self.negated("hakuna kifafa", "kifafa"))
        self.assertTrue(self.negated("hajakuwa na degedege", "degedege"))

    def test_positive_mentions_are_not_negated(self):
        self.assertFalse(self.negated("she is having a seizure", "seizure"))
        self.assertFalse(self.negated("hapumui kabisa", "hapumui"))
        self.assertFalse(self.negated("hajitambui", "hajitambui"))
        self.assertFalse(self.negated("he won't wake up", "won't wake"))

    def test_clause_break_stops_the_cue(self):
        self.assertFalse(self.negated("no fever, seizure started", "seizure"))
        self.assertFalse(self.negated("no food but kifafa", "kifafa"))

    def test_cue_outside_window_is_ignored(self):
        self.assertFalse(self.negated("no sleep and no food for two days then seizure", "seizure"))


class DecideMirrorTests(unittest.TestCase):
    def test_regex_fires_on_negated_keyword(self):
        keys, sleepy = nc.decide_danger_keys(row("no seizure", "monitor_at_home")["intake"])
        self.assertEqual(keys, ["dangerSeizure"])
        self.assertFalse(sleepy)

    def test_structured_fields_add_keys(self):
        keys, _ = nc.decide_danger_keys({"awake": "not_waking", "presentation": "no seizure"})
        self.assertEqual(keys, ["dangerNotWaking", "dangerSeizure"])

    def test_heavy_bleeding_needs_injury_and_heavy_word(self):
        intake = {"mainProblem": "injury", "presentation": "not bleeding heavily from the cut"}
        keys, _ = nc.decide_danger_keys(intake)
        self.assertEqual(keys, ["dangerHeavyBleeding"])

    def test_sleepy_difficult_branch_reported(self):
        _, sleepy = nc.decide_danger_keys({"awake": "sleepy", "breathing": "difficult", "presentation": ""})
        self.assertTrue(sleepy)


class AnalyseTests(unittest.TestCase):
    def test_false_go_negated_only(self):
        found = nc.analyse(row("no seizure", "monitor_at_home"))
        self.assertEqual(found["status"], "FALSE_GO")
        self.assertEqual(found["basis"], "negated-only")
        self.assertEqual(found["negated_terms"], ["seizure"])

    def test_false_go_swahili_convulsion_negated(self):
        found = nc.analyse(row("hakuna kifafa", "get_care_today"))
        self.assertEqual(found["status"], "FALSE_GO")

    def test_negated_stopped_breathing_is_agree_when_regex_silent(self):
        found = nc.analyse(row("did not stop breathing", "monitor_at_home"))
        self.assertEqual(found["status"], "AGREE")
        self.assertEqual(found["basis"], "none")

    def test_miss_when_label_go_now_but_regex_silent(self):
        found = nc.analyse(row("no fits", "go_now"))
        self.assertEqual(found["status"], "MISS")

    def test_mixed_when_positive_keyword_present(self):
        found = nc.analyse(row("no fits, but seizure now", "go_now"))
        self.assertEqual(found["basis"], "mixed")
        self.assertEqual(found["status"], "AGREE")

    def test_structured_basis_when_intake_fires(self):
        found = nc.analyse(row("no seizure", "go_now", awake="not_waking"))
        self.assertEqual(found["basis"], "structured")
        self.assertEqual(found["status"], "AGREE")

    def test_no_negated_keyword_returns_none(self):
        self.assertIsNone(nc.analyse(row("seizure, not waking", "go_now")))
        self.assertIsNone(nc.analyse(row("fever for two days", "monitor_at_home")))


class TableTests(unittest.TestCase):
    def test_end_to_end_on_synthetic_file_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "triage-sealed.jsonl"
            rows = [row("no seizure", "monitor_at_home"),
                    row("she is having a seizure", "go_now"),
                    row("fever", "monitor_at_home")]
            src.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            before = src.read_bytes()
            out = Path(tmp) / "out" / "table.md"
            found, totals = nc.build([("test", "synthetic.jsonl", src)])
            nc.write_table(out, found, totals, [("test", "synthetic.jsonl", src)])
            self.assertEqual(src.read_bytes(), before)
            self.assertEqual(len(found), 1)
            self.assertEqual(totals[("synthetic.jsonl", "FALSE_GO")], 1)
            text = out.read_text(encoding="utf-8")
            self.assertIn("| FALSE_GO | negated-only | synthetic.jsonl | 1 | dangerSeizure | monitor_at_home | seizure |", text)

    def test_pipe_in_snippet_is_escaped(self):
        self.assertEqual(nc.md_cell("a|b\nc"), "a\\|b c")

    def test_identical_sources_are_scanned_once(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("sys.stdout"):
            a, b = Path(tmp) / "a.jsonl", Path(tmp) / "b.jsonl"
            a.write_text("{}\n", encoding="utf-8")
            b.write_text("{}\n", encoding="utf-8")
            self.assertEqual(nc.unique_inputs([("test", "a", a), ("test", "b", b)]), [("test", "a", a)])

    def test_missing_private_file_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("sys.stderr") as err:
            with self.assertRaises(SystemExit):
                nc.main(["--out", str(Path(tmp) / "t.md"), "--private", str(Path(tmp) / "none.jsonl")])
        self.assertIn("--skip-private", "".join(c.args[0] for c in err.write.call_args_list))


class OverlapTests(unittest.TestCase):
    def test_overlapping_forms_give_one_hit(self):
        self.assertEqual([h.term for h in nc.find_hits("no seizures")], ["seizure"])
        self.assertEqual([h.term for h in nc.find_hits("not stopped breathing")], ["stopped breathing"])

    def test_extra_form_does_not_count_as_a_positive_app_keyword(self):
        found = nc.analyse(row("no fitting, she has fits", "monitor_at_home"))
        self.assertEqual(found["basis"], "negated-only")


if __name__ == "__main__":
    unittest.main()
