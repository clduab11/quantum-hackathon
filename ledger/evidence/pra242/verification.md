# PRA-242 verification evidence

Runtime: Python 3.13.13, NumPy 2.5.4, SciPy 1.18.1, WSL CPU. No GPU used.

```text
$ uv sync
Resolved 50 packages in 1ms
Installed 12 packages in 67ms
exit=0

$ OPENBLAS_NUM_THREADS=1 uv run pytest tests/test_factor_fit_v3.py -q
6 passed in 0.26s
exit=0

$ uv run python ledger/evidence/pra242/check_acceptance.py
PASS: 19.6 mHa error1 rejected at the 19.5 mHa floor
exit=0

$ uv run python ledger/evidence/pra242/check_acceptance.py --negative
FAIL: missing error1 margin gate accepts 19.6 mHa; restore both-error check
exit=1 (expected: deliberate in-memory mutation)

$ uv run python ledger/evidence/pra242/check_source_parity.py /tmp/pra242-provenance
{"status": "PASS", "max_covariance_difference": 0.0}
exit=0

$ uv run python -m tasks.dfthcsos.factor_fit_v3 --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --out /home/cld-main/work/vqcc-data/pra242-r6-v3 --dry-run
shape=[6,144,127], steps=500, gn_steps=30, pinned_files=26
exit=0; no output directory created

$ uv run python -m tasks.dfthcsos.factor_fit_v3 --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --out /home/cld-main/work/vqcc-data/pra242-invalid --steps 0 --dry-run
factor fit v3: iteration limits must be positive; sweeps nonnegative
exit=1 (expected)

$ uv run pytest
3 failed, 278 passed, 1 skipped in 132.68s
exit=1

$ uv run python -c 'import tasks.invsqrt.reference_gates'
ModuleNotFoundError: No module named 'kickmix'
exit=1

$ PYTHONPATH=/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix uv run pytest
281 passed, 1 skipped in 120.71s
exit=0

$ uv run python -m ledger.registers check
OK registers: 206 decisions, 5 notice files, legacy index unchanged
exit=0 (before numerical-result decision rows)
```

The full suite requires the competition kickmix directory in subprocess import
paths, as already documented in `tasks/dfthcsos/REFIT_V2.md`. No dependency,
hook, test, or gate was bypassed or edited for the successful rerun. The one
skip is the existing optional notebook suite (nbformat is not installed). Final register
count and queue-wide merge report accompany the measured-result commit/PR.

The merge math fixture reproduces the upstream synthetic covariance exactly.
GN tests independently check JVP finite differences, VJP adjointness and the
dense normal-operator quadratic form. Existing structural-gradient tests also
pass. These checks establish implementation correctness on fixtures, not
chemistry accuracy or circuit validity. Actual chemistry measurements are in
the per-shape reports; there is no full-circuit verification claim.

## Completed numerical and serialization checks

```text
$ uv run python -m tasks.dfthcsos.factor_fit_v3 --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --out /home/cld-main/work/vqcc-data/pra242-r6-v3 --shape r6
floor_met=false; continuous_error=0.08679648361729835
quantisation_training=SKIPPED_CONTINUOUS_ABOVE_30mHa
exit=3 (complete measured negative)

$ uv run python -m tasks.dfthcsos.factor_fit_v3 --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --out /home/cld-main/work/vqcc-data/pra242-thc-v3 --shape thc
floor_met=false; continuous_error=0.03516004413625665
quantisation_training=SKIPPED_CONTINUOUS_ABOVE_30mHa
exit=3 (complete measured negative)

$ uv run python ledger/evidence/pra242/recheck_words.py --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --data-root /home/cld-main/work/vqcc-data
status=PASS; six files; max_metric_difference=0.0 for each
exit=0

$ uv run python ledger/evidence/pra242/recheck_words.py --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --data-root <fresh scratch root containing corrupt first file>
ValueError: Factor hash mismatch: rounded-diagnostic-b10.npz; restore recorded own-generated file
exit=1 (expected; refuses before np.load)

$ uv run python -m ledger.registers check
OK registers: 214 decisions, 5 notice files, legacy index unchanged
exit=0
```

The serialized audit's complete output is `serialized-recheck.json`.
`checkpoints.json` records all 130 saved NPZ hashes. No factor archive is
committed. The accompanying attachment contains the final factors and the
target-width diagnostics (R6 10-bit, THC 11-bit), all explicitly failing.
