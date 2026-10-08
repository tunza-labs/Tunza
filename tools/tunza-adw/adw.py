#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""tunza-adw: a 7-agent workflow that executes the Tunza model build plan.

    tunza-adw doctor                 check this machine (GPU, git, claude, plan)
    tunza-adw status                 show every plan phase and its marker
    tunza-adw run --next             run the first phase not marked [x]
    tunza-adw run --phase 3          run one phase
    tunza-adw run --all              run phases in order until one stops
    tunza-adw run --next --dry-run   print the steps, call no model
    tunza-adw ui                     red dashboard: run workflows, live GPU memory and RAM

Code owns the order, the gates and the verdict. Agents fill typed envelopes.
Seats: scout, planner, builder, tuner, gatekeeper, reviewer, documenter.
Nothing is pushed unless --push is given. Clinical training stays behind
training/gate.py, which agents never sign.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

TOOL = Path(__file__).resolve().parent
ROOT = TOOL.parents[1]
PLAN_REL = "specs/tunza-model-build-and-gpu-utilization.html"
RUNS_REL = ".tunza-adw/runs"
IS_WIN = os.name == "nt"

SEATS = ["scout", "planner", "builder", "tuner", "gatekeeper", "reviewer", "documenter"]
READ_ONLY = {"scout", "gatekeeper", "reviewer"}
MAX_FIX_LOOPS = 3
DOC_PATHS = re.compile(r"^vault/(training\.md|INDEX\.md|sessions/[^/]+\.md)$")
TUNER_PATHS = re.compile(r"^training/(configs|queue/jobs)/[^/]+\.(ya?ml|json)$")
GPU_WORDS = re.compile(r"nvidia-smi|\bGPU\b|\bMFU\b|tok/s|throughput|bench|bake-off|queue|\bSFT\b|\bLoRA\b", re.I)

FORBIDDEN_COMMANDS = [
    (re.compile(r"\bgit\s+push\b", re.I), "git push is reserved for --push"),
    (re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)", re.I), "destructive git"),
    (re.compile(r"\brm\s+-rf?\s+(/|~|\$HOME|C:)", re.I), "recursive delete outside the repo"),
    (re.compile(r"Remove-Item\b[^\n]*-Recurse[^\n]*(C:\\|\$HOME|\$env:USERPROFILE|~)", re.I),
     "recursive delete outside the repo"),
    (re.compile(r"\b(Restart-Computer|Stop-Computer|shutdown(\.exe)?\s)", re.I), "reboots the box"),
    (re.compile(r"\bformat\s+[a-z]:", re.I), "formats a drive"),
    (re.compile(r"OPENING-CRITERIA\.json", re.I), "only people edit the opening criteria"),
]
FORBIDDEN_PATHS = re.compile(
    r"^(training/(data|runs|adapters|\.venv)/|\.tunza-adw/)|\.(safetensors|gguf|pt|pth|ckpt|bin)$", re.I)
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{30,}|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
MAX_FILE_BYTES = 5 * 1024 * 1024
# Files that Claude Code hooks and harnesses write on their own (not an agent's edit).
HARNESS_NOISE = re.compile(r"^(\.claude/data/|(.+/)?logs/[^/]+\.(json|jsonl|log)$)")
GATE_FIELDS = ["Y", "product", "clinician_signoff", "data_rights_note", "sealed_gold_sha256"]


# ----------------------------------------------------------------------------- plan

@dataclass
class Phase:
    number: int
    name: str
    status: str
    text: str
    items: list[str]
    validations: list[str]
    validation_items: list[int]
    block: str

    @property
    def needs_gpu(self) -> bool:
        return bool(GPU_WORDS.search(self.text))

    @property
    def gated(self) -> bool:
        return "gated" in self.name.lower()


_H3 = re.compile(r'<h3><code class="status">\[(.*?)\]</code>\s*Phase (\d+):\s*(.*?)</h3>', re.S)
_LI = re.compile(r'<li><code class="status">\[(.*?)\]</code>(.*?)</li>', re.S)
_TAG = re.compile(r"<[^>]+>")


def strip_tags(fragment: str) -> str:
    text = _TAG.sub(" ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _phase_blocks(doc: str) -> list[tuple[int, int]]:
    starts = [m.start() for m in re.finditer(r'<div class="phase">', doc)]
    spans = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else doc.find("</section>", start)
        spans.append((start, end if end != -1 else len(doc)))
    return spans


def parse_plan(doc: str) -> list[Phase]:
    phases = []
    for start, end in _phase_blocks(doc):
        block = doc[start:end]
        head = _H3.search(block)
        if not head:
            continue
        items, validations, validation_items = [], [], []
        testing_at = block.find("Testing Strategy")
        for m in _LI.finditer(block):
            if testing_at != -1 and m.start() > testing_at:
                code = re.search(r"<code>(.*?)</code>", m.group(2), re.S)
                validations.append(html.unescape(_TAG.sub("", code.group(1))).strip() if code
                                   else strip_tags(m.group(2)))
                validation_items.append(len(items))
            items.append(strip_tags(m.group(2)))
        phases.append(Phase(number=int(head.group(2)), name=strip_tags(head.group(3)),
                            status=head.group(1), text=strip_tags(block), items=items,
                            validations=validations, validation_items=validation_items, block=block))
    return phases


def set_markers(doc: str, number: int, phase_status: str, item_statuses: list[str]) -> str:
    """Rewrite one phase's markers. item_statuses lines up with Phase.items."""
    for start, end in _phase_blocks(doc):
        block = doc[start:end]
        head = _H3.search(block)
        if not head or int(head.group(2)) != number:
            continue
        block = block[:head.start(1)] + phase_status + block[head.end(1):]
        statuses = iter(item_statuses)

        def swap(m: re.Match) -> str:
            new = next(statuses, None)
            return m.group(0) if new is None else m.group(0).replace(f"[{m.group(1)}]", f"[{new}]", 1)

        block = _LI.sub(swap, block)
        return doc[:start] + block + doc[end:]
    raise KeyError(f"phase {number} not in plan")


def append_amendment(doc: str, iso: str, summary: str, detail: str) -> str:
    entry = (f'    <details>\n      <summary>{html.escape(iso)} — {html.escape(summary)}</summary>\n'
             f'      <p>{html.escape(detail)}</p>\n    </details>\n')
    doc = doc.replace('    <p style="color:var(--muted)">None yet.</p>\n', "", 1)
    anchor = doc.find('<section id="amendments">')
    close = doc.find("</section>", anchor)
    return doc[:close] + entry + "  " + doc[close:] if anchor != -1 else doc


# ----------------------------------------------------------------------------- envelopes

def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False,
            "properties": props, "required": list(props)}


