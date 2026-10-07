#!/usr/bin/env python3
"""Build a self-contained Tunza context pack.

The output is the context. Paths inside it are labels for bytes that follow.
An agent on another computer must not need this Mac, this repo, or this script.
"""

from __future__ import annotations

import hashlib
import html
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = Path(__file__).resolve().parent

# (repo-relative path, fence language, what question the bytes answer)
EMBED = [
    ("lib/copy.ts", "ts", "Every user-visible string, English and Kiswahili. A missing Kiswahili string is a compile error."),
    ("DESIGN.md", "md", "The product contract: one next action, three surfaces, the referral spine."),
    ("lib/types.ts", "ts", "Roles, the four decision kinds, the referral lifecycle, the encounter shape."),
    ("lib/assessment.ts", "ts", "The demo floor. decide() is the only approved path. Not clinically validated."),
    ("lib/clinical/contract.ts", "ts", "Ten-section contract, disposition table, validators. No new user-visible headline."),
    ("lib/clinical/state.ts", "ts", "Append-only encounter projection. No single temperature. No clinical cutoff."),
    ("lib/clinical/reconcile.ts", "ts", "Floor wins. A lower or unapproved candidate is rewritten up. fail_open is false."),
    ("lib/clinical/pipeline.ts", "ts", "decide() then reconciler then contract. The UI does not call this yet."),
    ("lib/store.tsx", "tsx", "The reducer. The answer path still calls decide() directly and persists that Decision."),
    ("lib/referral.ts", "ts", "The only place referral state becomes words."),
    ("components/DecisionResult.tsx", "tsx", "The verdict component. One headline, one action."),
    ("components/surfaces/HouseholdSurface.tsx", "tsx", "Household renders the stored Decision, not the pipeline."),
    ("components/surfaces/ChpSurface.tsx", "tsx", "CHP uses the same DecisionResult."),
    ("components/surfaces/FacilitySurface.tsx", "tsx", "Facility speaks referral state, not a second clinical paragraph."),
    ("components/CarePath.tsx", "tsx", "Referral presentation goes through describeReferral."),
    ("evals/gates.ts", "ts", "Release machinery. Promotion is blocked. This file cannot authorize a release."),
    ("vault/architecture.md", "md", "Module map as written in the repo vault."),
    ("vault/decisions.md", "md", "Dated decisions, including why wave 1 is a contract and not a model."),
    ("vault/capability-map.md", "md", "What exists, what is missing, and which README claims are not code."),
    ("vault/wave1-contract.md", "md", "Wave-1 scope, deferrals, and the files that must not be edited."),
    ("vault/wave1-handoff.md", "md", "What was written, what was verified, and what is still blocked."),
    ("vault/wave2-ledger.md", "md", "Closed doors and the evidence required before any of them open."),
]

