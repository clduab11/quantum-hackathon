# PRA-246 runtime preparation evidence

Recorded 2026-10-26 on `op-vqcc/PRA-246-factor-fit-v4`, cut from
`origin/main` at `c1961501dd4f299a0d2218b2fd07bc2c1b917dc1`.
This is preparation for fit v4. No chemistry fit, checkpoint or numerical
negative was produced. PRA-245's selected declared factor/hash is pending.

- `gpu-preflight.json`: real CUDA float32/float64 forward/backward result.
- `gpu-negative.json`: hidden GPU returns exit 1, with no CPU fallback.
- `gpu-wheels.json`: all 22 installed dependencies added for the GPU group,
  matched to exact filenames/URLs/SHA-256 records in `uv.lock` by installed
  version and wheel tags. These are lockfile hashes, not a separate redownload.
- `nvidia-smi.txt`: authorized WSL RTX 4060 Ti device and driver snapshot.
- `source-audit.json`: all 24 cached source files match PRA-242's published
  Apache-2.0 parent pins. Upstream training code was read, not executed.
- `pytest-default.txt`: initial full-suite failure and diagnosed environment
  prerequisite. The existing kickmix installer corrects it within this venv.
- `pytest-gpu.txt`: final full-suite output with the optional group installed.

Commands and source schedule are documented in `tasks/dfthcsos/FIT_V4.md`.
The runtime check command was:

```sh
uv run --group gpu python -m tasks.dfthcsos.factor_gpu
```

It exited 0: RTX 4060 Ti, capability 8.9, torch 2.8.0+cu128, CUDA runtime
12.8, Python 3.13.13, both precision checks PASS. Peak allocated memory was
17,043,968 bytes. This tiny runtime check does not estimate fit peak memory.

The deliberately failing check was:

```sh
CUDA_VISIBLE_DEVICES='' uv run --group gpu python -m tasks.dfthcsos.factor_gpu
```

It exited 1 and printed:

```text
factor GPU: CUDA is unavailable; check WSL GPU access and CUDA_VISIBLE_DEVICES; CPU fitting is forbidden
```

The focused test run `uv run --group gpu pytest tests/test_factor_gpu.py -q`
reported `3 passed in 8.89s`. `uv sync` and `uv sync --group gpu` both passed.
No main commit, submission, system driver change or external service operation
is part of this preparation. No source or factor provenance hold is imposed.