_S = {"type": "string"}
_SL = {"type": "array", "items": _S}
_NUM = {"type": ["number", "null"]}
_EVIDENCE = {"type": "array", "items": _obj({"claim": _S, "source": _S})}

SCHEMAS: dict[str, dict] = {
    "scout": _obj({
        "summary": _S,
        "hardware": _obj({"gpu_name": _S, "vram_mib": _NUM, "driver": _S, "cuda": _S,
                          "system_ram_gb": _NUM}),
        "current_state": _SL, "live_run": _S, "blockers": _SL, "evidence": _EVIDENCE}),
    "planner": _obj({
        "summary": _S,
        "steps": {"type": "array", "items": _obj({"n": {"type": "integer"}, "action": _S, "files": _SL})},
        "validations": {"type": "array", "items": _obj({
            "cmd": _S, "shell": {"type": "string", "enum": ["powershell", "bash"]}, "proves": _S,
            "covers": {"type": "array", "items": {"type": "integer"}}, "needs_gpu": {"type": "boolean"},
            "timeout_s": {"type": "integer"}, "manual": {"type": "boolean"}})},
        "out_of_scope": _SL, "risks": _SL}),
    "builder": _obj({
        "status": {"type": "string", "enum": ["done", "blocked"]}, "summary": _S, "files_changed": _SL,
        "commands_run": {"type": "array", "items": _obj({"cmd": _S, "exit_code": {"type": "integer"}})},
        "blocked_reason": _S}),
    "tuner": _obj({
        "verdict": {"type": "string", "enum": ["pass", "fail", "not_applicable"]},
        "metrics": _obj({"tok_per_s": _NUM, "mfu": _NUM, "gpu_util_pct": _NUM, "peak_mem_gb": _NUM,
                         "data_wait_pct": _NUM}),
        "evidence": _EVIDENCE, "files_changed": _SL, "recommendation": _S}),
    "gatekeeper": _obj({"verdict": {"type": "string", "enum": ["pass", "block"]}, "blocking": _SL,
                        "notes": _SL}),
    "reviewer": _obj({
        "approved": {"type": "boolean"}, "blocking": _SL, "summary": _S,
        "items": {"type": "array", "items": _obj({
            "index": {"type": "integer"}, "status": {"type": "string", "enum": ["x", "f", "open"]},
            "evidence": _S})}}),
    "documenter": _obj({"summary": _S, "files_changed": _SL}),
}


# ----------------------------------------------------------------------------- runtimes

class SeatError(RuntimeError):
    pass


@dataclass
class SeatResult:
    data: dict
    cost: float = 0.0
    engine: str = ""


def claude_exe() -> str | None:
    """Prefer the native claude.exe on Windows: an npm claude.cmd goes through cmd.exe,
    which mangles JSON and markdown arguments."""
    return (shutil.which("claude.exe") if IS_WIN else None) or shutil.which("claude")


class ClaudeRuntime:
    """Runs a seat as a fresh, headless Claude Code session."""

    def __init__(self, config: dict, run_dir: Path):
        self.config = config
        self.run_dir = run_dir
        self.exe = claude_exe()

    def call(self, seat: str, prompt: str, system: str, schema: dict, budget: float) -> SeatResult:
        if not self.exe:
            raise SeatError("claude CLI not found on PATH")
        conf = self.config["seats"][seat]
        system_file = self.run_dir / f"{seat}.system.md"
        system_file.write_text(system, encoding="utf-8")
        cmd = [self.exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema),
               "--model", conf["model"], "--append-system-prompt-file", str(system_file),
               "--dangerously-skip-permissions", "--no-session-persistence",
               "--max-budget-usd", f"{max(budget, 0.5):.2f}"]
        if seat in READ_ONLY:
            cmd += ["--disallowedTools", "Edit", "Write", "NotebookEdit"]
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=ROOT,
                                  encoding="utf-8", errors="replace", timeout=conf["timeout_s"])
        except subprocess.TimeoutExpired as exc:
            raise SeatError(f"{seat} timed out after {conf['timeout_s']} s") from exc
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SeatError(f"{seat} returned no JSON: {proc.stderr[-800:] or proc.stdout[-800:]}") from exc
        if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
            raise SeatError(f"{seat} failed: {out.get('subtype')} {str(out.get('result'))[:800]}")
        return SeatResult(out["structured_output"], float(out.get("total_cost_usd") or 0), "claude")


