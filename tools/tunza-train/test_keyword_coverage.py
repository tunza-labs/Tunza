import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_coverage as kc  # noqa: E402

MIN_ROWS = kc.MIN_ROWS


class DangerKeywordCoverage(unittest.TestCase):
    def test_min_rows_is_fifteen(self):
        # lowering the floor would hide the gap this tool reports
        self.assertEqual(kc.MIN_ROWS, 15)

    def test_threshold_catches_a_phrase_with_one_row_too_few(self):
        rows = [
            {"intake": {"presentation": "she is fitting again"}} for _ in range(MIN_ROWS - 1)
        ] + [{"intake": {"presentation": "he has a rash"}}]
        thin = kc.thin_alternatives(rows)
        self.assertIn(("seizure", "fitting", MIN_ROWS - 1), thin)

    def test_fifteen_rows_is_not_thin(self):
        rows = [{"intake": {"presentation": "fitting"}} for _ in range(15)]
        self.assertNotIn("fitting", [alt for _, alt, _ in kc.thin_alternatives(rows)])

    def test_alternatives_match_like_the_app(self):
        # the app needs "bleeding" before "heavily", and won'?t matches "wont"
        counts = kc.count_alternatives([{"intake": {"presentation": "heavily, he wont wake"}}])
        self.assertEqual(counts[("heavy-bleeding", "bleeding (a lot|heavily|won'?t stop)")], 0)
        self.assertEqual(counts[("not-waking", "won'?t wake")], 1)

    def test_only_the_presentation_is_matched(self):
        # the app matches prose on the presentation only, not other intake values
        counts = kc.count_alternatives([{"intake": {"presentation": "fever", "mainProblem": "fitting"}}])
        self.assertEqual(counts[("seizure", "fitting")], 0)

    def test_cli_exits_one_on_a_gap_and_zero_when_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "train.jsonl"
            path.write_text(json.dumps({"intake": {"presentation": "fitting"}}) + "\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(kc.main(["--train", str(path)]), 1)
            self.assertIn("fitting", out.getvalue())
            stories = [alt.replace("'?", "'").replace("(a lot|heavily|won't stop)", "a lot") for _, alt in kc.ALTERNATIVES]
            path.write_text("".join(json.dumps({"intake": {"presentation": " ".join(stories)}}) + "\n"
                                    for _ in range(MIN_ROWS)), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(kc.main(["--train", str(path)]), 0)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(kc.main(["--train", str(Path(tmp) / "missing.jsonl")]), 2)


if __name__ == "__main__":
    unittest.main()
