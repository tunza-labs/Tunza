import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import evaluate as ev  # noqa: E402

DATA = Path(__file__).parent / "data"
LANGS = ("en", "sw", "code-switch")


def _row(disposition: str, story: str, **extra) -> dict:
    row = {
        "intake": {"presentation": story, "who": "child", "awake": "alert", "breathing": "fine",
                   "drinking": "yes", "duration": "today", "mainProblem": "other"},
        "answer": {"disposition": disposition, "danger_facts": [], "follow_up_question": None},
    }
    row.update(extra)
    return row


def _go_now(story: str, **extra) -> dict:
    row = _row("go_now", story, **extra)
    row["answer"]["danger_facts"] = ["danger"]
    return row


def test_by_language_keeps_existing_keys_and_reports_each_language():
    rows = [_go_now("english danger", language="en"), _row("monitor_at_home", "swahili rest", language="sw")]
    res = ev.evaluate(rows, lambda p: "not json")
    assert set(res) >= {"n", "valid_json_rate", "mean_reward", "danger_cases", "danger_missed",
                        "danger_miss_rate", "confusion", "rows", "by_language"}
    assert set(res["by_language"]) == set(LANGS)
    assert res["by_language"]["en"]["n"] == 1
    assert res["by_language"]["en"]["danger_cases"] == 1
    assert res["by_language"]["en"]["danger_missed"] == 1
    assert res["by_language"]["en"]["mean_reward"] == -1.0
    assert res["by_language"]["sw"]["n"] == 1
    assert res["by_language"]["sw"]["danger_cases"] == 0
    assert res["by_language"]["code-switch"] == {"n": 0, "mean_reward": 0.0, "danger_cases": 0, "danger_missed": 0}


def test_language_field_wins_over_story_lookup():
    story = json.loads((DATA / "v2" / "triage-train.jsonl").read_text().splitlines()[0])["intake"]["presentation"]
    rows = [_row("monitor_at_home", story, language="sw")]
    assert ev.row_language(rows[0]) == "sw"
    res = ev.evaluate(rows, lambda p: ev.answer_text(rows[0]["answer"]))
    assert res["by_language"]["sw"]["n"] == 1 and res["by_language"]["sw"]["mean_reward"] == 1.0
    assert res["by_language"]["en"]["n"] == 0


def test_story_marker_in_data_files_sets_language_when_the_row_has_none():
    families = json.loads((DATA / "v2" / "families.json").read_text())
    rows = ev.read_rows(DATA / "v2" / "triage-sealed.jsonl")
    picked = {}
    for row, fam in zip(rows, families["sealed"]):
        lang = {"en": "en", "sw": "sw", "cs": "code-switch"}[fam["lang"]]
        if lang not in picked and row["intake"]["presentation"].strip():
            picked[lang] = row
        if len(picked) == 3:
            break
    assert set(picked) == set(LANGS)
    for lang, row in picked.items():
        assert "language" not in row and ev.row_language(row) == lang
    ordered = [picked[lang] for lang in LANGS]
    res = ev.evaluate(ordered, lambda p: "nope")
    for lang in LANGS:
        assert res["by_language"][lang]["n"] == 1
        assert res["by_language"][lang]["mean_reward"] == -1.0


def test_inline_story_marker_and_family_prefix():
    marked = _go_now("sw|mtoto hapumui")
    family = _row("get_care_today", "plain story", family="cs|shape=S1|subj=x")
    assert ev.row_language(marked) == "sw"
    assert ev.row_language(family) == "code-switch"
    res = ev.evaluate([marked, family], lambda p: ev.answer_text({"disposition": "monitor_at_home", "danger_facts": [], "follow_up_question": None}))
    assert res["by_language"]["sw"]["danger_cases"] == 1
    assert res["by_language"]["sw"]["danger_missed"] == 1
    assert res["by_language"]["code-switch"]["n"] == 1
    assert res["by_language"]["code-switch"]["danger_missed"] == 0