class CodexRuntime:
    """Runs a read-only seat on Codex so the review comes from a different model family."""

    def __init__(self, config: dict, run_dir: Path):
        self.config = config
        self.exe = shutil.which("codex")
        self.run_dir = run_dir

    def call(self, seat: str, prompt: str, system: str, schema: dict, budget: float) -> SeatResult:
        conf = self.config["seats"][seat]
        schema_file = self.run_dir / f"{seat}.schema.json"
        out_file = self.run_dir / f"{seat}.codex.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        cmd = [self.exe, "exec", "-s", "read-only", "-C", str(ROOT), "--skip-git-repo-check",
               "--output-schema", str(schema_file), "-o", str(out_file)]
        if conf.get("codex_model"):
            cmd += ["-m", conf["codex_model"]]
        cmd.append("-")
        try:
            proc = subprocess.run(cmd, input=system + "\n\n" + prompt, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=conf["timeout_s"])
        except subprocess.TimeoutExpired as exc:
            raise SeatError(f"{seat} (codex) timed out") from exc
        try:
            return SeatResult(json.loads(out_file.read_text(encoding="utf-8")), 0.0, "codex")
        except (OSError, json.JSONDecodeError) as exc:
            raise SeatError(f"{seat} (codex) gave no envelope: {proc.stderr[-800:]}") from exc


class Seats:
    """Picks the engine per seat. Reviewer prefers Codex, falls back to Claude."""

    def __init__(self, config: dict, run_dir: Path, claude=None, codex=None):
        self.config = config
        self.claude = claude or ClaudeRuntime(config, run_dir)
        self.codex = codex if codex is not None else CodexRuntime(config, run_dir)

    def engine_for(self, seat: str):
        want = self.config["seats"][seat].get("engine", "claude")
        if want == "codex" and getattr(self.codex, "exe", None):
            return self.codex
        return self.claude

    def call(self, seat: str, prompt: str, budget: float) -> SeatResult:
        system = (TOOL / "seats" / "_shared.md").read_text(encoding="utf-8") + "\n\n" + \
            (TOOL / "seats" / f"{seat}.md").read_text(encoding="utf-8")
        engine = self.engine_for(seat)
        try:
            return engine.call(seat, prompt, system, SCHEMAS[seat], budget)
        except SeatError:
            if engine is self.codex:
                return self.claude.call(seat, prompt, system, SCHEMAS[seat], budget)
            raise


# ----------------------------------------------------------------------------- repo checks

def git(*args: str, check: bool = False) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def fingerprint() -> dict[str, str]:
    """Content hash of every changed or untracked, non-ignored path."""
    prints = {}
    for line in git("status", "--porcelain", "--untracked-files=all", "-z").split("\0"):
        if len(line) < 4:
            continue
        path = line[3:]
        if HARNESS_NOISE.match(path):
            continue
        full = ROOT / path
        if full.is_file():
            prints[path] = hashlib.sha1(full.read_bytes()).hexdigest()
        elif not full.exists():
            prints[path] = "deleted"
    return prints


def changed_between(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def hygiene(paths: list[str]) -> list[str]:
    problems = []
    for path in paths:
        if FORBIDDEN_PATHS.search(path):
            problems.append(f"{path}: data, weights or run output must not enter this public repo")
            continue
        full = ROOT / path
        if not full.is_file():
            continue
        if full.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{path}: larger than 5 MB")
            continue
        text = full.read_text(encoding="utf-8", errors="ignore")
        if SECRET.search(text):
            problems.append(f"{path}: looks like it contains a secret")
        if path.endswith("OPENING-CRITERIA.json"):
            problems.append(f"{path}: only Evan and the named clinician edit the opening criteria")
    return problems


def forbidden(command: str) -> str | None:
    for pattern, why in FORBIDDEN_COMMANDS:
        if pattern.search(command):
            return why
    return None


def gate_state() -> tuple[str, str]:
    """('open'|'blocked', why). Reads the file directly; no agent involved."""
    path = ROOT / "training" / "OPENING-CRITERIA.json"
    if not path.is_file():
        return "blocked", "training/OPENING-CRITERIA.json does not exist"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "blocked", "OPENING-CRITERIA.json is not valid JSON"
    missing = [f for f in GATE_FIELDS if data.get(f) in (None, "", "unset") or
               (isinstance(data.get(f), dict) and "unset" in json.dumps(data[f]))]
    return ("blocked", "unset: " + ", ".join(missing)) if missing else ("open", "all five fields signed")


def gpu_receipt() -> dict:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"available": False}
    proc = subprocess.run([smi, "--query-gpu=name,memory.total,driver_version,power.limit",
                           "--format=csv,noheader,nounits"], capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"available": False, "error": proc.stderr.strip()}
    name, mem, driver, power = [p.strip() for p in proc.stdout.splitlines()[0].split(",")[:4]]
    return {"available": True, "name": name, "memory_mib": float(mem), "driver": driver,
            "power_limit_w": power, "raw": proc.stdout.strip()}


def run_command(cmd: str, shell: str, timeout_s: int) -> tuple[int, str]:
    if shell == "powershell" or (IS_WIN and shell != "bash"):
        argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
    else:
        argv = ["bash", "-lc", cmd]
    try:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout_s} s"
    except FileNotFoundError as exc:
        return 127, str(exc)
    out = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, out[-4000:]


# ----------------------------------------------------------------------------- the run

