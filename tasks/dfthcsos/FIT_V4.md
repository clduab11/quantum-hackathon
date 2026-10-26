# GPU fit v4 (PRA-246)

Status: the declared-input run04 completed with exit 3 on 2026-10-26 at
07:42 UTC. Final 8-bit errors are 22.091251207 and 63.720988762 mHa, both
above 20 mHa. This is a measured negative for the full published-method
schedule at the declared THC shape, not a proof that all 8-bit fits are impossible.
The separate Google-only run01 started at 07:51 UTC with no public-factor
checkpoint or completed-stage resume. It remains incomplete.

Final declared report and every checkpoint hash are in
`ledger/evidence/pra246/declared-v4-04-report.json`; the result summary records
all source gates. The 8-bit joint barrier and two-body integer repair were
ineligible under their published error-entry gates. One-body repair used all
2000 steps and reduced error1 from 50.268023166 to 22.091251207 mHa.
The unmodified competition evaluator measured every saved point.

## Run the declared factor

```sh
uv run --group gpu python -m tasks.dfthcsos.factor_fit_v4 \
  --starter /home/cld-main/work/vqcc-data/starter-kit \
  --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
  --factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz \
  --sha256 809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5 \
  --source-bits 11 --out /home/cld-main/work/vqcc-data/pra246-declared-v4-01 --dry-run
```

Remove `--dry-run` to fit. Both forms check all declared input/package hashes
and real CUDA operations. Dry-run writes no files. The fitter writes a new
`--out` directory and refuses any existing output path. No source checkpoint is
overwritten. No network, service, credentials, circuit or Kaggle call occurs.
Exit 0 means a verified numerical 8-bit point passed (or successful dry-run),
3 means the published schedule completed without one, and 1 means an error.
An interrupted run has `progress.json` but no completed `report.json`.

For the second run use `--factor` pointing to the starter-kit
`starter_kit/starter/task1_factorization/FeMoco76_65_60_60.npz` and its exact hash
from `ledger/manifests/inputs/pra198-google-v4.json`, with a new output directory.
Only the two declared hashes are admitted. The Google initializer is merged
with 8 PSD sweeps to (1,496,384) using the existing tested initializer. No
public factor, learned checkpoint or word table enters that run.

Implementation map: `gpu_fit/continuous.py` runs the published Torch L-BFGS
and GN stage methods. `quantize.py` ports Ahmed's progressive freezing with
Torch compilation; `fixed.py` ports fixed-word QR and the joint barrier;
`gauge.py` ports augmented column rotations; `integer.py` and `one_body.py`
port exact discrete repair. `native.py` adapts these to the unchanged official
`evaluate_words`; `reporting.py` persists exclusive checkpoints through
`factor_progress.py`, encoded snapshots, metrics and best ordinary-QROM layout
under the 128-qubit cap. `port-map.json` identifies the exact selected source
functions. This is attributed source reuse, not a claim of independent invention.

The source float32 CUDA precision, iteration/time budgets, convergence gates
and float64 physical checks are retained. The task's shape, warm start and
11-then-8 continuation replace the source's unrelated multi-case search and
independent 12/10/9 branches. Postprocessing retains the incoming `H2_I`
warm start rather than resetting that array to zero as the upstream driver
does; the same published offset optimization then runs. CPU helpers are the published QR/barrier/gauge/
one-body routines; the complete fit cannot start without CUDA and is never a
CPU-only run. The optimizer seed is 95101, TF32 is off, deterministic Torch
algorithms are required, and `CUBLAS_WORKSPACE_CONFIG=:4096:8` is explicit.
No cross-hardware bit-for-bit optimizer claim is made. Fixed NPZ metadata
and ordered keys make a given checkpoint deterministic to serialize.

Every persisted numerical point includes its exact words, factor hash,
shape/bits, error1/error2, Lambda, E_gap, lambda_eff, predicted T/Q/ratio,
wall-clock and peak GPU allocation. `passing-8bit.json` appears only after
serialized-file reload and a second unchanged-evaluator pass. It is a
numerical handoff, not a full circuit-verifier or submission authorization.
Raw `inflight-*` files remain explicitly unverified; the corresponding encoded
point has the official numerical result. If a source hash changes mid-run,
the driver rejects completion and retains partial evidence.

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
Removing this runtime helper affects its CLI, its tests and the v4 fitter,
which calls it before writing any checkpoint. There is no deployed service or machine change to undo.

## Published schedule audit

Source parent: anazemcev / Artem1410 / ViberTeam, *Quantum Circuits — 881Q
Paired DQI + R6 DF-THC*, v6, Apache-2.0, notebook SHA-256
`d4a147523ac07cb2dc5fe4bd5dc9c7da48719e34dfc847402628723b37930682`.
URL: https://www.kaggle.com/code/anazemcev/quantum-circuits-881q-paired-dqi-r6-df-thc.
The pinned dataset v2 source URLs and individual hashes are in
`ledger/evidence/pra242/method-parents.json`; the v4 audit rechecks those bytes.
Selected mathematical source definitions are ported with attribution. No upstream
loader, CLI, circuit or numerical payload is copied into code.

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

