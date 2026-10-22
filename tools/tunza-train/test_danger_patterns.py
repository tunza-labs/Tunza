import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import danger_patterns as dp  # noqa: E402

# <repo>/tools/tunza-train -> <repo>. TUNZA_REPO points elsewhere when this folder is not in the repo.
ASSESSMENT_TS = Path(os.environ.get("TUNZA_REPO", HERE.parents[1])) / "lib" / "assessment.ts"


class DangerPatternsTest(unittest.TestCase):
    def test_patterns_equal_the_app_source(self):
        app = dp.app_sources(ASSESSMENT_TS.read_text(encoding="utf-8"))
        self.assertEqual(app, dp.SOURCES)
        self.assertEqual(list(app), [key for key, _, _ in dp.DANGER])

    def test_alternatives_rebuild_each_family(self):
        self.assertTrue(dp.FAMILIES["heavy-bleeding"].search("bleeding wont stop"))
        self.assertFalse(dp.FAMILIES["heavy-bleeding"].search("heavily"))
        self.assertEqual(len(dp.ALTERNATIVES), sum(len(alts) for _, _, alts in dp.DANGER))


if __name__ == "__main__":
    unittest.main()
