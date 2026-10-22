#!/usr/bin/env python3
"""Run every test_*.py here without pytest installed. No network, no GPU.

  python tools/tunza-train/run_tests.py            # all files
  python tools/tunza-train/run_tests.py test_live  # files whose name contains the word

unittest classes run through unittest. Plain test_ functions get tmp_path, capsys and the
module's @pytest.fixture values by argument name. When real pytest is installed it is used for
fixtures and skips only. live.gpu_info is stubbed so no test queries the GPU.
"""
from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import os
import sys
import tempfile
import traceback
import types
import unittest
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # torch, if imported, sees no GPU


class Skip(Exception):
    pass


def _stub_pytest() -> types.ModuleType:
    m = types.ModuleType("pytest")

    def fixture(fn=None, **_):
        def mark(f):
            f._fixture = True
            return f
        return mark(fn) if fn else mark

    def importorskip(name):
        try:
            return __import__(name)
        except ImportError:
            raise Skip(f"{name} not installed")

    m.fixture, m.importorskip = fixture, importorskip
    return m


try:
    import pytest  # noqa: F401
except ImportError:
    sys.modules["pytest"] = _stub_pytest()

Captured = namedtuple("Captured", "out err")


class Capsys:
    def __init__(self):
        self.out, self.err = io.StringIO(), io.StringIO()

    def readouterr(self):
        got = Captured(self.out.getvalue(), self.err.getvalue())
        self.out.seek(0), self.out.truncate(), self.err.seek(0), self.err.truncate()
        return got


def _no_gpu():
    live = sys.modules.get("live")
    if live is not None:
        live.gpu_info = lambda force=False: {"ok": False, "error": "gpu query stubbed by run_tests"}


# The code finds the Tunza sources two folders up, as in <repo>/tools/tunza-train. A copy kept
# elsewhere points at TUNZA_REPO instead. Read only: decide() is bundled into a temp folder.
REPO = Path(os.environ.get("TUNZA_REPO", HERE.parents[1]))
if not (REPO / "lib" / "assessment.ts").exists():
    REPO = Path.home() / "tunza-train"
os.environ["TUNZA_REPO"] = str(REPO)
ESBUILD = [Path(os.environ["ESBUILD"])] if os.environ.get("ESBUILD") else []
ESBUILD += [REPO / "node_modules" / "@esbuild" / "win32-x64" / "esbuild.exe",
            Path.home() / "Tunza" / "node_modules" / "@esbuild" / "win32-x64" / "esbuild.exe"]


def _repo_paths(mod):
    g = sys.modules.get("gen_cases")
    if g is not None:
        g.ASSESSMENT_TS = REPO / "lib" / "assessment.ts"
        g.ESBUILD_CANDIDATES = list(g.ESBUILD_CANDIDATES) + ESBUILD
    for k in ("TUNZA_CONTRACT", "TUNZA_RECONCILE"):
        if hasattr(mod, k) and not getattr(mod, k).exists():
            setattr(mod, k, REPO / getattr(mod, k).relative_to(mod.REPO))


def _load(path: Path):
    name = "_t_" + "_".join(path.relative_to(HERE).with_suffix("").parts)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_functions(mod, tally: dict) -> None:
    fixtures = {k: v for k, v in vars(mod).items() if callable(v) and getattr(v, "_fixture", False)}
    made, teardown = {}, []

    def value(arg, tmp):
        if arg == "tmp_path":
            return tmp
        if arg in made:
            return made[arg]
        fn = fixtures[arg]
        out = fn(*(value(a, tmp) for a in inspect.signature(fn).parameters))
        if inspect.isgenerator(out):
            teardown.append(out)
            out = next(out)
        made[arg] = out
        return out

    tests = [(k, v) for k, v in vars(mod).items() if k.startswith("test_") and inspect.isfunction(v) and v.__module__ == mod.__name__]
    for name, fn in tests:
        label = f"{mod.__file__.rsplit(os.sep, 1)[-1]}::{name}"
        cap = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                args = []
                for a in inspect.signature(fn).parameters:
                    if a == "capsys":
                        cap = Capsys()
                        args.append(cap)
                    else:
                        args.append(value(a, Path(tmp)))
                if cap:
                    with contextlib.redirect_stdout(cap.out), contextlib.redirect_stderr(cap.err):
                        fn(*args)
                else:
                    fn(*args)
            tally["pass"] += 1
        except Skip as e:
            tally["skip"] += 1
            print(f"SKIP {label}: {e}")
        except (Exception, SystemExit):
            tally["fail"] += 1
            print(f"FAIL {label}\n{traceback.format_exc()}")
    for gen in teardown:
        with contextlib.suppress(StopIteration):
            next(gen)


def main(argv: list[str]) -> int:
    files = sorted(p for p in HERE.rglob("test_*.py") if "__pycache__" not in p.parts and p.name != "run_tests.py")
    if argv:
        files = [p for p in files if any(w in p.name for w in argv)]
    tally = {"pass": 0, "fail": 0, "skip": 0}
    for path in files:
        try:
            mod = _load(path)
        except Skip as e:
            tally["skip"] += 1
            print(f"SKIP {path.name}: {e}")
            continue
        except Exception:
            tally["fail"] += 1
            print(f"FAIL {path.name} (import)\n{traceback.format_exc()}")
            continue
        _no_gpu()
        _repo_paths(mod)
        suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
        if suite.countTestCases():
            res = unittest.TextTestRunner(stream=sys.stdout, verbosity=0).run(suite)
            bad = len(res.failures) + len(res.errors)
            tally["fail"] += bad
            tally["skip"] += len(res.skipped)
            tally["pass"] += res.testsRun - bad - len(res.skipped)
        run_functions(mod, tally)
        print(f"{path.relative_to(HERE)}: done")
    print(f"\n{tally['pass']} passed, {tally['fail']} failed, {tally['skip']} skipped")
    return 1 if tally["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