@dataclass
class Run:
    phase: Phase
    run_id: str
    run_dir: Path
    seats: Seats
    budget: float
    dry_run: bool = False
    push: bool = False
    spent: float = 0.0
    steps: list[dict] = field(default_factory=list)
    envelopes: dict[str, Any] = field(default_factory=dict)
    exec_cmd: Callable[[str, str, int], tuple[int, str]] = run_command

    # --- bookkeeping
    def log(self, name: str, owner: str, ok: bool, **detail) -> None:
        step = {"step": name, "owner": owner, "ok": ok, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **detail}
        self.steps.append(step)
        mark = "ok " if ok else "FAIL"
        extra = detail.get("why") or detail.get("summary") or ""
        print(f"  [{mark}] {name:<14} {owner:<11} {str(extra)[:110]}")
        self.save()

    def save(self) -> None:
        (self.run_dir / "receipt.json").write_text(json.dumps({
            "run_id": self.run_id, "phase": self.phase.number, "phase_name": self.phase.name,
            "spent_usd": round(self.spent, 4), "budget_usd": self.budget, "steps": self.steps,
            "envelopes": self.envelopes}, indent=2), encoding="utf-8")

    def finish(self, accepted: bool, why: str = "") -> int:
        self.log("finish", "code", accepted, why=why or ("accepted" if accepted else "not accepted"),
                 spent_usd=round(self.spent, 4))
        print(f"\nphase {self.phase.number} {'ACCEPTED' if accepted else 'NOT ACCEPTED'}"
              f"{': ' + why if why else ''} · ${self.spent:.2f} · receipt {self.run_dir / 'receipt.json'}")
        return 0 if accepted else 1

    def seat(self, name: str, prompt: str) -> dict:
        left = self.budget - self.spent
        if left <= 0:
            raise SeatError(f"budget ${self.budget:.2f} spent before {name}")
        before = fingerprint()
        result = self.seats.call(name, prompt, min(left, self.seats.config["seats"][name]["budget_usd"]))
        self.spent += result.cost
        touched = [p for p in changed_between(before, fingerprint())]
        if name in READ_ONLY and touched:
            raise SeatError(f"read-only seat {name} changed files: {', '.join(touched[:8])}")
        self.envelopes[name] = result.data
        (self.run_dir / f"{name}.json").write_text(json.dumps(result.data, indent=2), encoding="utf-8")
        self.log(name, result.engine or "agent", True, summary=result.data.get("summary", ""),
                 cost_usd=round(result.cost, 4), touched=touched)
        result.data["_touched"] = touched
        return result.data

    def context(self) -> str:
        p = self.phase
        items = "\n".join(f"  [{i}] {t}" for i, t in enumerate(p.items))
        vals = "\n".join(f"  [{i}] {v}" for i, v in zip(p.validation_items, p.validations))
        return (f"REPO: {ROOT}\nPLAN: {ROOT / PLAN_REL}\nRUN DIR (write scratch files here): {self.run_dir}\n"
                f"OS: {'Windows (PowerShell)' if IS_WIN else sys.platform}\n"
                f"GPU RECEIPT (from code): {json.dumps(self.envelopes.get('gpu', {}))}\n"
                f"GATE (from code): {json.dumps(self.envelopes.get('gate', {}))}\n\n"
                f"PHASE {p.number}: {p.name}\n{p.text}\n\nPLAN CHECKLIST ITEMS (index: text):\n{items}\n\n"
                f"PLAN VALIDATIONS (item index: command; every index must be covered):\n{vals}\n")

    # --- code checks
    def check_plan(self, plan: dict) -> list[str]:
        problems = []
        if not plan["validations"]:
            problems.append("planner returned no validation commands")
        covered = {i for v in plan["validations"] for i in v["covers"]}
        missing = [i for i in self.phase.validation_items if i not in covered]
        if missing:
            problems.append(f"plan validations for items {missing} are not covered")
        for v in plan["validations"]:
            why = forbidden(v["cmd"])
            if why:
                problems.append(f"forbidden command ({why}): {v['cmd']}")
        return problems

    def quality(self, plan: dict) -> dict:
        results = []
        for v in plan["validations"]:
            if v["manual"]:
                results.append({"cmd": v["cmd"], "covers": v["covers"], "status": "manual", "output": ""})
                continue
            code, out = self.exec_cmd(v["cmd"], v["shell"], max(60, v["timeout_s"]))
            results.append({"cmd": v["cmd"], "covers": v["covers"], "exit_code": code,
                            "status": "pass" if code == 0 else "fail", "output": out})
        passed = all(r["status"] != "fail" for r in results)
        (self.run_dir / f"quality_{len([s for s in self.steps if s['step'].startswith('test')]) + 1}.json") \
            .write_text(json.dumps(results, indent=2), encoding="utf-8")
        return {"passed": passed, "results": results}

    def claims_vs_diff(self, this_round: list[str], all_claims: set[str], changed: list[str]) -> list[str]:
        """Every file that differs from the pre-build tree must have been claimed in some round,
        and every file claimed this round must actually differ from the pre-build tree."""
        norm = lambda p: p.replace("\\", "/").removeprefix("./")  # noqa: E731
        now, every, actual = {norm(p) for p in this_round}, {norm(p) for p in all_claims}, {norm(p) for p in changed}
        problems = []
        if now - actual:
            problems.append(f"claimed but not changed: {sorted(now - actual)}")
        if actual - every:
            problems.append(f"changed but not claimed: {sorted(actual - every)}")
        return problems

    # --- the pipeline
    def execute(self) -> int:
        p = self.phase
        print(f"\ntunza-adw {self.run_id} · phase {p.number}: {p.name} · budget ${self.budget:.2f}")
        if self.dry_run:
            for name, owner, what in DRY_STEPS:
                print(f"  {name:<14} {owner:<11} {what}")
            return 0

        gpu = gpu_receipt()
        self.envelopes["gpu"] = gpu
        state, why = gate_state()
        self.envelopes["gate"] = {"state": state, "why": why}
        self.log("preflight", "code", True, gpu=gpu.get("name", "none"),
                 vram_mib=gpu.get("memory_mib"), gate=state, branch=git("branch", "--show-current").strip())
        if p.gated and state != "open":
            return self.finish(False, f"gate blocked ({why}); clinical training needs people, not agents")
        if p.needs_gpu and IS_WIN and not gpu.get("available"):
            return self.finish(False, "this phase needs the GPU and nvidia-smi is not available")

        try:
            ctx = self.context()
            scout = self.seat("scout", ctx + "\nDo the recon described in your seat instructions.")
            plan = self.seat("planner", ctx + "\nSCOUT ENVELOPE:\n" + json.dumps(scout, indent=2))
            problems = self.check_plan(plan)
            if problems:
                plan = self.seat("planner", ctx + "\nSCOUT ENVELOPE:\n" + json.dumps(scout, indent=2) +
                                 "\n\nYOUR LAST PLAN WAS REJECTED BY CODE:\n- " + "\n- ".join(problems) +
                                 "\nReturn a corrected plan.")
                problems = self.check_plan(plan)
            self.log("plan_check", "code", not problems, why="; ".join(problems))
            if problems:
                return self.finish(False, "plan rejected: " + "; ".join(problems))

            build_prompt = ctx + "\nPLAN ENVELOPE:\n" + json.dumps(plan, indent=2)
            baseline = fingerprint()
            build = self.seat("builder", build_prompt)
            if build["status"] == "blocked":
                return self.finish(False, "builder blocked: " + build["blocked_reason"])
            claimed: set[str] = set()

            fixes = 0
            while True:
                changed = changed_between(baseline, fingerprint())
                claimed |= set(build["files_changed"])
                problems = self.claims_vs_diff(build["files_changed"], claimed, changed) + hygiene(changed)
                self.log("diff_check", "code", not problems, why="; ".join(problems), files=changed)
                test = self.quality(plan) if not problems else {"passed": False, "results": []}
                if not problems:
                    self.log(f"test_{fixes + 1}", "code", test["passed"],
                             why=", ".join(f"{r['status']}:{r['cmd'][:40]}" for r in test["results"]))
                if not problems and test["passed"]:
                    break
                if fixes >= MAX_FIX_LOOPS:
                    return self.finish(False, "still red after 3 repairs")
                fixes += 1
                failing = [r for r in test["results"] if r["status"] == "fail"]
                build = self.seat("builder", build_prompt + "\n\nREPAIR ROUND " + str(fixes) +
                                  ". Code found these problems. Fix the cause, not the check:\n" +
                                  json.dumps({"diff_problems": problems, "failing_commands": failing}, indent=2) +
                                  "\nfiles_changed must list every file you changed in THIS round.")
                if build["status"] == "blocked":
                    return self.finish(False, "builder blocked: " + build["blocked_reason"])

            tuner = None
            if p.needs_gpu or any(v["needs_gpu"] for v in plan["validations"]):
                tuner = self.seat("tuner", ctx + "\nPLAN ENVELOPE:\n" + json.dumps(plan, indent=2) +
                                  "\nQUALITY RESULTS:\n" + json.dumps(test, indent=2)[:12000])
                bad = [f for f in tuner["_touched"] if not TUNER_PATHS.match(f.replace("\\", "/"))]
                bad += hygiene(tuner["_touched"])
                if bad:
                    return self.finish(False, f"tuner changed files outside configs: {bad}")
                if tuner["_touched"]:
                    changed = sorted(set(changed) | set(tuner["_touched"]))
                    test = self.quality(plan)
                    self.log("test_tuned", "code", test["passed"])
                    if not test["passed"]:
                        return self.finish(False, "tuner config change broke validation")
                if tuner["verdict"] == "fail":
                    return self.finish(False, "tuner: " + tuner["recommendation"])
            else:
                self.log("tuner", "code", True, why="phase has no GPU work; seat not needed")

            diff = git("diff", "--", *changed)[:60000] if changed else ""
            untracked = [f for f in changed if git("ls-files", "--error-unmatch", f).strip() == ""]
            evidence = (ctx + "\nPLAN ENVELOPE:\n" + json.dumps(plan, indent=2) +
                        "\nBUILDER ENVELOPE:\n" + json.dumps(build, indent=2) +
                        "\nTUNER ENVELOPE:\n" + json.dumps(tuner, indent=2) +
                        "\nQUALITY RESULTS (from code, verbatim):\n" + json.dumps(test, indent=2)[:20000] +
                        f"\nCHANGED FILES: {changed}\nNEW FILES (read them from disk): {untracked}\n"
                        "DIFF OF TRACKED FILES:\n" + diff)
            gate = self.seat("gatekeeper", evidence)
            if gate["verdict"] != "pass" or gate["blocking"]:
                return self.finish(False, "gatekeeper: " + "; ".join(gate["blocking"]))
            review = self.seat("reviewer", evidence)
            approved = review["approved"] and not review["blocking"]
            if not approved:
                return self.finish(False, "reviewer: " + "; ".join(review["blocking"]))

            statuses = self.item_statuses(review, test)
            phase_mark = "x" if all(s == "x" for s in statuses) else "wip"
            self.log("accept", "code", True, why=f"quality green, gatekeeper pass, reviewer approved; "
                                                  f"phase marker [{phase_mark}]")

            plan_path = ROOT / PLAN_REL
            doc = set_markers(plan_path.read_text(encoding="utf-8"), p.number, phase_mark, statuses)
            plan_path.write_text(doc, encoding="utf-8")
            docs = self.seat("documenter", evidence + "\nREVIEWER ENVELOPE:\n" + json.dumps(review, indent=2) +
                             f"\nRUN ID: {self.run_id}  SPENT SO FAR: ${self.spent:.2f}")
            stray = [f for f in docs["_touched"] if not DOC_PATHS.match(f.replace("\\", "/"))
                     and f.replace("\\", "/") != PLAN_REL]
            if stray:
                return self.finish(False, f"documenter changed files outside the vault: {stray}")
            self.commit(sorted(set(changed) | set(docs["_touched"]) | {PLAN_REL}))
            return self.finish(True)
        except SeatError as exc:
            return self.finish(False, str(exc))

    def item_statuses(self, review: dict, test: dict) -> list[str]:
        statuses = ["open"] * len(self.phase.items)
        for item in review["items"]:
            if 0 <= item["index"] < len(statuses):
                statuses[item["index"]] = item["status"]
        for r in test["results"]:
            for i in r["covers"]:
                if 0 <= i < len(statuses):
                    statuses[i] = {"pass": statuses[i] if statuses[i] != "open" else "x",
                                   "fail": "f", "manual": "open"}[r["status"]]
        return ["" if s == "open" else s for s in statuses]

    def commit(self, paths: list[str]) -> None:
        paths = [p for p in paths if (ROOT / p).exists() or p in git("ls-files")]
        if not paths:
            return
        git("add", "--", *paths, check=True)
        msg = f"adw(phase {self.phase.number}): {self.phase.name} [{self.run_id}]"
        git("commit", "-m", msg, check=True)
        sha = git("rev-parse", "--short", "HEAD").strip()
        self.log("commit", "code", True, why=f"{sha} on {git('branch', '--show-current').strip()}")
        if self.push:
            branch = git("branch", "--show-current").strip()
            git("push", "-u", "origin", branch, check=True)
            self.log("push", "code", True, why=f"origin/{branch}")


