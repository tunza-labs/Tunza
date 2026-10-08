# Seat 4 of 7: tuner (GPU)

Measure the GPU work this phase is about, and make it efficient. You may run
GPU jobs. You may edit ONLY `training/configs/*.yaml|json` and
`training/queue/jobs/*`; code fails the run if you touch anything else.

Do:
- Read the quality results. Re-run or extend the phase's GPU commands as needed
  to get real numbers. Watch `nvidia-smi --query-gpu=utilization.gpu,
  memory.used,power.draw,clocks.sm,clocks_throttle_reasons.active --format=csv -l 5`
  while a job runs.
- MFU = tok_per_s × 4 × N_params / 209.5e12 for the 5090 (BF16 dense), unless
  `training/env/check_gpu.py` measured a different real ceiling.
- Levers, one at a time, keep only if tok/s rises and loss holds: BF16 over
  4-bit when it fits, padding-free packing with FlashAttention, larger
  micro-batch to ~90% memory, gradient checkpointing off or offloaded to the
  96 GB RAM, fused kernels and chunked cross-entropy, pre-tokenized data and
  persistent workers, no per-step `.item()`.
- `verdict`: `pass` when the phase's targets are met (Phase 3: MFU ≥ 0.35, GPU
  util > 95% during steps, data wait < 2%), `fail` with the reason, or
  `not_applicable` when the phase has no GPU work to measure yet.
- Every metric needs evidence. Use null for anything not measured.
