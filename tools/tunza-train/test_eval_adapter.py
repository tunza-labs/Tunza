import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import eval_adapter as ea  # noqa: E402


class _LoaderCalled(Exception):
    pass


def _adapter_dir(tmp, base):
    d = Path(tmp) / "adapter"
    d.mkdir()
    if base is not None:
        (d / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": base}))
    return d


def _fake_modules(seen):
    # Stand-ins for torch, transformers, peft and unsloth. They record calls; no model or GPU is touched.
    torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False),
                                  backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)),
                                  bfloat16="bf16", float32="f32")

    def loader(kind):
        return types.SimpleNamespace(from_pretrained=lambda path, **kw: seen.setdefault(kind, []).append(path) or kind)

    transformers = types.SimpleNamespace(AutoModelForCausalLM=loader("model"), AutoTokenizer=loader("tok"))
    peft = types.SimpleNamespace(PeftModel=types.SimpleNamespace(
        from_pretrained=lambda base, path: seen.setdefault("peft", []).append((base, path)) or "peft"))
    unsloth = types.SimpleNamespace(FastLanguageModel=types.SimpleNamespace(
        from_pretrained=lambda path, **kw: seen.setdefault("unsloth", []).append(path) or ("u", "t"),
        for_inference=lambda m: None))
    return {"torch": torch, "transformers": transformers, "peft": peft, "unsloth": unsloth}


class ResolveBaseTest(unittest.TestCase):
    def test_explicit_model_wins_over_the_recorded_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, "Qwen/Qwen3.5-0.8B")
            with mock.patch("sys.stderr"):
                self.assertEqual(ea.resolve_base(d, "Qwen/Qwen3.5-4B"), "Qwen/Qwen3.5-4B")

    def test_no_model_uses_the_recorded_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, "Qwen/Qwen3.5-4B")
            self.assertEqual(ea.resolve_base(d, None), "Qwen/Qwen3.5-4B")

    def test_no_model_and_no_config_falls_back_to_the_default_with_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, None)
            with mock.patch("sys.stderr") as err:
                self.assertEqual(ea.resolve_base(d, None), ea.DEFAULT_BASE)
            self.assertIn("no base recorded", "".join(c.args[0] for c in err.write.call_args_list))

    def test_conflicting_model_prints_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, "Qwen/Qwen3.5-0.8B")
            with mock.patch("sys.stderr") as err:
                ea.resolve_base(d, "Qwen/Qwen3.5-4B")
            self.assertIn("differs", "".join(c.args[0] for c in err.write.call_args_list))

    def test_corrupt_config_warns_and_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, None)
            (d / "adapter_config.json").write_text("{not json")
            with mock.patch("sys.stderr") as err:
                self.assertEqual(ea.resolve_base(d, None), ea.DEFAULT_BASE)
            self.assertIn("cannot read", "".join(c.args[0] for c in err.write.call_args_list))


class LoadModelBranchTest(unittest.TestCase):
    def _load(self, base, cuda, asked=None):
        seen = {}
        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, base)
            with mock.patch.dict(sys.modules, _fake_modules(seen)), mock.patch("sys.stderr") as err:
                ea.load_model(asked or base or ea.DEFAULT_BASE, str(d), cuda)
            seen["stderr"] = "".join(c.args[0] for c in err.write.call_args_list)
            return seen, str(d)

    def test_cpu_lora_loads_the_base_then_attaches_the_adapter(self):
        seen, d = self._load("Qwen/Qwen3.5-4B", cuda=False)
        self.assertEqual(seen["tok"], ["Qwen/Qwen3.5-4B"])
        self.assertEqual(seen["model"], ["Qwen/Qwen3.5-4B"])
        self.assertEqual(seen["peft"], [("model", d)])

    def test_cpu_full_fine_tune_loads_the_folder_itself(self):
        seen, d = self._load(None, cuda=False)
        self.assertEqual(seen["tok"], [d])
        self.assertEqual(seen["model"], [d])
        self.assertNotIn("peft", seen)

    def test_cuda_loads_the_folder_through_unsloth(self):
        seen, d = self._load("Qwen/Qwen3.5-4B", cuda=True)
        self.assertEqual(seen["unsloth"], [d])
        self.assertNotIn("peft", seen)
        self.assertEqual(seen["stderr"], "")

    def test_cuda_says_a_different_model_is_ignored(self):
        seen, _ = self._load("Qwen/Qwen3.5-0.8B", cuda=True, asked="Qwen/Qwen3.5-4B")
        self.assertIn("is ignored", seen["stderr"])


class MainPassesBaseToLoaderTest(unittest.TestCase):
    def _run_main(self, argv, recorded="Qwen/Qwen3.5-4B"):
        # The loader is mocked. It records what main asks for, then stops the run before any model work.
        seen = {}

        def fake_loader(base, adapter, cuda):
            seen.update(base=base, adapter=adapter, cuda=cuda)
            raise _LoaderCalled

        with tempfile.TemporaryDirectory() as tmp:
            d = _adapter_dir(tmp, recorded)
            argv = ["eval_adapter.py", "--adapter", str(d), "--file", str(Path(tmp) / "x.jsonl"), "--out", str(Path(tmp) / "o.json")] + argv
            with mock.patch.object(ea, "load_model", fake_loader), mock.patch.object(sys, "argv", argv), \
                    mock.patch.dict(sys.modules, {"torch": _fake_modules({})["torch"]}):
                with self.assertRaises(_LoaderCalled):
                    ea.main()
            seen["dir"] = str(d)
        return seen

    def test_explicit_non_default_model_reaches_the_loader(self):
        with mock.patch("sys.stderr"):
            seen = self._run_main(["--model", "Qwen/Qwen3.5-4B"], recorded="Qwen/Qwen3.5-0.8B")
        self.assertEqual(seen["base"], "Qwen/Qwen3.5-4B")

    def test_omitted_model_reaches_the_loader_as_the_recorded_base(self):
        # the recorded base is not DEFAULT_BASE, so a resolve_base that ignored the config would fail here
        seen = self._run_main([])
        self.assertNotEqual(ea.DEFAULT_BASE, "Qwen/Qwen3.5-4B")
        self.assertEqual(seen["base"], "Qwen/Qwen3.5-4B")
        self.assertEqual((seen["adapter"], seen["cuda"]), (seen["dir"], False))

    def test_folder_without_adapter_or_model_config_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("sys.stderr") as err:
            argv = ["eval_adapter.py", "--adapter", tmp, "--file", "x.jsonl", "--out", "o.json"]
            with mock.patch.object(sys, "argv", argv), self.assertRaises(SystemExit):
                ea.main()
        self.assertIn("neither adapter_config.json", "".join(c.args[0] for c in err.write.call_args_list))


class BaseUsedTest(unittest.TestCase):
    def test_base_recorded_in_the_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            lora = _adapter_dir(tmp, "Qwen/Qwen3.5-4B")
            self.assertEqual(ea.base_used("Qwen/Qwen3.5-4B", str(lora), cuda=False), "Qwen/Qwen3.5-4B")
            # on CUDA unsloth uses the recorded base, whatever --model said
            self.assertEqual(ea.base_used("Qwen/Qwen3.5-2B", str(lora), cuda=True), "Qwen/Qwen3.5-4B")
        with tempfile.TemporaryDirectory() as tmp:
            full = _adapter_dir(tmp, None)
            self.assertEqual(ea.base_used(ea.DEFAULT_BASE, str(full), cuda=True), str(full))


if __name__ == "__main__":
    unittest.main()
