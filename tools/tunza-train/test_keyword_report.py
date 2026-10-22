import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyword_report as kr  # noqa: E402

STORIES = (
    ("Baby is unconscious and not breathing", "go_now"),
    ("She had a seizure this morning", "go_now"),
    ("Mild cough for two days", "monitor_at_home"),
    ("Cut finger, damu nyingi", "escalate"),
    ("Chest pain and sweating", "go_now"),
)
# Row indexes each run misses. run-b misses row 0 with an invalid answer, the others with stopped=danger_under_triage.
MISSES = {"run-a": {1, 3, 4}, "run-b": {0}, "run-c": {1, 3}, "run-d": {0, 1}, "run-e": set()}
FILE_MISSED = {"run-a": 3, "run-b": 1, "run-c": 2, "run-d": 2, "run-e": 1}


def _write_fixture(root):
    sealed = root / "sealed.jsonl"
    sealed.write_text("".join(
        json.dumps({"intake": {"presentation": story}, "answer": {"disposition": label}}) + "\n"
        for story, label in STORIES), encoding="utf-8")
    runs = root / "runs"
    for name, missed in MISSES.items():
        rows = []
        for index, (_, label) in enumerate(STORIES):
            if index not in missed:
                rows.append({"expected": label, "predicted": label, "reward": 1.0, "stopped": None})
            elif name == "run-b":
                rows.append({"expected": label, "predicted": "invalid", "reward": -1.0, "stopped": None})
            else:
                rows.append({"expected": label, "predicted": "monitor_at_home", "reward": -1.0,
                             "stopped": "danger_under_triage"})
        folder = runs / name
        folder.mkdir(parents=True)
        (folder / "private-v2.json").write_text(json.dumps(
            {"danger_cases": 4, "danger_missed": FILE_MISSED[name], "rows": rows}), encoding="utf-8")
    return runs, sealed


class KeywordReportTest(unittest.TestCase):
    def test_families_match_app_patterns_case_insensitively(self):
        self.assertEqual(kr.families_in("Baby is UNCONSCIOUS"), ["not-waking"])
        self.assertEqual(kr.families_in("ana degedege na kifafa"), ["seizure"])
        self.assertEqual(kr.families_in("bleeding heavily from the leg"), ["heavy-bleeding"])
        self.assertEqual(kr.families_in("Mild cough"), [])

    def test_report_counts_and_lists_rows_missed_by_three_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs, sealed = _write_fixture(Path(tmp))
            report = kr.build_report(runs, sealed, min_runs=3)
        self.assertIn("| run-a | 3 | 0 | 1 | 0 | 0 | 1 | 1 | 3 | ok |", report)
        self.assertIn("| run-b | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 1 | ok |", report)
        self.assertIn("| run-e | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | MISMATCH |", report)
        self.assertIn("| 1 | go_now | 3 of 5 | seizure | She had a seizure this morning |", report)
        self.assertNotIn("Cut finger", report)
        self.assertNotIn("Mild cough", report)

    def test_row_alignment_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs, sealed = _write_fixture(Path(tmp))
            path = runs / "run-a" / "private-v2.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["rows"][0]["expected"] = "monitor_at_home"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                kr.build_report(runs, sealed, min_runs=3)

    def test_row_count_mismatch_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs, sealed = _write_fixture(Path(tmp))
            path = runs / "run-a" / "private-v2.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["rows"] = data["rows"][:4]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "4 rows, sealed file has 5"):
                kr.build_report(runs, sealed, min_runs=3)

    def test_folder_counts_blank_lines_and_empty_story_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs, sealed = _write_fixture(Path(tmp))
            (runs / "not-scored").mkdir()
            sealed.write_text(sealed.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
            report = kr.build_report(runs, sealed, min_runs=6)
        self.assertIn("Run folders: 6. Runs with private-v2.json: 5. Folders without it: 1.", report)
        self.assertIn("## Rows missed by 6 or more runs\n\nNone.", report)

    def test_run_scored_on_another_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs, sealed = _write_fixture(Path(tmp))
            path = runs / "run-c" / "private-v2.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["file"] = "private\\other-sealed.jsonl"
            path.write_text(json.dumps(data), encoding="utf-8")
            path = runs / "run-d" / "private-v2.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["file"] = str(sealed)
            path.write_text(json.dumps(data), encoding="utf-8")
            report = kr.build_report(runs, sealed, min_runs=3)
        self.assertIn("| run-c | 2 | 0 | 1 | 0 | 0 | 1 | 0 | 2 | OTHER FILE |", report)
        self.assertIn("| run-d | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 2 | ok |", report)

    def test_same_file_matches_a_relative_tail(self):
        sealed = Path("C:/x/tunza-train/private/triage-sealed.jsonl")
        self.assertTrue(kr.same_file("private\\triage-sealed.jsonl", sealed))
        self.assertFalse(kr.same_file("data\\v3\\triage-sealed.jsonl", sealed))


if __name__ == "__main__":
    unittest.main()