The driver records settings and actual stop reasons. It retains full published
iteration limits and source per-stage time limits (700/450 seconds), and removes
unrelated-case remaining-session skips. A source-time-limit stop is reported
as such, never as convergence or proof of shape infeasibility. The published QR/barrier/gauge routines use NumPy/SciPy; the driver
uses CUDA for continuous/GN/QAT and two-body repair. That hybrid fact must be
reported accurately instead of describing every source operation as CUDA.

## Input and completion boundary

John Wick's PRA-245 handoff selected Gluzdov v8, SHA-256
`809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5`.
Intake independently reproduces error1 6.383440999 mHa, error2 19.999496917
mHa, Lambda 294.453313580, gap 3.914898049999465, lambda_eff 47.855856272.
The file is immutable and remains outside git. `ledger/evidence/pra246/intake.json`
contains the full result. The documented source methods, not these original
numbers, determine whether an 8-bit refit passes.

Check new numerical paths with `uv run --group gpu pytest tests/test_factor_fit_v4.py`.
Tests compare GPU tangent derivatives to dense and finite-difference forms,
QR loss/gradients to a dense objective, column gauge Gram preservation, exact
integer deltas and stale-state rejection, real CUDA continuous descent, and
progressive freezing/word decoding with deliberate CPU refusal. The tiny QAT
fixture checks both eager and real compiled CUDA execution; the actual training
driver uses the published compiled path.

Acceptance is error1/error2 <=20 mHa (aim <=19.5), Lambda>49.0 and
E_gap>3.914898. Hand passing factor hashes to PRA-248 immediately. Full circuit
verification and Kaggle submission stay on the downstream tasks. Until both
runs and all requested reporting are complete, the PR remains a draft.

## Long-run process lifetime

Run01 stopped at the heartbeat boundary during GN. Its71 measured points are
retained as an interrupted run, not a completed negative. Run02 exited1 before
fitting: the CUDA runtime initialized its cache under the output directory before
the fitter could reserve that directory. The exclusive-output check correctly
refused it. No checkpoint was overwritten.

Run03 restarts every stage from the declared input. The exact argv, cwd, process
group, log and exit-record paths are in
`ledger/evidence/pra246/declared-v4-03.launch.json`; the adjacent
`declared-v4-03.runner.py` is the one-shot supervisor used. It runs in a new
process session with closed stdin and an exclusive log. It has survived its
launcher exit and emitted CUDA stage10 checkpoints. The next issue monitor must
verify survival across the heartbeat boundary; a monitor alone is not proof.
Do not start another fit while that process is alive.

The launch explicitly puts TORCHINDUCTOR_CACHE_DIR, TRITON_CACHE_DIR,
TORCH_EXTENSIONS_DIR and CUDA_CACHE_PATH beneath the adjacent
`/home/cld-main/work/vqcc-data/pra246-declared-v4-03.cache` directory. The supervisor
writes its log and exit JSON beside the output directory. Without explicit cache
settings, the CUDA compiler can use default user cache paths. A zero exit is
accepted only with a complete report and reloaded passing factor; an absent exit
record or report is not success. No daemon or production service is installed.

## Resume completed continuous stages after a runtime failure

Run03 completed its L-BFGS and GN source budgets, then compilation failed because
its inherited TMPDIR belonged to an expired heartbeat. This is a runtime failure,
not a chemistry negative. The complete continuous result is16.868331753377305mHa.
The supervisor now sets TMPDIR, TMP and TEMP to a persistent explicit adjacent
`.tmp` directory, in addition to the named compiler caches.

`--resume-continuous` names a JSON manifest with explicit progress/factor paths
and hashes; `--resume-sha256` pins that manifest. Only completed stages from the
original v4 driver with unchanged numerical modules and matching input/seed are
accepted. An inflight optimizer is rejected. The raw checkpoint must reproduce
the recorded continuous result within1e-12Ha. The original output is read only;
the new output must not exist. The restart retains the completed stage records,
prior elapsed seconds and exact source/checkpoint hashes. It resets seed95101 and
runs every 11-bit and8-bit QAT/postprocessing step; no optimizer state or reduced
iteration budget is substituted. Total elapsed work includes the recorded
`resume.prior_seconds` plus the new run's seconds. The helper is read-only and
invoked only by this CLI; removing it disables this optional resume path.

Use the declared-input command above with a fresh output directory and:

```sh
--resume-continuous ledger/evidence/pra246/continuous-resume-run03.json \
--resume-sha256 362d82da2f1f03fdcf1968378ae0699574dc653bfe8f35bfdcc15f4f7063d440 \
--dry-run
```

The real dry-run reports `recomputed_error:0.016868331753377305`, manifest hash,
checkpoint hash and completed stage budgets. Replacing the digest with `wrong`
exits1: `resume manifest hash mismatch; use the recorded SHA-256`, without creating
an output. Remove `--dry-run` to start QAT. Tests reject changed manifest, report,
checkpoint, source, input and unfinished-stage evidence; they also reproduce a
valid checkpoint's continuous residual. Both eager and compiled CUDA QAT fixtures
pass. Run these checks with a persistent TMPDIR and explicit compiler cache paths.

Recovery validation: `uv run --group gpu pytest -q` with the persistent
TMPDIR/compiler-cache paths: **330 passed, 1 skipped in100.33s**. The declared
run04 launch record and exact supervisor are in `ledger/evidence/pra246/`.
