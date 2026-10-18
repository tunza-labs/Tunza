#!/usr/bin/env bash
# Set up and start a Tunza LoRA run on an Apple Silicon Mac. Safe to re-run.
# It installs uv if missing, clones tunza-labs/Tunza (branch train/choice-model-live) into ~/code/tunza-train,
# builds a Python 3.12 environment there, runs the tests, opens the live page, and starts one training run.
# It does not touch anything outside ~/code/tunza-train and uv's own folders. It never pushes.
set -euo pipefail

echo "== This Mac =="
CHIP="$(sysctl -n machdep.cpu.brand_string)"
RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
echo "chip: $CHIP"
echo "memory: ${RAM_GB} GB"
df -h ~ | tail -1
if [ "$RAM_GB" -lt 12 ] && [ "${FORCE:-0}" != "1" ]; then
  echo "Under 12 GB of memory: not starting. Re-run with FORCE=1 to try anyway."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

mkdir -p ~/code && cd ~/code
if [ -d tunza-train/.git ]; then
  git -C tunza-train pull --ff-only
else
  git clone --depth 1 --branch train/choice-model-live https://github.com/tunza-labs/Tunza.git tunza-train
fi
cd tunza-train

[ -d .venv-train ] || uv venv --python 3.12 .venv-train
uv pip install --python .venv-train/bin/python torch 'transformers>=5' peft datasets accelerate pytest
.venv-train/bin/python -c "import torch; print('mps available:', torch.backends.mps.is_available())"
.venv-train/bin/python -m pytest tools/tunza-train -q

pkill -f "tunza-train/live.py" 2>/dev/null || true
nohup .venv-train/bin/python tools/tunza-train/live.py --runs runs --port 8790 > live.log 2>&1 &
sleep 2
open http://127.0.0.1:8790 || true

TAG="${TAG:-sft-0.8b-s0-m1}"
nohup .venv-train/bin/python tools/tunza-train/train.py --method "${METHOD:-sft}" --model Qwen/Qwen3.5-0.8B \
  --runs runs --tag "$TAG" --steps "${STEPS:-80}" --seed "${SEED:-0}" --batch "${BATCH:-1}" --accum "${ACCUM:-16}" > "$TAG.out.txt" 2> "$TAG.err.txt" &
caffeinate -i -w $! &
echo "Started $TAG. Watch it on the page that just opened. Logs: ~/code/tunza-train/$TAG.out.txt and .err.txt"
