"""Tests for the v2 triage generator and its data. No network, no GPU. Needs node and a local esbuild."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "reward"))
import gen_cases as g  # noqa: E402
import tunza_reward as reward  # noqa: E402

V2 = HERE / "data" / "v2"
TRAIN = V2 / "triage-train.jsonl"
SEALED = V2 / "triage-sealed.jsonl"
KINDS = g.KINDS
LANG_NAME = {"en": "en", "sw": "sw", "cs": "code-switch"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def shingle_set(text: str, n: int = 5) -> frozenset:
    toks = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip().split()
    if not toks:
        return frozenset()
    if len(toks) < n:
        return frozenset({" ".join(toks)})
    return frozenset(" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1))


@pytest.fixture(scope="module")
def decider():
    d = g.Decider()
    yield d
    d.close()


@pytest.fixture(scope="module")
def manifest():
    return json.loads((V2 / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fams():
    return json.loads((V2 / "families.json").read_text(encoding="utf-8"))


# ---- determinism ----------------------------------------------------------

def test_same_seed_same_hash_and_matches_committed_files(tmp_path, manifest):
    a, b = tmp_path / "a", tmp_path / "b"
    g.generate(manifest["seed"], a)
    g.generate(manifest["seed"], b)
    for name in ("triage-train.jsonl", "triage-sealed.jsonl", "families.json"):
        assert sha(a / name) == sha(b / name)
    assert sha(a / "triage-train.jsonl") == manifest["files"]["triage-train.jsonl"]["sha256"] == sha(TRAIN)
    assert sha(a / "triage-sealed.jsonl") == manifest["files"]["triage-sealed.jsonl"]["sha256"] == sha(SEALED)


def test_different_seed_changes_the_data(tmp_path, manifest):
    g.generate(manifest["seed"] + 1, tmp_path)
    assert sha(tmp_path / "triage-train.jsonl") != sha(TRAIN)


def test_manifest_flags_and_hashes(manifest):
    assert manifest["jev_derived"] is False and manifest["clinical_data"] is False
    assert manifest["model_written_text"] is False
    assert manifest["label_source"] == "decide() in lib/assessment.ts"
    assert manifest["dev_file_checked_against"]["sha256"] == sha(g.V1_DEV)
    assert manifest["assessment_ts_sha256"] == sha(g.ASSESSMENT_TS)
    for name, info in manifest["files"].items():
        assert info["sha256"] == sha(V2 / name)
        assert info["rows"] == len(rows(V2 / name))


# ---- size and balance -----------------------------------------------------

def test_train_size_distinct_stories_and_balance(fams):
    tr = rows(TRAIN)
    assert 2800 <= len(tr) <= 3200
    texts = [norm(r["intake"]["presentation"]) for r in tr]
    assert len({t for t in texts if t}) >= 2500
    by_lang = Counter(f["lang"] for f in fams["train"])
    assert set(by_lang) == {"en", "sw", "cs"}
    assert max(by_lang.values()) <= 1.10 * min(by_lang.values())
    by_kind = Counter(r["answer"]["disposition"] for r in tr)
    assert set(by_kind) <= set(KINDS) and set(by_kind) == set(KINDS)
    assert by_kind["go_now"] >= 0.25 * len(tr)
    assert by_kind["need_one_more_answer"] >= 0.10 * len(tr)
    assert "escalate" not in by_kind and "abstain" not in by_kind


def test_sealed_size_and_balance(fams):
    se = rows(SEALED)
    assert 400 <= len(se) <= 500
    go_by_lang = Counter(f["lang"] for r, f in zip(se, fams["sealed"]) if r["answer"]["disposition"] == "go_now")
    assert all(go_by_lang[lang] >= 40 for lang in ("en", "sw", "cs"))
    by_kind = Counter(r["answer"]["disposition"] for r in se)
    for k in ("get_care_today", "monitor_at_home", "need_one_more_answer"):
        assert by_kind[k] >= 30
    assert "escalate" not in by_kind and "abstain" not in by_kind


def test_intake_shape_matches_v1():
    keys = {"who", "presentation", "awake", "breathing", "drinking", "duration", "mainProblem"}
    allowed = {
        "who": {"self", "household_adult", "child", "unknown", None},
        "awake": {"alert", "sleepy", "not_waking", "unknown", None},
        "breathing": {"fine", "difficult", "severe", "unknown", None},
        "drinking": {"yes", "little", "no", "unknown", None},
        "duration": {"today", "two_days", "longer", "unknown", None},
        "mainProblem": {"breathing", "fever", "injury", "stomach", "other", "unknown", None},
    }
    for r in rows(TRAIN) + rows(SEALED):
        assert set(r["intake"]) == keys and set(r["answer"]) == {"disposition", "danger_facts", "follow_up_question"}
        for f, ok in allowed.items():
            assert r["intake"][f] in ok
        assert isinstance(r["intake"]["presentation"], str)


# ---- leakage --------------------------------------------------------------

def test_no_exact_duplicate_rows_or_stories():
    for path in (TRAIN, SEALED):
        rs = rows(path)
        keys = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rs]
        assert len(set(keys)) == len(keys)
        stories = [norm(r["intake"]["presentation"]) for r in rs if norm(r["intake"]["presentation"])]
        assert len(set(stories)) == len(stories)


def test_no_shared_story_with_v1_or_between_v2_files():
    v1 = rows(g.V1_TRAIN) + rows(g.V1_DEV)
    v1s = {norm(r["intake"]["presentation"]) for r in v1} - {""}
    tr = {norm(r["intake"]["presentation"]) for r in rows(TRAIN)} - {""}
    se = {norm(r["intake"]["presentation"]) for r in rows(SEALED)} - {""}
    assert not (tr & v1s) and not (se & v1s) and not (tr & se)


def test_no_near_duplicate_sealed_story_against_train_or_dev():
    refs = [r["intake"]["presentation"] for r in rows(TRAIN) + rows(g.V1_TRAIN) + rows(g.V1_DEV)]
    ref_sets = [s for s in (shingle_set(t) for t in refs) if s]
    index: dict[str, list[int]] = {}
    for i, s in enumerate(ref_sets):
        for sh in s:
            index.setdefault(sh, []).append(i)
    worst = 0.0
    for r in rows(SEALED):
        a = shingle_set(r["intake"]["presentation"])
        if not a:
            continue
        cands = {i for sh in a for i in index.get(sh, ())}
        for i in cands:
            b = ref_sets[i]
            worst = max(worst, len(a & b) / len(a | b))
    assert worst < 0.8


def test_train_has_no_near_duplicate_of_v1_stories():
    v1 = [shingle_set(r["intake"]["presentation"]) for r in rows(g.V1_TRAIN) + rows(g.V1_DEV)]
    v1 = [s for s in v1 if s]
    for r in rows(TRAIN):
        a = shingle_set(r["intake"]["presentation"])
        if not a:
            continue
        for b in v1:
            if a & b:
                assert len(a & b) / len(a | b) < 0.8


def test_sealed_families_never_appear_in_train(fams):
    def sets(entries):
        out = {"shape": set(), "subj": set(), "sym": set(), "frames": set()}
        for e in entries:
            if e["shape"] == "blank":
                continue
            out["shape"].add(e["shape"])
            out["subj"].add(e["subj"])
            out["sym"].update(e["sym"])
            out["frames"].update(e["frames"])
        out["subj"].discard("-")
        return out

    tr, se = sets(fams["train"]), sets(fams["sealed"])
    for key in tr:
        assert tr[key] and se[key] or key == "frames"
        assert not (tr[key] & se[key]), key
    assert len(fams["train"]) == len(rows(TRAIN)) and len(fams["sealed"]) == len(rows(SEALED))
    for e in fams["train"] + fams["sealed"]:
        assert "family" in e and e["lang"] in ("en", "sw", "cs")
    for r in rows(TRAIN) + rows(SEALED):
        assert "family" not in r and "family" not in r["intake"]


def test_pool_definitions_keep_splits_apart():
    train_sym = {gid for lang in g.SYM.values() for groups in lang.values() for gid, sp, _ in groups if sp == "train"}
    sealed_sym = {gid for lang in g.SYM.values() for groups in lang.values() for gid, sp, _ in groups if sp == "sealed"}
    assert train_sym and sealed_sym and not (train_sym & sealed_sym)
    train_subj = {gid for groups in g.SUBJ.values() for gid, sp, _ in groups if sp == "train"}
    sealed_subj = {gid for groups in g.SUBJ.values() for gid, sp, _ in groups if sp == "sealed"}
    assert train_subj and sealed_subj and not (train_subj & sealed_subj)
    assert not (set(g.SHAPE_IDS["train"]) & set(g.SHAPE_IDS["sealed"]))
    for lang in g.BARE:
        assert not (set(g.BARE[lang]["train"]) & set(g.BARE[lang]["sealed"]))


# ---- labels ---------------------------------------------------------------

def test_label_equals_decide_on_every_row(decider):
    for path in (TRAIN, SEALED):
        rs = rows(path)
        labels = decider.decide([r["intake"] for r in rs])
        assert [lab["kind"] for lab in labels] == [r["answer"]["disposition"] for r in rs]


def test_bundle_agrees_with_v1_labels(decider):
    v1 = rows(g.V1_TRAIN) + rows(g.V1_DEV)
    assert len(v1) == 396
    labels = decider.decide([r["intake"] for r in v1])
    assert [lab["kind"] for lab in labels] == [r["answer"]["disposition"] for r in v1]


def test_answer_logic_reproduces_every_v1_answer():
    for r in rows(g.V1_TRAIN) + rows(g.V1_DEV):
        a = r["answer"]
        assert g.danger_facts(r["intake"], a["disposition"]) == a["danger_facts"]
        if a["disposition"] == "need_one_more_answer":
            assert a["follow_up_question"] in [g.follow_up_question(lang, r["intake"]) for lang in g.LANGS]
        else:
            assert a["follow_up_question"] is None


def test_every_pool_clause_matches_what_decide_expects(decider):
    base = {"who": "self", "awake": "alert", "breathing": "fine", "drinking": "yes", "duration": "today",
            "mainProblem": "other"}
    items = []
    for lang, topics in g.SYM.items():
        for topic, groups in topics.items():
            for gid, split, variants in groups:
                for text in variants:
                    prof = dict(base, mainProblem="injury") if topic == "inj" else dict(base)
                    items.append((topic, gid, text, dict(prof, presentation=text)))
    labels = decider.decide([i[3] for i in items])
    for (topic, gid, text, _), lab in zip(items, labels):
        if topic in g.DANGER_TOPICS:
            assert lab["kind"] == "go_now", (gid, text)
        else:
            assert lab["kind"] != "go_now", (gid, text)


# ---- reward ---------------------------------------------------------------

def test_reward_scores_every_reference_answer_one(fams):
    for path, key in ((TRAIN, "train"), (SEALED, "sealed")):
        for r, f in zip(rows(path), fams[key]):
            a = r["answer"]
            raw = reward.render_output(a["disposition"], a["danger_facts"], a["follow_up_question"])
            res = reward.score(raw, expected=a["disposition"], case_input=r["intake"], language=LANG_NAME[f["lang"]])
            assert res.reward == 1.0, (r, res)


def test_go_now_rows_carry_facts_and_other_rows_do_not():
    for r in rows(TRAIN) + rows(SEALED):
        a = r["answer"]
        if a["disposition"] == "go_now":
            assert a["danger_facts"] and a["follow_up_question"] is None
        elif a["disposition"] == "need_one_more_answer":
            assert a["danger_facts"] == [] and a["follow_up_question"].count("?") == 1
        else:
            assert a["danger_facts"] == [] and a["follow_up_question"] is None
