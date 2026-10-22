import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import results_table  # noqa: E402


def _run(root, name, meta=None, results=None, sealed=None, private=None):
    folder = root / name
    folder.mkdir()
    if meta is not None:
        (folder / "meta.json").write_text(json.dumps(meta))
    if results is not None:
        (folder / "results.json").write_text(json.dumps(results))
    if sealed is not None:
        (folder / "sealed.json").write_text(json.dumps(sealed))
    if private is not None:
        (folder / "private-v2.json").write_text(json.dumps(private))


def _print(root):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        results_table.print_tables(root)
    return out.getvalue()


class ResultsTableTest(unittest.TestCase):
    def test_tables_with_missing_sealed_and_multiple_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, seed, reward, sealed in (("a", 0, 0.0, 1.0), ("b", 1, 2.0, None)):
                _run(root, name, meta={"mode": "lora"},
                     results={"method": "sft", "seed": seed, "mean_reward": reward, "danger_missed": seed,
                              "valid_json_rate": 1.0, "rows": [{"private": "never print"}]},
                     sealed=None if sealed is None else {"mean_reward": sealed, "danger_missed": 0})
            output = _print(root)
        self.assertIn("| a | sft | lora | 0 | 0.0000 | 0 | 1.0000 | 0 | 1.0000 |", output)
        self.assertIn("| b | sft | lora | 1 | 2.0000 | 1 | — | — | 1.0000 |", output)
        self.assertIn("| sft | 2 | 1.0000 | 1.4142 | 0.5000 | 0.7071 | 1.0000 | 0.0000 | 0 | 0.0000 | 1.0000 | 0.0000 |", output)
        self.assertNotIn("never print", output)

    def test_family_table_groups_private_mean_and_range_over_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _run(root, "v2-full-sft-0.8b-s0", meta={"size": "0.8b", "mode": "full", "method": "sft", "seed": 0},
                 results={"method": "sft", "seed": 0},
                 private={"mean_reward": 0.5, "danger_missed": 1, "rows": [{"private": "never print"}]})
            _run(root, "v2-full-sft-0.8b-s1", meta={"size": "0.8b", "mode": "full", "method": "sft", "seed": 1},
                 results={"method": "sft", "seed": 1},
                 private={"mean_reward": 0.7, "danger_missed": 0, "rows": [{"private": "never print"}]})
            _run(root, "v3-lora-sft-2b-s0", meta={"size": "2b", "mode": "lora", "method": "sft", "seed": 0},
                 results={"method": "sft", "seed": 0})
            _run(root, "sft-0.8b-s0", meta={"size": "0.8b", "mode": "lora", "method": "sft", "seed": 0},
                 results={"method": "sft", "seed": 0})
            output = _print(root)
        self.assertIn("Private set (private-v2.json).", output)
        self.assertIn("| family | method | size | mode | runs | private runs | private seeds | private reward mean "
                      "| private reward range | private danger missed mean | private danger missed range |", output)
        self.assertIn("| — | sft | 0.8b | lora | 1 | 0 | 0 | — | — | — | — |", output)
        self.assertIn("| v2 | sft | 0.8b | full | 2 | 2 | 2 | 0.6000 | 0.2000 | 0.5000 | 1 |", output)
        self.assertIn("| v3 | sft | 2b | lora | 1 | 0 | 0 | — | — | — | — |", output)
        self.assertNotIn("never print", output)

    def test_family_table_counts_the_runs_it_averages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta = {"size": "4b", "mode": "lora", "method": "sft", "seed": 0}
            # two sweep variants share seed 0, one run has no private file, one private file has no numbers
            _run(root, "v3-lora-sft-4b-s0", meta=meta, results={"method": "sft", "seed": 0},
                 private={"mean_reward": 0.9, "danger_missed": 0})
            _run(root, "v3-lora-sft-4b-st400-s0", meta=meta, results={"method": "sft", "seed": 0},
                 private={"mean_reward": 0.7, "danger_missed": 2})
            _run(root, "v3-lora-sft-4b-s1", meta={**meta, "seed": 1}, results={"method": "sft", "seed": 1})
            _run(root, "v3-lora-sft-4b-s2", meta={**meta, "seed": 2}, results={"method": "sft", "seed": 2},
                 private={"n": 450})
            output = _print(root)
        self.assertIn("| v3 | sft | 4b | lora | 4 | 2 | 1 | 0.8000 | 0.2000 | 1 | 2 |", output)

    def test_private_only_and_method_less_folders_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _run(root, "v3-scored-only", private={"mean_reward": 0.5, "danger_missed": 3})
            _run(root, "v2x-lora-sft-0.8b-s0", meta={"size": "0.8b", "mode": "lora", "method": "sft", "seed": 0},
                 results={"method": "sft", "seed": 0}, private={"mean_reward": 0.4, "danger_missed": 1})
            output = _print(root)
        self.assertIn("| v3 | ? | — | — | 1 | 1 | 0 | 0.5000 | 0.0000 | 3 | 0 |", output)
        # a near-miss prefix is not a family
        self.assertIn("| — | sft | 0.8b | lora | 1 | 1 | 1 | 0.4000 | 0.0000 | 1 | 0 |", output)

    def test_family_table_splits_same_method_by_mode_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _run(root, "v3-lora-dpo-2b-s0", meta={"size": "2b", "mode": "lora", "method": "dpo", "seed": 0},
                 results={"method": "dpo", "seed": 0}, private={"mean_reward": 0.4, "danger_missed": 2})
            _run(root, "v3-lora-dpo-4b-s0", meta={"size": "4b", "mode": "lora", "method": "dpo", "seed": 0},
                 results={"method": "dpo", "seed": 0}, private={"mean_reward": 0.9, "danger_missed": 0})
            output = _print(root)
        self.assertIn("| v3 | dpo | 2b | lora | 1 | 1 | 1 | 0.4000 | 0.0000 | 2 | 0 |", output)
        self.assertIn("| v3 | dpo | 4b | lora | 1 | 1 | 1 | 0.9000 | 0.0000 | 0 | 0 |", output)


if __name__ == "__main__":
    unittest.main()
