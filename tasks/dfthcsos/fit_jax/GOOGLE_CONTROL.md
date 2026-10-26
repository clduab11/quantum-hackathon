# Google baseline control

`google_control.py` runs the pinned Google (65,60,60) baseline through the
existing JAX feasible optimizer and official circuit cascade. It uses 12-bit
words, 300 fit seconds, at most 32 steps and rate 1e-4. It makes no shape change
and no new objective or acceptance rule. Its success condition is official
stage-3 PASS, without the public-factor smoke's 4x threshold. A negative or
timeout is evidence, not permission to extend the run.

Requires Python 3.13, `uv sync --locked --group gpu`, the hash-pinned starter
and competition packages, an available GPU, and this checkout's pinned
verifier paths installed as described in README.md. Run from the repo root:

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 timeout --kill-after=5 1190 \
  uv run --locked --group gpu python -m tasks.dfthcsos.fit_jax.google_control \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --out /home/cld-main/work/vqcc-data/pra251-google-control-01
```

The default validates pinned inputs and GPU without writing. Add `--execute`
for the authorized control. Keep the outer timeout: the optimizer's budget
alone cannot bound compilation, verification or an individual GPU operation.
The timeout stops the command after 1,190 seconds (with five seconds to kill).
Longer runs and TPU runs require John Wick's approval; this command is for GPU.

Only the new output directory is written: checkpoints, step logs, factor,
generated circuits, evaluator artifacts and report. Inputs, seeds and verifier
salts are unchanged. Missing GPU, changed pins, existing output, mirror
disagreement or verification failure exits nonzero. Check `report.json` and
the process exit code; a checkpoint without an official PASS is unverified.
Do not upload it. Timeout exit 124/137 is incomplete, never a PASS.

Documented guard check: repeat the dry run with `--starter /does-not-exist`;
it must fail nonzero and create no output. On real pinned input the dry run
must return shape `[65,60,60]`, `dry_run: true` and a GPU device. A repeated
execution using the same output must fail without overwriting it.
