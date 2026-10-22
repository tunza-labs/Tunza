import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leakage_check as lc  # noqa: E402


def row(story, main_problem="fever", disposition="monitor_at_home", danger=None, follow_up=None):
    return {
        "intake": {"presentation": story, "mainProblem": main_problem, "awake": "yes"},
        "answer": {"disposition": disposition, "danger_facts": danger or [], "follow_up_question": follow_up},
    }


class CharGramsTest(unittest.TestCase):
    def test_case_and_spacing_do_not_change_grams(self):
        a = lc.char_grams("Fever  Today", 3)
        b = lc.char_grams("fever today", 3)
        self.assertEqual(lc.jaccard(a, b), 1.0)

    def test_short_text_is_one_gram(self):
        self.assertEqual(lc.char_grams("ab", 3), frozenset({"ab"}))

    def test_blank_text_has_no_grams(self):
        self.assertEqual(lc.char_grams("   ", 3), frozenset())


class JaccardTest(unittest.TestCase):
    def test_disjoint_is_zero(self):
        self.assertEqual(lc.jaccard(lc.char_grams("abc", 2), lc.char_grams("xyz", 2)), 0.0)

    def test_empty_side_is_zero(self):
        self.assertEqual(lc.jaccard(frozenset(), lc.char_grams("abc", 2)), 0.0)

    def test_partial_overlap(self):
        # {ab, bc, cd} and {ab, be, ef}: 1 shared of 5 distinct
        self.assertAlmostEqual(lc.jaccard(lc.char_grams("abcd", 2), lc.char_grams("abef", 2)), 0.2)


class CheckTest(unittest.TestCase):
    def test_nearest_is_the_most_similar_row_not_the_first(self):
        train = [row("headache since monday"), row("child has fever and fits")]
        result = lc.check(train, [row("child has fever and fitting")])
        self.assertEqual(result["rows"][0]["nearest_train_index"], 1)
        # 2-grams: {ab, bc, cd} vs {ab, bc, ce}: 2 shared of 4 distinct
        pinned = lc.check([row("abce")], [row("abcd")], n=2)["rows"][0]
        self.assertEqual(pinned["similarity"], 0.5)

    def test_tie_keeps_the_first_train_row(self):
        result = lc.check([row("same story"), row("same story")], [row("same story")])["rows"][0]
        self.assertEqual((result["nearest_train_index"], result["similarity"]), (0, 1.0))

    def test_threshold_is_inclusive_like_the_generator(self):
        # 2 shared of 4 distinct 2-grams: exactly 0.5
        train, test = [row("abce")], [row("abcd")]
        self.assertTrue(lc.check(train, test, n=2, threshold=0.5)["rows"][0]["near_duplicate"])
        self.assertFalse(lc.check(train, test, n=2, threshold=0.51)["rows"][0]["near_duplicate"])
        self.assertTrue(lc.check([row("same story")], [row("same story")], threshold=1.0)["rows"][0]["near_duplicate"])

    def test_story_only_intake_is_never_an_identical_structure(self):
        bare = {"intake": {"presentation": "x"}, "answer": {"disposition": "go_now"}}
        other = {"intake": {"presentation": "y"}, "answer": {"disposition": "go_now"}}
        self.assertFalse(lc.check([bare], [other])["rows"][0]["identical_structure"])

    def test_danger_fact_order_does_not_change_the_answer(self):
        result = lc.check([row("a", danger=["x", "y"])], [row("b", danger=["y", "x"])])["rows"][0]
        self.assertTrue(result["identical_answer"])

    def test_no_nearest_reason_tells_blank_from_no_match(self):
        rows = lc.check([row("abc")], [row(""), row("xyz")])["rows"]
        self.assertEqual([r["no_nearest_reason"] for r in rows], ["blank_story", "no_match"])

    def test_whitespace_story_is_counted_apart(self):
        report = lc.check([row("abc")], [row("  \t"), row("")])
        self.assertEqual((report["blank_story_test_rows"], report["whitespace_story_test_rows"]), (2, 1))

    def test_identical_structure_ignores_story_text(self):
        result = lc.check([row("alpha beta gamma")], [row("completely different words")])["rows"][0]
        self.assertTrue(result["identical_structure"])
        self.assertTrue(result["identical_answer"])
        self.assertFalse(result["near_duplicate"])

    def test_intake_field_difference_breaks_structure_but_not_answer(self):
        result = lc.check([row("story one", main_problem="cough")], [row("story two", main_problem="fever")])["rows"][0]
        self.assertFalse(result["identical_structure"])
        self.assertTrue(result["identical_answer"])

    def test_answer_difference_breaks_both(self):
        result = lc.check([row("story one", disposition="go_now")], [row("story one")])["rows"][0]
        self.assertFalse(result["identical_structure"])
        self.assertFalse(result["identical_answer"])

    def test_blank_story_has_no_similarity_but_still_matches_structure(self):
        result = lc.check([row("")], [row("")])["rows"][0]
        self.assertEqual(result["similarity"], 0.0)
        self.assertFalse(result["near_duplicate"])
        self.assertTrue(result["identical_structure"])

    def test_shares_and_counts(self):
        train = [row("the child has a fever and is fitting")]
        test = [row("the child has a fever and is fitting"), row("a man with a broken arm", main_problem="fracture", disposition="get_care_today")]
        report = lc.check(train, test)
        self.assertEqual(report["n_test"], 2)
        self.assertEqual(report["near_duplicate_rows"], 1)
        self.assertEqual(report["share_near_duplicate"], 0.5)
        self.assertEqual(report["share_identical_structure"], 0.5)
        self.assertEqual(report["share_identical_answer"], 0.5)

    def test_empty_test_file_gives_no_shares(self):
        report = lc.check([row("story")], [])
        self.assertEqual(report["n_test"], 0)
        self.assertIsNone(report["share_near_duplicate"])


class MainTest(unittest.TestCase):
    def test_writes_full_report_with_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            train_path = tmp / "train.jsonl"
            test_path = tmp / "test.jsonl"
            out_path = tmp / "report.json"
            train_path.write_text(json.dumps(row("secret train story")) + "\n", encoding="utf-8")
            test_path.write_text(json.dumps(row("secret test story")) + "\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                self.assertEqual(lc.main(["--train", str(train_path), "--test", str(test_path), "--out", str(out_path)]), 0)
            text = out_path.read_text(encoding="utf-8")
            report = json.loads(text)
            self.assertEqual(report["n_test"], 1)
            self.assertEqual(len(report["rows"]), 1)
            self.assertEqual(report["test_sha256"], lc.sha256_file(test_path))
            self.assertFalse(report["test_in_manifest"])
            self.assertIn("warning", err.getvalue())
            # indices and scores only: no story text in the report or on stdout, no rows on stdout
            self.assertNotIn("secret", text)
            self.assertNotIn("secret", out.getvalue())
            self.assertNotIn('"rows"', out.getvalue())

    def test_manifest_sealed_file_is_recognised(self):
        sealed = Path(lc.__file__).resolve().parent / "data" / "v3" / "triage-sealed.jsonl"
        self.assertIn(lc.sha256_file(sealed), lc.manifest_sealed_hashes())

    def test_rejects_n_below_one(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            lc.main(["--train", "x.jsonl", "--test", "y.jsonl", "--n", "0"])

    def test_rejects_threshold_outside_zero_to_one(self):
        for value in ("0", "1.5"):
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                lc.main(["--train", "x.jsonl", "--test", "y.jsonl", "--threshold", value])


if __name__ == "__main__":
    unittest.main()
