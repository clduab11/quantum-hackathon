# GPU fit v4 preparation (PRA-246)

Status: runtime preparation and source audit only. The fitting driver is not
implemented yet. There is no v4 factor, numerical negative, or shipping claim.
PRA-245 supplies the declared THC factor and its hash before the ship-lane fit.
The Google-only run follows that fit, as requested by the board.

## CUDA dependency and preflight

The optional `gpu` dependency group pins PyTorch 2.8.0+cu128 from the explicit
PyTorch CUDA 12.8 index, with all resolved dependencies and wheel hashes in
`uv.lock`. This group supports Linux x86-64 (the authorized WSL runtime).
The index is used only for PyTorch. Other platforms do not install a CPU
substitute. No CUDA toolkit, system driver, service, or global Python is changed.
See the [PyTorch version instructions](https://pytorch.org/get-started/previous-versions/)
and [uv PyTorch guide](https://docs.astral.sh/uv/guides/integration/pytorch/).

From this worktree:

```sh
uv sync --group gpu
uv run --group gpu python -m tasks.dfthcsos.factor_gpu
/usr/lib/wsl/lib/nvidia-smi
uv run --group gpu pytest tests/test_factor_gpu.py
```

The full repository suite also needs the existing project-local kickmix
installer because some test subprocesses replace `PYTHONPATH`:

```sh
uv run --group gpu python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run
uv run --group gpu python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
uv run --group gpu pytest
```

That existing installer checks the binary hash and writes only this worktree's
`.venv/lib/python3.13/site-packages/vqcc_local.pth`. Its rollback is
`uv run --group gpu python scripts/uninstall_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation`.

`factor_gpu` checks real CUDA matrix multiplication and backward gradients in
float32 and float64. It returns JSON with device, runtime versions, capability,
memory and checks. This verifies runtime readiness, not numerical accuracy of
a factor. GPU memory is a point-in-time reading, not a reserved allocation.

Prerequisites: the WSL GPU device/driver and internet access for the initial
dependency download. The command writes no files and invokes no subprocesses
or network services. Exit 1 prints the corrective action to stderr if PyTorch,
CUDA, or a numerical operation fails; it never selects CPU. `--help` works
without PyTorch. The deliberate failing case is:

```sh
CUDA_VISIBLE_DEVICES='' uv run --group gpu python -m tasks.dfthcsos.factor_gpu
```

It must exit 1 and say `CPU fitting is forbidden`. **Fail loudly, fail early**
and **The check must be able to fail** drive this boundary. **No hidden state**:
`CUDA_VISIBLE_DEVICES` controls visible GPUs; `cuda:0` means the first visible
GPU. No factor, checkpoint or credentials are discovered implicitly.

A plain `uv sync` omits the optional GPU group. Use `--group gpu` on fitting
and test commands so uv retains PyTorch. Use a separate worktree/venv per run.
Removing this runtime helper affects only its CLI and its tests; no existing
fitter calls it yet. There is no deployed service or machine change to undo.

## Published schedule audit

Source parent: anazemcev / Artem1410 / ViberTeam, *Quantum Circuits — 881Q
Paired DQI + R6 DF-THC*, v6, Apache-2.0, notebook SHA-256
`d4a147523ac07cb2dc5fe4bd5dc9c7da48719e34dfc847402628723b37930682`.
URL: https://www.kaggle.com/code/anazemcev/quantum-circuits-881q-paired-dqi-r6-df-thc.
The pinned dataset v2 source URLs and individual hashes are in
`ledger/evidence/pra242/method-parents.json`; the v4 audit rechecks those bytes.
This preparation copies no upstream implementation or numerical array.

| Stage | Published driver / implementation settings |
|---|---|
| Continuous merge branch | `run_gpu_qat.py`: 8 initializer sweeps; 8000 outer L-BFGS steps; 700-second maximum within session; float32 CUDA; checkpoint every 100; regularizer 2e-6 |
| L-BFGS internals | `structural_train.py`: 5 inner iterations, history 20, strong Wolfe, learning rate 1, gradient tolerance 1e-10, change tolerance 1e-13; retain best exact float64 residual snapshot; stop after >=100 steps if <15 mHa |
| Tangent Gauss–Newton | 300 iterations, 100 PCG iterations each, 450-second maximum within session; damping starts 0.001; six backtracking scales; stop at <15 mHa or failed damping at 100 |
| Continuous gate | Residual >30 mHa skips quantisation in the source driver |
| Progressive freeze | `qat_pipeline.py`: fractions 0.2/0.4/0.6/0.75/0.85/0.92/0.97/1; 800 Adam steps per fraction; driver passes 1600 final steps; 4 importance probes; seed 95101; kappa 0 |
| Adam details | Weight LR 3e-4, free-angle LR 1e-3; each decays by 0.2 over a stage; retain best every 25 steps; signed half-open angle lattice |
| Fixed-word QR | Driver passes 350 physical iterations, history 15, max line searches 30, ftol 1e-14, gtol 1e-8; retain best residual |
| Offset + column gauge | Two rounds; 400 offset iterations; gauge: 5×60 proximal steps, 2×40 Cayley steps with 9 line-search trials, 3 plane sweeps |
| Joint barrier | 100 iterations for each of mu=1e-3/1e-4/1e-5; error2 cap 19.999 mHa, gap floor 3.915048, Lambda floor 49.001; entry requires physical error2 below cap |
| Two-body integer repair | If 20<error2<30 mHa: 2 rounds, 90 seconds each, up to 256 steps, 150 weight-fit iterations; then postprocess with 150 physical / 60 joint iterations |
| One-body integer repair | If error1>19.5 mHa: target 19.5 mHa, up to 2000 steps / 60 seconds |

The public driver also imposes a 6900-second multi-case session budget and
remaining-time skips. Its bit sequence is 12/10/9, with 9 conditional on a
passing 10-bit point. Its merge case is (6,157,127), not (1,496,384).
The task specifically requests the THC shape and 11 then 8 bits, so these are
declared adaptations, not a literal replay of an upstream THC training run.
Gluzdov v14 describes the shape but does not publish its optimizer; this does
not prevent reusing the published R6 methods at the declared THC shape.

The v4 implementation must record all settings and actual stop reasons. It
must not silently replace the full iteration limits with PRA-242's CPU
fraction, inherit unrelated-case session skips, or declare a negative because
a wall clock expires. Source time limits and task-driven changes must remain
explicit. The published QR/barrier/gauge routines use NumPy/SciPy; the driver
uses CUDA for continuous/GN/QAT and two-body repair. That hybrid fact must be
reported accurately instead of describing every source operation as CUDA.

## Input and completion boundary

Wait for John Wick's PRA-245 handoff: selected file under
`/home/cld-main/work/vqcc-data/inputs/thc/`, SHA-256, dataset/version/licence,
array schema, encoding and unmodified-verifier metrics. Intake must verify the
hash and shape before any fit. Binary inputs and outputs stay outside git.

Remaining implementation: adapt continuous/GN/QAT, fixed-word QR/joint barrier,
column gauge and integer repair into small modules; exclusive checkpoints via
`factor_progress.py`; evaluator-backed reporting after every saved point;
tests for new numerical paths; ship-lane run first, Google-only run second.
Use a fixed optimizer seed without modifying verifier salts or grinding seeds.

Every point needs shape, bits, error1/error2, Lambda, E_gap, lambda_eff,
predicted T/Q/ratio, elapsed time, GPU memory, source/input/checkpoint hashes.
Acceptance is error1 and error2 <=20 mHa (aim <=19.5), Lambda>49.0,
E_gap>3.914898 using the unchanged competition verifier. Hand a passing
factor hash to T4 immediately. Circuit verification and Kaggle submission
belong to the downstream task and John Wick. This draft is not ready to merge.