DRY_STEPS = [
    ("preflight", "code", "nvidia-smi receipt, gate state, branch"),
    ("gate", "code", "a Gated phase stops here unless training/gate.py criteria are signed"),
    ("scout", "agent", "read-only recon of the repo, the box and the live run"),
    ("planner", "agent", "step plan + validation commands that cover every plan check"),
    ("plan_check", "code", "coverage of plan checks, forbidden commands; one re-plan allowed"),
    ("builder", "agent", "implements the step plan in this checkout"),
    ("diff_check", "code", "claimed files == changed files; no data, weights or secrets"),
    ("test_n", "code", "runs every validation command; repairs loop at most 3 times"),
    ("tuner", "agent", "GPU phases: runs and measures (MFU, util, tok/s), may edit configs only"),
    ("gatekeeper", "agent", "read-only: clinical gate, public-repo hygiene, BUILD-PROMPT rules"),
    ("reviewer", "agent", "read-only, Codex if installed: checks each plan item against evidence"),
    ("accept", "code", "green quality AND gatekeeper pass AND reviewer approved"),
    ("documenter", "agent", "vault/training.md + session note; code sets plan markers"),
    ("commit", "code", "local commit on the adw branch; push only with --push"),
]



# ----------------------------------------------------------------------------- dashboard

