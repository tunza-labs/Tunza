#!/usr/bin/env python3
"""Small stdlib HTTP server for the Tunza triage model. Nothing is loaded at import time.

  python serve/serve_model.py --adapter runs/<tag>/adapter [--model Qwen/Qwen3.5-0.8B] [--port 8765] [--timeout 20]

POST /v1/triage  {"intake": {...}, "language": "en"}  -> harness.triage() result
GET  /health                                           -> model and rules state

The base model and adapter are loaded on the first triage request, inside the single model worker, through
eval_adapter.resolve_base and eval_adapter.load_model (the same path eval_adapter.py scores with). Requests that
arrive while it loads, or that pass the timeout, get the rules fallback. Batch size is 1: one worker runs one
generation at a time.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

MAX_BODY_BYTES = 16 * 1024
NO_GPU = ("no GPU visible (torch.cuda and mps are both unavailable): the model is not loaded and every request "
          "is answered by the rules fallback. Pass --allow-cpu to load on CPU (slow).")


class NoGPU(RuntimeError):
    pass


class LazyModel:
    """Callable prompt -> raw text. Loads on the first call and keeps the first load error for /health."""

    def __init__(self, adapter: str, model: str | None, max_new: int = 100, allow_cpu: bool = False, loader=None) -> None:
        self.adapter, self.model, self.max_new, self.allow_cpu = adapter, model, max_new, allow_cpu
        self._loader = loader or self._load_real
        self._generate = None
        self._lock = threading.Lock()
        self.state = "not_loaded"
        self.error: str | None = None

    def _load_real(self):
        try:
            import torch
        except ImportError as exc:
            raise NoGPU(f"torch is not installed ({exc}); " + NO_GPU) from None
        cuda = torch.cuda.is_available()
        if not cuda and not torch.backends.mps.is_available() and not self.allow_cpu:
            raise NoGPU(NO_GPU)
        sys.path.insert(0, str(harness.TOOLS))
        import eval_adapter as ea
        from train import chat_prompt_ids

        base = ea.resolve_base(Path(self.adapter), self.model)
        model, tok = ea.load_model(base, self.adapter, cuda)
        tok = getattr(tok, "tokenizer", tok)
        model.eval()
        device = next(model.parameters()).device
        im_end = tok.convert_tokens_to_ids("<|im_end|>")
        pad = tok.pad_token_id if tok.pad_token_id is not None else im_end
        max_new = self.max_new

        @torch.no_grad()
        def generate(prompt: str) -> str:
            ids = torch.tensor([chat_prompt_ids(tok, prompt)], device=device)
            res = model.generate(input_ids=ids, max_new_tokens=max_new, do_sample=False,
                                 eos_token_id=[im_end, tok.eos_token_id], pad_token_id=pad)
            return tok.decode(res[0, ids.shape[1]:], skip_special_tokens=True).strip()

        return generate

    def __call__(self, prompt: str) -> str:
        with self._lock:
            if self._generate is None:
                if self.error is not None:
                    raise NoGPU(self.error)
                self.state = "loading"
                try:
                    self._generate = self._loader()
                except Exception as exc:  # noqa: BLE001  keep serving rules; report the reason on /health
                    self.state, self.error = "failed", f"{type(exc).__name__}: {exc}"
                    raise
                self.state = "ready"
        return self._generate(prompt)


def make_handler(generate, rules, timeout_s: float, executor: cf.Executor, model_state):
    class Handler(BaseHTTPRequestHandler):
        server_version = "tunza-serve/1"

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):  # request line and status only; bodies are never logged
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

        def do_GET(self):
            if self.path != "/health":
                return self._send(404, {"error": "not found"})
            self._send(200, {"status": "ok", "batch_size": 1, "timeout_s": timeout_s, **model_state()})

        def do_POST(self):
            if self.path != "/v1/triage":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY_BYTES:
                return self._send(400, {"error": f"body must be 1..{MAX_BODY_BYTES} bytes"})
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return self._send(400, {"error": "body is not JSON"})
            if not isinstance(body, dict) or "intake" not in body:
                return self._send(400, {"error": "body must be {\"intake\": {...}, \"language\": \"en|sw|cs\"}"})
            try:
                result = harness.triage(body["intake"], generate=generate, rules=rules, timeout_s=timeout_s,
                                        language=body.get("language", "en"), executor=executor)
            except harness.IntakeError as exc:
                return self._send(400, {"error": str(exc)})
            except harness.RulesUnavailable as exc:
                return self._send(503, {"error": f"rules unavailable, no answer given: {exc}"})
            self._send(200, result)

    return Handler


def make_server(generate, rules, timeout_s: float = 20.0, host: str = "127.0.0.1", port: int = 8765,
                model_state=lambda: {"model": "none"}) -> ThreadingHTTPServer:
    executor = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="model")  # batch size 1
    server = ThreadingHTTPServer((host, port), make_handler(generate, rules, timeout_s, executor, model_state))
    server.model_executor = executor
    return server


def main() -> int:
    ap = argparse.ArgumentParser(description="Tunza triage server (rules floor + LoRA model)")
    ap.add_argument("--adapter", help="runs/<tag>/adapter; omit to serve the rules answer only")
    ap.add_argument("--model", default=None, help="base model; default: the base recorded in adapter_config.json")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds per model call, including queue wait")
    ap.add_argument("--max_new", type=int, default=100)
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--repo", default=str(harness.DEFAULT_REPO), help="checkout with lib/assessment.ts and esbuild")
    a = ap.parse_args()
    if a.adapter:
        folder = Path(a.adapter)
        if not ((folder / "adapter_config.json").is_file() or (folder / "config.json").is_file()):
            ap.error(f"{a.adapter} holds neither adapter_config.json (LoRA) nor config.json (full fine-tune)")
    model = LazyModel(a.adapter, a.model, a.max_new, a.allow_cpu) if a.adapter else None
    rules = harness.DecideRules(Path(a.repo))

    def state() -> dict:
        if model is None:
            return {"model": "none (rules only)"}
        return {"model": model.state, "model_error": model.error, "adapter": a.adapter}

    server = make_server(model, rules, a.timeout, a.host, a.port, state)
    print(f"serving on http://{a.host}:{a.port} (model loads on first request)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.model_executor.shutdown(wait=False, cancel_futures=True)
        rules.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
