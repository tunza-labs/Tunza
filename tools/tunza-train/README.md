# tunza-train live page

A read-only page for Tunza decision-model training runs. It shows the plan, a method-by-seed grid, loss curves, the model's layers changing, and the machine's GPU, memory and disk. It never starts or stops a run.

    python tools/tunza-train/live.py --runs runs --port 8790

Open http://127.0.0.1:8790 on the training machine.

- With no runs it says so. Nothing on the page is sample data.
- If the GPU cannot be read, it shows the exact error instead of a number.
- GPU full use is 85 to 92% busy. The page warns when other programs share the card.
- `plan-status.json` holds phase names and checkbox counts only. Regenerate it from the plan page with `live.parse_plan_html`.
- Run folders follow the contract at the top of `live.py`.
- Engineering runs only. Nothing here is clinical or promoted.

Tests: `python -m pytest tools/tunza-train -q`
