"""tunza-adw tests. Each test copies the tool and the real plan into a throwaway
git repo, so the pipeline runs end to end without touching this checkout or
calling a model."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
PLAN_REL = "specs/tunza-model-build-and-gpu-utilization.html"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def repo(tmp_path: Path):
    root = tmp_path / "Tunza"
    tool = root / "tools" / "tunza-adw"
    shutil.copytree(HERE, tool, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (root / "specs").mkdir()
    shutil.copy(REPO / PLAN_REL, root / PLAN_REL)
    shutil.copy(REPO / ".gitignore", root / ".gitignore")
    (root / "vault" / "sessions").mkdir(parents=True)
    (root / "vault" / "training.md").write_text("# Training\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    spec = importlib.util.spec_from_file_location(f"adw_{tmp_path.name}", tool / "adw.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    yield root, mod
    sys.modules.pop(spec.name, None)


class FakeSeats:
    """Stands in for Claude/Codex. behaviours[seat](prompt, root) -> envelope."""

    def __init__(self, mod, root: Path, behaviours: dict, cost: float = 0.5):
        self.config = mod.load_config()
        self.root, self.behaviours, self.cost, self.mod = root, behaviours, cost, mod
        self.calls: list[str] = []

    def call(self, seat, prompt, budget):
        self.calls.append(seat)
        return self.mod.SeatResult(self.behaviours[seat](prompt, self.root), self.cost, "fake")


def happy(mod, phase):
    """Envelopes for a clean run of `phase`."""
    def builder(_p, root):
        (root / "training").mkdir(exist_ok=True)
        (root / "training" / "schema.py").write_text("ROW = {}\n")
        return {"status": "done", "summary": "wrote schema", "files_changed": ["training/schema.py"],
                "commands_run": [], "blocked_reason": ""}

    def documenter(_p, root):
        (root / "vault" / "training.md").write_text("# Training\n\nphase done\n")
        return {"summary": "noted", "files_changed": ["vault/training.md"]}

    return {
        "scout": lambda p, r: {"summary": "recon", "hardware": {"gpu_name": "", "vram_mib": None, "driver": "",
                               "cuda": "", "system_ram_gb": None}, "current_state": [], "live_run": "not found",
                               "blockers": [], "evidence": []},
        "planner": lambda p, r: {"summary": "plan", "steps": [{"n": 1, "action": "x", "files": []}],
                                 "validations": [{"cmd": f'"{sys.executable}" -c "pass"', "shell": "bash",
                                                  "proves": "ok", "covers": phase.validation_items,
                                                  "needs_gpu": False, "timeout_s": 60, "manual": False}],
                                 "out_of_scope": [], "risks": []},
        "builder": builder,
        "tuner": lambda p, r: {"verdict": "not_applicable", "metrics": {"tok_per_s": None, "mfu": None,
                               "gpu_util_pct": None, "peak_mem_gb": None, "data_wait_pct": None},
                               "evidence": [], "files_changed": [], "recommendation": ""},
        "gatekeeper": lambda p, r: {"verdict": "pass", "blocking": [], "notes": []},
        "reviewer": lambda p, r: {"approved": True, "blocking": [], "summary": "ok",
                                  "items": [{"index": i, "status": "x", "evidence": "seen"}
                                            for i in range(len(phase.items))]},
        "documenter": documenter,
    }


def make_run(mod, root, phase, behaviours, budget=40.0, cost=0.5):
    run_dir = root / ".tunza-adw" / "runs" / f"t-p{phase.number}"
    run_dir.mkdir(parents=True, exist_ok=True)
    seats = FakeSeats(mod, root, behaviours, cost)
    run = mod.Run(phase=phase, run_id="t", run_dir=run_dir, seats=seats, budget=budget)
    return run, seats


def phase_n(mod, n):
    return next(p for p in mod.load_phases() if p.number == n)


# ----------------------------------------------------------------------------- plan

def test_real_plan_parses_into_eight_phases(repo):
    _, mod = repo
    phases = mod.load_phases()
    assert [p.number for p in phases] == list(range(8))
    for p in phases:
        assert p.validations, f"phase {p.number} has no validation commands"
        assert len(p.validations) == len(p.validation_items)
        assert all(0 <= i < len(p.items) for i in p.validation_items)
    assert phases[7].gated and not any(p.gated for p in phases[:7])
    assert not phases[6].needs_gpu and phases[3].needs_gpu and phases[7].needs_gpu


def test_set_markers_changes_only_the_named_phase(repo):
    root, mod = repo
    doc = (root / PLAN_REL).read_text()
    p2 = phase_n(mod, 2)
    new = mod.set_markers(doc, 2, "x", ["x"] * len(p2.items))
    phases = mod.parse_plan(new)
    assert phases[2].status == "x"
    assert all(p.status == "" for p in phases if p.number != 2)
    assert new.count('<code class="status">[x]</code>') == 1 + len(p2.items)


# ----------------------------------------------------------------------------- code checks

def test_hygiene_blocks_data_weights_secrets_and_gate_file(repo):
    root, mod = repo
    (root / "training").mkdir()
    (root / "training" / "leak.py").write_text('KEY = "sk-ant-' + "a" * 30 + '"\n')
    (root / "training" / "OPENING-CRITERIA.json").write_text("{}")
    problems = mod.hygiene(["training/data/rows.jsonl", "model.safetensors", "training/leak.py",
                            "training/OPENING-CRITERIA.json", "training/ok.py"])
    assert len(problems) == 4


@pytest.mark.parametrize("cmd", ["git push origin main", "git reset --hard HEAD", "Restart-Computer",
                                 "Remove-Item -Recurse -Force $HOME\\x", "echo x > training/OPENING-CRITERIA.json"])
def test_forbidden_commands(repo, cmd):
    _, mod = repo
    assert mod.forbidden(cmd)


def test_gate_needs_all_five_signed_fields(repo):
    root, mod = repo
    assert mod.gate_state()[0] == "blocked"
    gate = root / "training" / "OPENING-CRITERIA.json"
    gate.parent.mkdir(exist_ok=True)
    gate.write_text(json.dumps({f: "unset" for f in mod.GATE_FIELDS}))
    state, why = mod.gate_state()
    assert state == "blocked" and "Y" in why
    gate.write_text(json.dumps({"Y": "urgent_within_24h", "product": "chp_worklist",
                                "clinician_signoff": {"name": "Dr A", "ceiling": "unset"},
                                "data_rights_note": "note-1", "sealed_gold_sha256": "ab"}))
    assert mod.gate_state() == ("blocked", "unset: clinician_signoff")


def test_memory_advice_pushes_toward_full_use(repo):
    _, mod = repo
    g = {"available": True, "mem_total_mib": 32607, "util_pct": 99}
    proc = [{"pid": 1, "name": "python", "used_mib": 1}]
    assert mod.memory_advice({**g, "mem_used_mib": 1000, "util_pct": 0}, [])["level"] == "idle"
    # Windows (WDDM) often lists no per-process memory while a job runs: judge by the card itself.
    assert mod.memory_advice({**g, "mem_used_mib": 29000}, [])["level"] == "full"
    assert mod.memory_advice({**g, "mem_used_mib": 16000}, proc)["level"] == "headroom"
    assert mod.memory_advice({**g, "mem_used_mib": 29000}, proc)["level"] == "full"
    assert mod.memory_advice({**g, "mem_used_mib": 29000, "util_pct": 40}, proc)["level"] == "headroom"
    assert mod.memory_advice({**g, "mem_used_mib": 31900}, proc)["level"] == "danger"


# ----------------------------------------------------------------------------- pipeline

def test_happy_path_commits_and_marks_the_plan(repo):
    root, mod = repo
    _git(root, "switch", "-qc", "adw/t")
    p6 = phase_n(mod, 6)
    run, seats = make_run(mod, root, p6, happy(mod, p6))
    assert run.execute() == 0
    assert seats.calls == ["scout", "planner", "builder", "gatekeeper", "reviewer", "documenter"]
    assert "adw(phase 6)" in _git(root, "log", "-1", "--pretty=%s")
    committed = _git(root, "show", "--name-only", "--pretty=", "HEAD").split()
    assert set(committed) == {"training/schema.py", "vault/training.md", PLAN_REL}
    assert phase_n(mod, 6).status == "x"
    receipt = json.loads((run.run_dir / "receipt.json").read_text())
    assert receipt["steps"][-1]["ok"] and receipt["spent_usd"] == 3.0


def test_gpu_phase_runs_all_seven_seats(repo):
    root, mod = repo
    _git(root, "switch", "-qc", "adw/t")
    p3 = phase_n(mod, 3)
    run, seats = make_run(mod, root, p3, happy(mod, p3))
    assert run.execute() == 0
    assert seats.calls == mod.SEATS


def test_gated_phase_stops_before_any_agent(repo):
    root, mod = repo
    p7 = phase_n(mod, 7)
    run, seats = make_run(mod, root, p7, happy(mod, p7))
    assert run.execute() == 1
    assert seats.calls == []


def test_read_only_seat_that_edits_fails_the_run(repo):
    root, mod = repo
    p6 = phase_n(mod, 6)
    b = happy(mod, p6)
    honest = b["scout"]

    def sneaky(_p, r):
        (r / "vault" / "training.md").write_text("edited by scout\n")
        return honest(_p, r)

    b["scout"] = sneaky
    run, seats = make_run(mod, root, p6, b)
    assert run.execute() == 1
    assert seats.calls == ["scout"]


def test_false_file_claim_is_repaired_then_accepted(repo):
    root, mod = repo
    _git(root, "switch", "-qc", "adw/t")
    p6 = phase_n(mod, 6)
    b = happy(mod, p6)
    rounds = {"n": 0}
    honest = b["builder"]

    def builder(p, r):
        rounds["n"] += 1
        env = honest(p, r)
        if rounds["n"] == 1:
            env["files_changed"] = ["training/schema.py", "training/never_written.py"]
        return env

    b["builder"] = builder
    run, seats = make_run(mod, root, p6, b)
    assert run.execute() == 0
    assert seats.calls.count("builder") == 2


def test_failing_validation_loops_three_repairs_then_stops(repo):
    root, mod = repo
    p6 = phase_n(mod, 6)
    b = happy(mod, p6)
    plan = b["planner"]

    def red_plan(p, r):
        env = plan(p, r)
        env["validations"][0]["cmd"] = f'"{sys.executable}" -c "raise SystemExit(1)"'
        return env

    b["planner"] = red_plan
    run, seats = make_run(mod, root, p6, b)
    assert run.execute() == 1
    assert seats.calls.count("builder") == 1 + mod.MAX_FIX_LOOPS
    assert "reviewer" not in seats.calls


def test_uncovered_plan_check_is_rejected(repo):
    root, mod = repo
    p6 = phase_n(mod, 6)
    b = happy(mod, p6)
    plan = b["planner"]

    def partial(p, r):
        env = plan(p, r)
        env["validations"][0]["covers"] = p6.validation_items[:1]
        return env

    b["planner"] = partial
    run, seats = make_run(mod, root, p6, b)
    assert run.execute() == 1
    assert seats.calls == ["scout", "planner", "planner"]


def test_reviewer_block_means_no_commit(repo):
    root, mod = repo
    p6 = phase_n(mod, 6)
    b = happy(mod, p6)
    b["reviewer"] = lambda p, r: {"approved": False, "blocking": ["test asserts nothing"], "summary": "no",
                                  "items": []}
    head = _git(root, "rev-parse", "HEAD")
    run, _ = make_run(mod, root, p6, b)
    assert run.execute() == 1
    assert _git(root, "rev-parse", "HEAD") == head


def test_documenter_outside_vault_is_refused(repo):
    root, mod = repo
    p6 = phase_n(mod, 6)
    b = happy(mod, p6)

    def stray(_p, r):
        (r / "README.md").write_text("changed\n")
        return {"summary": "x", "files_changed": ["README.md"]}

    b["documenter"] = stray
    head = _git(root, "rev-parse", "HEAD")
    run, _ = make_run(mod, root, p6, b)
    assert run.execute() == 1
    assert _git(root, "rev-parse", "HEAD") == head


def test_budget_stops_the_run(repo):
    root, mod = repo
    p6 = phase_n(mod, 6)
    run, seats = make_run(mod, root, p6, happy(mod, p6), budget=1.0, cost=0.6)
    assert run.execute() == 1
    assert seats.calls == ["scout", "planner"]


def test_tuner_may_only_touch_configs(repo):
    root, mod = repo
    p3 = phase_n(mod, 3)
    b = happy(mod, p3)
    tuner = b["tuner"]

    def wild(p, r):
        (r / "training" / "sft.py").write_text("lr = 1\n")
        return tuner(p, r)

    b["tuner"] = wild
    run, seats = make_run(mod, root, p3, b)
    assert run.execute() == 1
    assert "gatekeeper" not in seats.calls


def test_gpu_reading_survives_windows_na_fields_and_renamed_throttle(repo, monkeypatch):
    _, mod = repo
    answers = {
        "name,memory.used,memory.total,utilization.gpu,power.draw,power.limit,clocks.sm,temperature.gpu":
            [["NVIDIA GeForce RTX 5090", "28123", "32607", "98", "[N/A]", "575.00", "2700", "71"]],
        "clocks_event_reasons.active": None,          # older driver: unknown field
        "clocks_throttle_reasons.active": [["0x0000000000000004"]],
        "pid,process_name,used_memory": [["4242", "C:\\Python\\python.exe", "[N/A]"]],
    }
    monkeypatch.setattr(mod, "_smi", lambda fields, kind="gpu": answers.get(fields))
    g = mod.gpu_metrics()
    assert g["available"] and g["mem_used_mib"] == 28123 and g["power_w"] is None and g["throttle"]
    procs = mod.gpu_procs()
    assert procs == [{"pid": 4242, "name": "python.exe", "used_mib": None}]
    assert mod.memory_advice(g, procs)["level"] == "full"