SECRET_MARKERS = (
    "sk-ant-",
    "sk-proj-",
    "sk-live-",
    "AKIA",
    "BEGIN PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load() -> list[dict]:
    loaded = []
    for rel, lang, why in EMBED:
        path = ROOT / rel
        if not path.is_file():
            raise SystemExit(f"missing source: {rel}")
        text = path.read_text(encoding="utf-8")
        for marker in SECRET_MARKERS:
            if marker in text:
                raise SystemExit(f"refusing to pack {rel}: found {marker}")
        loaded.append(
            {
                "rel": rel,
                "lang": lang,
                "why": why,
                "text": text,
                "sha": sha256(text),
                "lines": text.count("\n") + (0 if text.endswith("\n") or text == "" else 1),
            }
        )
    return loaded


def preamble(when: str, branch: str, head: str, status: str, files: list[dict]) -> str:
    index = "\n".join(
        f"- `{item['rel']}` — {item['why']} SHA-256 `{item['sha']}`."
        for item in files
    )
    dirty = status if status else "(clean)"
    return f"""# Tunza agent context pack

Generated {when}. Branch `{branch}`. HEAD `{head}`.
This pack snapshots the working tree, including uncommitted files. It is not origin/main.

## You are not on the machine that wrote this

This document is the context. Each path below is a label for source that is pasted in full under that same heading. The bytes are in this file.

Answer from those bytes. If a fact is not in this file, it is absent. Say absent. Do not search your disk for `~/code/Tunza`, and do not treat a path as a file you can open.

A filename is not a capability. The capability map embedded below is the reconciliation of README claims against code. The embedded code wins if a sentence and a file disagree.

## What you can decide from this pack

- The public app is a Next.js demo. `decide()` in `lib/assessment.ts` is the only approved decision path. The file says it is not clinically validated. Keep that label.
- The store still calls `decide()` when the question flow stops. `runClinicalPipeline` exists and no surface imports it.
- The contract has ten sections. They stay separate. `abstain` has no user-visible headline.
- A candidate below the floor, or an unapproved higher candidate, is rewritten to the floor. `fail_open` is false.
- There is no owned model, no training set, and no retrieval corpus in the embedded tree.
- Promotion stays blocked. Green tests are not a release.
- Training, retrieval ingestion, guideline thresholds, JEV, the private `medical-triage` route, and cross-encounter persistence stay closed. The opening tests are in the embedded wave-2 ledger. This pack does not supply that evidence.

## Working tree at pack time

```
{dirty}
```

## Index

{index}

## Embedded sources
"""


def render_md(when: str, branch: str, head: str, status: str, files: list[dict]) -> str:
    parts = [preamble(when, branch, head, status, files)]
    for item in files:
        parts.append(
            f"\n### `{item['rel']}`\n\n"
            f"{item['why']}\n\n"
            f"SHA-256 `{item['sha']}` · {item['lines']} lines\n\n"
            f"```{item['lang']}\n{item['text'].rstrip()}\n```\n"
        )
    return "".join(parts)


def render_html(when: str, branch: str, head: str, status: str, files: list[dict]) -> str:
    blocks = []
    for item in files:
        blocks.append(
            "<section class='src'>"
            f"<h2><code>{html.escape(item['rel'])}</code></h2>"
            f"<p>{html.escape(item['why'])}</p>"
            f"<p class='sha'>SHA-256 {html.escape(item['sha'])} · {item['lines']} lines</p>"
            f"<pre><code>{html.escape(item['text'].rstrip())}</code></pre>"
            "</section>"
        )
    body = html.escape(preamble(when, branch, head, status, files))
    # The preamble is markdown. Keep it readable in the PDF as preformatted text
    # so an agent who only receives the PDF still gets the rules before the source.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Tunza agent context pack</title>
<style>
  :root {{
    --ink: #1c1916;
    --paper: #f4efe6;
    --action: #7c1f18;
    --line: #e2d8c8;
    --raised: #fffcf7;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; background: var(--paper); color: var(--ink);
    font: 14px/1.45 Inter, Roboto, system-ui, sans-serif; }}
  main {{ max-width: 920px; margin: 0 auto; padding: 28px 22px 64px; }}
  h1 {{ font-size: 26px; margin: 0 0 8px; }}
  h2 {{ font-size: 16px; margin: 0 0 6px; }}
  .lead, pre.rules {{ white-space: pre-wrap; font: 13px/1.45 ui-monospace, Menlo, Consolas, monospace;
    background: var(--raised); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }}
  .src {{ margin-top: 28px; break-inside: auto; }}
  .sha {{ color: #5c564c; font-size: 12px; }}
  pre {{ white-space: pre-wrap; word-break: break-word; background: var(--raised);
    border: 1px solid var(--line); border-radius: 12px; padding: 12px; font-size: 11px; line-height: 1.35; }}
  @page {{ size: letter; margin: 0.55in; }}
  @media print {{
    * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    main {{ max-width: none; padding: 0; }}
    pre, .src {{ break-inside: auto; }}
    h2 {{ break-after: avoid; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Tunza agent context pack</h1>
  <p>Self-contained. Paths are labels. The source follows each heading.</p>
  <pre class="rules">{body}</pre>
  {''.join(blocks)}
</main>
</body>
</html>
"""


def verify(md: str, files: list[dict]) -> None:
    missing = []
    for item in files:
        if item["text"].rstrip() not in md:
            missing.append(item["rel"])
        if item["sha"] not in md:
            missing.append(item["rel"] + " hash")
    if missing:
        raise SystemExit("pack missing: " + ", ".join(missing))
    required = [
        "You are not on the machine that wrote this",
        "decide()",
        "not clinically validated",
        "fail_open",
        "SECTION_KEYS",
        "promotion: \"blocked\"",
        "trust_tier: \"none\"",
        "self-care",
    ]
    absent = [token for token in required if token not in md]
    if absent:
        raise SystemExit("pack missing required tokens: " + ", ".join(absent))


def main() -> None:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    head = git("rev-parse", "--short", "HEAD") or "unknown"
    status = git("status", "--short")
    files = load()
    md = render_md(when, branch, head, status, files)
    page = render_html(when, branch, head, status, files)
    verify(md, files)
    md_path = OUT_DIR / "TUNZA-AGENT-CONTEXT.md"
    html_path = OUT_DIR / "TUNZA-AGENT-CONTEXT.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(page, encoding="utf-8")
    # Re-read from disk. The written file is what the other computer receives.
    disk = md_path.read_text(encoding="utf-8")
    verify(disk, files)
    print(f"md {md_path} bytes {md_path.stat().st_size} files {len(files)}")
    print(f"html {html_path} bytes {html_path.stat().st_size}")
    print(f"pack_sha256 {sha256(disk)}")


if __name__ == "__main__":
    main()
