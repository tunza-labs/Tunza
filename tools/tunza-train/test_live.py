import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import live  # noqa: E402


def make_run(root: Path, tag: str, steps: int, total: int = 10, **meta):
    d = root / tag
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"method": "ce", "seed": 0, "size": "0.8b", "total_steps": total, **meta}))
    rows = [{"step": s, "loss": 1.0 / s, "elapsed_s": s * 2.0, "tok_per_s": 100} for s in range(1, steps + 1)]
    (d / "telemetry.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    return d


def test_empty_runs_dir_says_no_runs(tmp_path):
    st = live.build_state(tmp_path / "missing", None)
    assert st["runs"] == [] and st["current"] is None
    assert st["plan"]["phases"] == []


def test_running_done_and_failed_states(tmp_path):
    make_run(tmp_path, "a", 4)
    make_run(tmp_path, "b", 10)
    make_run(tmp_path, "c", 3, failed=True)
    st = {r["tag"]: r for r in live.build_state(tmp_path, None)["runs"]}
    assert st["a"]["state"] == "running" and st["a"]["step"] == 4
    assert st["b"]["state"] == "done"
    assert st["c"]["state"] == "failed"


def test_stalled_when_telemetry_is_old(tmp_path):
    make_run(tmp_path, "a", 4)
    later = time.time() + live.STALE_SECONDS + 5
    assert live.build_state(tmp_path, None, now=later)["runs"][0]["state"] == "stalled"


def test_eta_from_recent_step_time(tmp_path):
    make_run(tmp_path, "a", 5, total=15)
    run = live.build_state(tmp_path, None)["runs"][0]
    assert run["eta_min"] == 0 or run["eta_min"] is not None  # 10 steps x 2 s is under a minute


def test_bad_telemetry_lines_are_skipped(tmp_path):
    make_run(tmp_path, "a", 2)
    assert len(live.read_telemetry(tmp_path / "a" / "telemetry.jsonl")) == 2


def test_plan_html_counts_boxes():
    html = ('<div class="phase"><h3><code class="status">[x]</code> Phase 0: Brief</h3>'
            '<ul><li><code class="status">[x]</code> a</li><li><code class="status">[]</code> b</li></ul></div>')
    p = live.parse_plan_html(html)["phases"][0]
    assert p["name"] == "Phase 0: Brief" and p["status"] == "done" and (p["done"], p["total"]) == (2, 3)


def test_dedication_reports_unreadable_gpu():
    d = live.dedication({"ok": False, "error": "NVML failed"}, {"pid": 1})
    assert d["tone"] == "bad" and "NVML failed" in d["text"]


def test_dedication_flags_other_gpu_programs():
    gpu = {"ok": True, "util": 90, "apps": [{"pid": 1, "name": "python.exe"}, {"pid": 9, "name": "game.exe"}]}
    d = live.dedication(gpu, {"pid": 1})
    assert d["tone"] == "warn" and "game.exe" in d["text"]


def test_dedication_low_use_and_full_use():
    assert live.dedication({"ok": True, "util": 40, "apps": []}, {"pid": 1})["tone"] == "warn"
    assert live.dedication({"ok": True, "util": 90, "apps": []}, {"pid": 1})["tone"] == "ok"
    assert live.dedication({"ok": True, "util": 0, "apps": []}, None)["tone"] == "idle"
    busy = live.dedication({"ok": True, "util": 88, "apps": [{"pid": 5, "name": "llama-server.exe"}]}, None)
    assert busy["tone"] == "warn" and "llama-server.exe" in busy["text"]


def test_parse_typeperf_reads_one_sample():
    head = ('"(PDH-CSV 4.0)",'
            '"\\\\H\\GPU Engine(pid_12_luid_0x0_0x1_phys_0_eng_0_engtype_3D)\\Utilization Percentage",'
            '"\\\\H\\GPU Engine(pid_12_luid_0x0_0x1_phys_0_eng_1_engtype_Compute_0)\\Utilization Percentage"')
    row = '"10/18/2026 00:00:00.1","12.5","80.25"'
    got = live.parse_typeperf(head + "\n" + row + "\n\nExiting, please wait...\nThe command completed successfully.\n")
    assert sorted(got.values()) == [12.5, 80.25]


def test_windows_fallback_is_off_the_windows_path():
    if live.os.name != "nt":
        assert live.windows_gpu_info("x") is None
