import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import evaluate as ev  # noqa: E402
import methods as mt  # noqa: E402

TRAIN = Path(__file__).parent / "data" / "triage-train.jsonl"


def test_rejected_answer_for_a_danger_case_is_a_missed_danger():
    rng = random.Random(0)
    for row in ev.read_rows(TRAIN):
        if ev.reward.RANK[row["answer"]["disposition"]] == 40:
            res = ev.reward.score(mt.rejected_text(row, rng), expected="go_now", case_input=row["intake"])
            assert res.stopped == "danger_under_triage" and res.reward == -1.0


def test_rejected_answer_is_never_the_correct_one_and_always_valid_json():
    rng = random.Random(1)
    for row in ev.read_rows(TRAIN):
        obj = json.loads(mt.rejected_text(row, rng))
        assert obj["disposition"] != row["answer"]["disposition"]


def _results(tmp, tag, mean, go_now):
    d = tmp / tag
    d.mkdir()
    (d / "results.json").write_text(json.dumps({"mean_reward": mean, "constant_baselines": {"go_now": go_now}}))


def test_rl_from_base_is_blocked_while_always_go_now_beats_the_base(tmp_path):
    _results(tmp_path, "base-0.8b", -0.399, -0.0125)
    ok, why = mt.rl_gate(tmp_path, "grpo", 0)
    assert not ok and "T7" in why


def test_sft_grpo_needs_an_sft_run_that_beats_go_now(tmp_path):
    assert not mt.rl_gate(tmp_path, "sft_grpo", 0)[0]
    _results(tmp_path, "sft-0.8b-s0", 0.861, -0.0125)
    assert mt.rl_gate(tmp_path, "sft_grpo", 0)[0]


torch = pytest.importorskip("torch")


def test_orpo_prefers_a_better_chosen_answer():
    good = mt.orpo_loss(torch.tensor([-1.0]), torch.tensor([10.0]), torch.tensor([-30.0]), torch.tensor([10.0]), torch)
    bad = mt.orpo_loss(torch.tensor([-30.0]), torch.tensor([10.0]), torch.tensor([-1.0]), torch.tensor([10.0]), torch)
    assert good < bad


def test_dpo_loss_falls_when_the_policy_moves_toward_the_chosen_answer():
    n = torch.tensor([10.0])
    ref = (torch.tensor([-10.0]), torch.tensor([-10.0]))
    still = mt.dpo_loss(torch.tensor([-10.0]), torch.tensor([-10.0]), *ref, n, torch, nll_weight=0.0)
    moved = mt.dpo_loss(torch.tensor([-5.0]), torch.tensor([-15.0]), *ref, n, torch, nll_weight=0.0)
    assert moved < still