VRAM_TARGET = (85.0, 92.0)


def gpu_metrics() -> dict:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"available": False}
    q = ("name,memory.used,memory.total,utilization.gpu,power.draw,power.limit,clocks.sm,"
         "temperature.gpu,clocks_throttle_reasons.active")
    proc = subprocess.run([smi, f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"available": False}
    f = [x.strip() for x in proc.stdout.splitlines()[0].split(",")]

    def num(v: str) -> float | None:
        try:
            return float(v)
        except ValueError:
            return None

    throttle = f[8].lower()
    return {"available": True, "name": f[0], "mem_used_mib": num(f[1]), "mem_total_mib": num(f[2]),
            "util_pct": num(f[3]), "power_w": num(f[4]), "power_limit_w": num(f[5]),
            "sm_mhz": num(f[6]), "temp_c": num(f[7]),
            # 0x1 is plain idle; anything else is a real slowdown (power, thermal, ...)
            "throttle": throttle not in ("0x0000000000000000", "0x0000000000000001", "[n/a]", "")}


def gpu_procs() -> list[dict]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    proc = subprocess.run([smi, "--query-compute-apps=pid,process_name,used_memory",
                           "--format=csv,noheader,nounits"], capture_output=True, text=True)
    rows = []
    for line in proc.stdout.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 3:
            try:
                rows.append({"pid": int(parts[0]), "name": Path(parts[1]).name, "used_mib": float(parts[2])})
            except ValueError:
                continue
    return sorted(rows, key=lambda r: -r["used_mib"])


def system_ram() -> dict:
    gib = 1024 ** 3
    if IS_WIN:
        import ctypes

        class MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = MemStatus()
        st.dwLength = ctypes.sizeof(MemStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return {"total_gb": st.ullTotalPhys / gib, "used_gb": (st.ullTotalPhys - st.ullAvailPhys) / gib}
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        kv = {l.split(":")[0]: float(l.split()[1]) * 1024 for l in meminfo.read_text().splitlines() if ":" in l}
        return {"total_gb": kv["MemTotal"] / gib, "used_gb": (kv["MemTotal"] - kv["MemAvailable"]) / gib}
    try:
        total = float(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        page = float(re.search(r"page size of (\d+)", vm).group(1))
        pages = lambda k: float(re.search(rf"{k}:\s+(\d+)", vm).group(1))  # noqa: E731
        used = (pages("Pages active") + pages("Pages wired down") + pages("Pages occupied by compressor")) * page
        return {"total_gb": total / gib, "used_gb": used / gib}
    except (ValueError, AttributeError, FileNotFoundError):
        return {"total_gb": None, "used_gb": None}


def memory_advice(gpu: dict, procs: list[dict]) -> dict:
    """One plain sentence on whether the model is using the card fully."""
    if not gpu.get("available"):
        return {"level": "idle", "text": "No NVIDIA GPU visible on this machine."}
    pct = 100 * gpu["mem_used_mib"] / gpu["mem_total_mib"]
    free_gb = (gpu["mem_total_mib"] - gpu["mem_used_mib"]) / 1024
    util = gpu["util_pct"] or 0
    lo, hi = VRAM_TARGET
    if not procs:
        return {"level": "idle", "text": "GPU idle: no model loaded. Idle hours count against the buy bar; "
                                         "queue the next job."}
    if pct > 95:
        return {"level": "danger", "text": f"{pct:.0f}% full: close to out-of-memory. Lower micro-batch "
                                           "or turn on offloaded checkpointing (uses system RAM)."}
    if pct < lo:
        return {"level": "headroom", "text": f"{free_gb:.1f} GB unused. Raise micro-batch (and lower "
                                             f"gradient accumulation) until memory sits at {lo:.0f}–{hi:.0f}%."}
    if util < 90:
        return {"level": "headroom", "text": f"Memory is full ({pct:.0f}%) but the GPU is only {util:.0f}% busy. "
                                             "It is waiting: check the data loader and per-step logging."}
    return {"level": "full", "text": f"Full use: memory {pct:.0f}% and GPU {util:.0f}% busy. Target met."}


class _ActiveRun:
    proc: subprocess.Popen | None = None
    cmd: str = ""
    started: str = ""
    log_path: Path | None = None
    exit_code: int | None = None
    since: float = 0.0


def _latest_receipt(since: float) -> dict | None:
    runs = ROOT / RUNS_REL
    receipts = sorted(runs.glob("*/receipt.json"), key=lambda p: p.stat().st_mtime) if runs.is_dir() else []
    if not receipts or receipts[-1].stat().st_mtime < since:
        return None
    try:
        return json.loads(receipts[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cmd_ui(args) -> int:
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    active = _ActiveRun()
    lock = threading.Lock()
    log_dir = ROOT / ".tunza-adw" / "ui"
    log_dir.mkdir(parents=True, exist_ok=True)

    def run_state() -> dict:
        with lock:
            running = active.proc is not None and active.proc.poll() is None
            if active.proc is not None and not running and active.exit_code is None:
                active.exit_code = active.proc.returncode
            tail = None
            if active.log_path and active.log_path.exists():
                tail = active.log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
            return {"active": running, "cmd": active.cmd, "started": active.started,
                    "exit_code": active.exit_code, "log_tail": tail,
                    "receipt": _latest_receipt(active.since) if active.since else None}

    def start(body: dict) -> tuple[int, dict]:
        with lock:
            if active.proc is not None and active.proc.poll() is None:
                return 409, {"error": "a workflow is already running"}
            mode = body.get("mode")
            argv = [sys.executable, str(Path(__file__).resolve()), "run"]
            if mode == "next":
                argv.append("--next")
            elif mode == "all":
                argv.append("--all")
            elif mode == "phase" and isinstance(body.get("phase"), int):
                argv += ["--phase", str(body["phase"])]
            else:
                return 400, {"error": "mode must be next, all or phase"}
            if body.get("dry_run"):
                argv.append("--dry-run")
            if body.get("push"):
                argv.append("--push")
            stamp = time.strftime("%Y%m%d-%H%M%S")
            active.log_path = log_dir / f"run-{stamp}.log"
            log = open(active.log_path, "w", encoding="utf-8")
            env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
            active.proc = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
            active.cmd = "tunza-adw " + " ".join(argv[2:])
            active.started = time.strftime("%H:%M:%S")
            active.exit_code = None
            active.since = time.time() - 1
            return 200, {"ok": True, "cmd": active.cmd}

    def stop() -> dict:
        with lock:
            if active.proc is not None and active.proc.poll() is None:
                active.proc.terminate()
                return {"ok": True}
            return {"ok": False, "error": "nothing running"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a) -> None:
            pass

        def send(self, code: int, payload, ctype: str = "application/json") -> None:
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                return self.send(200, (TOOL / "ui.html").read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/metrics":
                gpu, procs = gpu_metrics(), gpu_procs()
                return self.send(200, {"gpu": gpu, "procs": procs, "ram": system_ram(),
                                       "advice": memory_advice(gpu, procs), "t": time.time()})
            if self.path == "/api/state":
                try:
                    phases = [{"number": p.number, "name": p.name, "status": p.status, "gpu": p.needs_gpu,
                               "gated": p.gated} for p in load_phases()]
                except SystemExit as exc:
                    phases = [{"number": -1, "name": str(exc), "status": "f", "gpu": False, "gated": False}]
                state, why = gate_state()
                return self.send(200, {"phases": phases, "gate": {"state": state, "why": why}, "run": run_state()})
            self.send(404, {"error": "not found"})

        def do_POST(self) -> None:
            # Same-origin only: the page is served from this server, nothing else may start runs.
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"):
                return self.send(403, {"error": "cross-origin request refused"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self.send(400, {"error": "bad json"})
            if self.path == "/api/run":
                code, payload = start(body)
                return self.send(code, payload)
            if self.path == "/api/stop":
                return self.send(200, stop())
            self.send(404, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Tunza ADW dashboard: {url}  (Ctrl+C to quit)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# ----------------------------------------------------------------------------- CLI

def load_config() -> dict:
    return json.loads((TOOL / "config.json").read_text(encoding="utf-8"))


def load_phases() -> list[Phase]:
    path = ROOT / PLAN_REL
    if not path.is_file():
        raise SystemExit(f"plan not found: {path}")
    return parse_plan(path.read_text(encoding="utf-8"))


def ensure_branch(run_id: str, phase: Phase) -> str:
    branch = git("branch", "--show-current").strip()
    if branch.startswith("adw/"):
        return branch
    new = f"adw/model-build-{run_id}"
    git("switch", "-c", new, check=True)
    return new


def cmd_status(_args) -> int:
    for p in load_phases():
        done = sum(1 for t in p.items if t)
        print(f"[{p.status or ' '}] phase {p.number}: {p.name}  ({len(p.items)} checks, "
              f"{'GPU' if p.needs_gpu else 'no GPU'}{', gated' if p.gated else ''})")
    state, why = gate_state()
    print(f"\ngate: {state} ({why})")
    return 0


def cmd_doctor(_args) -> int:
    ok = True

    def row(name: str, good: bool, detail: str, required: bool = True) -> None:
        nonlocal ok
        ok = ok and (good or not required)
        print(f"  [{'ok ' if good else ('FAIL' if required else 'warn')}] {name:<14} {detail}")

    print(f"tunza-adw doctor · repo {ROOT}")
    row("python", sys.version_info >= (3, 11), sys.version.split()[0])
    row("git", bool(shutil.which("git")), shutil.which("git") or "missing")
    claude = claude_exe()
    ver = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip() if claude else ""
    row("claude", bool(claude), ver or "missing: irm https://claude.ai/install.ps1 | iex")
    if claude and claude.lower().endswith((".cmd", ".bat")):
        row("claude.exe", False, "only the npm claude.cmd was found; install the native one: "
            "irm https://claude.ai/install.ps1 | iex")
    row("codex", bool(shutil.which("codex")), "found: reviewer uses a second model family" if shutil.which("codex")
        else "not found: reviewer falls back to Claude", required=False)
    row("node/npm", bool(shutil.which("npm")), shutil.which("npm") or "missing (needed for app checks)",
        required=False)
    gpu = gpu_receipt()
    if gpu.get("available"):
        good = "5090" in gpu["name"] and gpu["memory_mib"] >= 30000
        row("gpu", good, f"{gpu['name']} · {gpu['memory_mib']:.0f} MiB · driver {gpu['driver']}")
    else:
        row("gpu", False, "nvidia-smi not available", required=IS_WIN)
    row("plan", (ROOT / PLAN_REL).is_file(), PLAN_REL)
    row("seats", all((TOOL / "seats" / f"{s}.md").is_file() for s in SEATS), ", ".join(SEATS))
    ignored = subprocess.run(["git", "check-ignore", "-q", "training/data/x"], cwd=ROOT).returncode == 0
    row("gitignore", ignored, "training/data is ignored" if ignored else "training/data is NOT ignored")
    state, why = gate_state()
    print(f"  [info] gate           {state} ({why})")
    print("\nready" if ok else "\nnot ready: fix the FAIL rows")
    return 0 if ok else 1


def cmd_run(args) -> int:
    config = load_config()
    phases = load_phases()
    if args.phase is not None:
        queue = [p for p in phases if p.number == args.phase]
    else:
        pending = [p for p in phases if p.status != "x"]
        queue = pending if args.all else pending[:1]
    if not queue:
        print("nothing to run: every phase is [x]" if args.phase is None else f"no phase {args.phase}")
        return 0 if args.phase is None else 2
    dirty = [l for l in git("status", "--porcelain", "--untracked-files=no").splitlines() if l.strip()]
    if dirty and not args.allow_dirty and not args.dry_run:
        print("tracked files have uncommitted changes; commit or stash them, or pass --allow-dirty:")
        print("\n".join("  " + l for l in dirty[:20]))
        return 2
    run_id = args.run_id or uuid.uuid4().hex[:8]
    if not args.dry_run:
        print(f"branch: {ensure_branch(run_id, queue[0])}")
    code = 0
    for phase in queue:
        run_dir = ROOT / RUNS_REL / f"{run_id}-p{phase.number}"
        run_dir.mkdir(parents=True, exist_ok=True)
        run = Run(phase=phase, run_id=run_id, run_dir=run_dir, seats=Seats(config, run_dir),
                  budget=args.budget or config["phase_budget_usd"], dry_run=args.dry_run, push=args.push)
        code = run.execute()
        if code != 0:
            break
        phases = load_phases()
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tunza-adw", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    run = sub.add_parser("run")
    pick = run.add_mutually_exclusive_group(required=True)
    pick.add_argument("--next", action="store_true")
    pick.add_argument("--phase", type=int)
    pick.add_argument("--all", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--push", action="store_true", help="push the adw branch when a phase is accepted")
    run.add_argument("--budget", type=float, default=None, help="USD cap per phase")
    run.add_argument("--allow-dirty", action="store_true")
    run.add_argument("--run-id", default=None)
    run.set_defaults(fn=cmd_run)
    ui = sub.add_parser("ui", help="open the red dashboard: run workflows, watch GPU and RAM")
    ui.add_argument("--port", type=int, default=8787)
    ui.add_argument("--no-open", action="store_true")
    ui.set_defaults(fn=cmd_ui)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
