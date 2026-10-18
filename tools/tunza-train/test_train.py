import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluate as ev  # noqa: E402
import train  # noqa: E402

DEV = Path(__file__).parent / "data" / "triage-dev.jsonl"
TRAIN = Path(__file__).parent / "data" / "triage-train.jsonl"


def test_data_is_the_expected_size_and_has_no_math_rows():
    assert len(ev.read_rows(TRAIN)) == 300 and len(ev.read_rows(DEV)) == 96
    for row in ev.read_rows(DEV):
        assert row["answer"]["disposition"] in ev.DISPOSITIONS and "intake" in row


def test_a_perfect_model_scores_one_and_misses_no_danger():
    rows = ev.read_rows(DEV)
    perfect = {ev.make_prompt(r["intake"]): ev.answer_text(r["answer"]) for r in rows}
    res = ev.evaluate(rows, lambda p: perfect[p])
    assert res["mean_reward"] == 1.0 and res["danger_missed"] == 0 and res["valid_json_rate"] == 1.0


def test_garbage_scores_minimum_and_counts_as_a_missed_danger():
    rows = ev.read_rows(DEV)
    res = ev.evaluate(rows, lambda p: "I think they should rest")
    assert res["mean_reward"] == -1.0 and res["valid_json_rate"] == 0.0
    assert res["danger_missed"] == res["danger_cases"] > 0


def test_always_go_now_loses():
    rows = ev.read_rows(DEV)
    base = ev.constant_baselines(rows)
    assert base["go_now"] < 0 and all(v < 0.5 for v in base.values())


def test_cost_weights_average_one_and_rank_danger_highest():
    rows = ev.read_rows(TRAIN)
    w = train.row_weights(rows, "sft_cost")
    assert abs(sum(w) / len(w) - 1.0) < 1e-9
    by = {}
    for r, x in zip(rows, w):
        by[r["answer"]["disposition"]] = x
    assert by["go_now"] > by["get_care_today"] > by["monitor_at_home"]
    assert set(train.row_weights(rows, "sft")) == {1.0}


def test_learning_rate_warms_up_then_decays():
    assert train.lr_at(1, 100, 1e-3) < train.lr_at(5, 100, 1e-3)
    assert train.lr_at(100, 100, 1e-3) < train.lr_at(20, 100, 1e-3)


class FakeTok:
    def apply_chat_template(self, msgs, add_generation_prompt=True, tokenize=True, enable_thinking=False):
        return [1, 2, 3]

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [10 + i for i in range(len(text) // 20 + 1)]}


def test_only_the_answer_is_learned():
    row = ev.read_rows(DEV)[0]
    ex = train.build_example(FakeTok(), row["intake"], row["answer"], 4096, 99)
    assert ex["labels"][:3] == [-100, -100, -100] and ex["labels"][-1] == 99
    assert len(ex["ids"]) == len(ex["labels"])


def test_queue_skips_runs_that_already_have_results(tmp_path):
    import queue as _q  # noqa: F401  (stdlib name; load ours by path)
    import importlib.util
    spec = importlib.util.spec_from_file_location("tunza_queue", Path(__file__).parent / "queue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "sft-0.8b-s1").mkdir()
    (tmp_path / "sft-0.8b-s1" / "results.json").write_text("{}")
    jobs = mod.plan(["sft", "sft_cost"], [1, 2], "0.8b", 80, tmp_path)
    assert [(j["tag"], j["done"]) for j in jobs] == [("sft-0.8b-s1", True), ("sft_cost-0.8b-s1", False), ("sft-0.8b-s2", False), ("sft_cost-0.8b-s2", False)]
