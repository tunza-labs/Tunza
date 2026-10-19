import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import results_table  # noqa: E402


def test_tables_with_missing_sealed_and_multiple_seeds(tmp_path, capsys):
    for name, seed, reward, sealed in (("a", 0, 0.0, 1.0), ("b", 1, 2.0, None)):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "meta.json").write_text(json.dumps({"mode": "lora"}))
        (folder / "results.json").write_text(json.dumps({"method": "sft", "seed": seed,
            "mean_reward": reward, "danger_missed": seed, "valid_json_rate": 1.0,
            "rows": [{"private": "never print"}]}))
        if sealed is not None:
            (folder / "sealed.json").write_text(json.dumps({"mean_reward": sealed, "danger_missed": 0}))
    results_table.print_tables(tmp_path)
    output = capsys.readouterr().out
    assert "| a | sft | lora | 0 | 0.0000 | 0 | 1.0000 | 0 | 1.0000 |" in output
    assert "| b | sft | lora | 1 | 2.0000 | 1 | — | — | 1.0000 |" in output
    assert "| sft | 2 | 1.0000 | 1.4142 | 0.5000 | 0.7071 | 1.0000 | 0.0000 | 0 | 0.0000 | 1.0000 | 0.0000 |" in output
    assert "never print" not in output
