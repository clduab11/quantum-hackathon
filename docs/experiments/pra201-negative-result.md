# PRA-201: no accurate own-refit point for circuit generation

The 2.8x floor is unmet. The PRA-198 handoff contains no accurate compressed
factor point and no passing 7–10-bit point. We stop before ANGLE generation
under **Fail loudly, fail early**. This completes the task's permitted measured
negative result; it is not a shipping candidate or a claim of infeasibility.

The upstream [rank curve](/PRA/issues/PRA-198#document-rank-curve) has 48 rows;
all 32 rows in the requested 7–10-bit sweep fail accuracy. Its only passing row
is the Google control (65,60,60), 12 bits, predicted ratio 1.0000. The first
compression (65,60,30) already misses error2 at 12 bits (20.363453 mHa).
The R=32, B=60, C=30 point gives 655.539761 mHa. The limit is 20 mHa.

## Independent numerical recheck

Fresh encoding and package numerical evaluation of three hash-verified
checkpoints at 7, 8, 9, 10 and 12 bits reproduce all five reported numerical
metrics within 1e-12. The 14 failing rows below are real failures of the
existing `acceptance_problems` check; the 12-bit control exercises its passing
case. This recheck evaluates the saved factors, not a fresh optimization.
All starter-kit and competition source/input pins were checked before import.

Runtime: 60.075 s, single-threaded NumPy 2.5.4. Full metrics, exact tree edges, pinned source/input hashes, checkpoint sizes and per-stage heuristic T/Q are in [numerical-recheck.json](../../ledger/evidence/pra201/numerical-recheck.json).

| R,B,C | bits | error1 Ha | error2 Ha | Lambda | E_gap | lambda_eff | numerical gate |
|---|---:|---:|---:|---:|---:|---:|---|
| 65,60,60 | 7 | 0.117042050456 | 0.302705317033 | 310.819992536 | 6.32953004673 | 62.4069388221 | FAIL |
| 65,60,60 | 8 | 0.0523510538667 | 0.155382552477 | 309.331492229 | 4.84102974027 | 54.5117449548 | FAIL |
| 65,60,60 | 9 | 0.0251597698297 | 0.0766720830694 | 308.712637074 | 4.22217458482 | 50.8827135902 | FAIL |
| 65,60,60 | 10 | 0.0139693989617 | 0.040014621461 | 308.507369167 | 4.01690667773 | 49.6221229233 | FAIL |
| 65,60,60 | 12 | 0.0031851950318 | 0.018639570631 | 308.455939733 | 3.96547724429 | 49.3013692506 | PASS |
| 65,60,30 | 7 | 0.113368720388 | 0.302885744092 | 336.305122736 | 6.39790295448 | 65.2867667641 | FAIL |
| 65,60,30 | 8 | 0.0545525505417 | 0.155587651406 | 334.828870112 | 4.92165032975 | 57.1978897865 | FAIL |
| 65,60,30 | 9 | 0.0273813425741 | 0.0770589188686 | 334.220497462 | 4.3132776804 | 53.5216522515 | FAIL |
| 65,60,30 | 10 | 0.0133550736993 | 0.0408490225637 | 334.017747578 | 4.11052779586 | 52.2406166952 | FAIL |
| 65,60,30 | 12 | 0.00315630602025 | 0.0203634530602 | 333.961323968 | 4.05410418615 | 51.878629919 | FAIL |
| 32,60,30 | 7 | 0.191402231196 | 0.729562235607 | 367.667550979 | 22.6779940885 | 127.128414131 | FAIL |
| 32,60,30 | 8 | 0.0894116136992 | 0.677068568119 | 366.595609967 | 21.6060530765 | 123.994140521 | FAIL |
| 32,60,30 | 9 | 0.044435982412 | 0.660347727654 | 366.021542347 | 21.0319854559 | 122.286446911 | FAIL |
| 32,60,30 | 10 | 0.0219190024994 | 0.656924277247 | 365.870194499 | 20.8806376081 | 121.832692078 | FAIL |
| 32,60,30 | 12 | 0.00526549919137 | 0.655539761202 | 365.851201609 | 20.8616447177 | 121.77564352 | FAIL |

No full circuit cost, measured speedup, G3 simulation, G4 improvement or G5
regeneration is claimed. Heuristic costs exclude ANGLE circuits. The upstream
ordinary-QROM predictions are not a measurement of the proposed banked QROM.
No new submission archive, circuit, candidate manifest or third-party circuit
port was made. The notebook attribution/provenance-map requirement remains
mandatory for any later port; no method code was ported in this evidence PR.

## Evidence lineage and limitations

- Upstream PR: https://github.com/clduab11/quantum-hackathon/pull/24
- Published source/evidence commit: `3eb0cea1713c317aaec7eeaa30e9cd6769a10608`.
- `ledger/evidence/pra198/rank-curve.json` SHA-256:
  `4a7465d3fde85fdeabffc17a5f82fb3cdc6713663762809a0943156f55998edb`.
  Its bytes were compared with that published commit before rechecking.
- The full upstream sweep used 20 structural iterations per cut and up to 100
  offset iterations. Every structural fit reached its iteration cap.
- The original full-sweep report does not record pipeline source hashes.
  The separate final CLI rerun records source hashes and repeats only the
  control and first cut. Do not call that a source-pinned repeat of all stages.
- This check independently verifies numerical metrics from three recorded
  checkpoint hashes. It does not prove the numerical repeatability of the full
  fitting pipeline. Upstream repeatability covers the first refit only.
- Apache-2.0 starter-kit v4 encoder: `starter_kit/starter/task2_angles/encode.py`,
  SHA-256 `cd8eb31056619b2c85ef9e7a1a3743eb2ef621035cda7dd23e6b47208e683745`;
  tree builder: `starter_kit/starter/task2_angles/trees.py`, SHA-256
  `47429502abc75e1a4360a2591f5df6b8ba56f79c0909d90739c38225ce25ea0c`.
  The exact log-depth tree is stored in the JSON. Precision is explicit at
  each encoder/evaluator call; the old main-branch G2 width inference is not used.

## Exact blocker and next research

A factor point that passes both 20 mHa errors at the chosen 7–10-bit precision
with the required norm/gap floors is missing. Aurelio owns the tooling;
The High Table must scope a follow-on factor study, with longer/error-aware
refits and quantization-aware fitting. Optimizer changes and longer searches
were not tested here. Circuit engineering can resume when such a handoff has
numerical determinism evidence and declared source/input hashes. It still
requires G0–G5, the 2.8x measured target, candidate-specific Adjudicator sign-off
and the watchdog re-check before shipping. Chris owns merges.

## Reproduce the numerical check

Prerequisites: this branch's `uv sync`; downloaded pinned starter-kit v4 and
competition package at the paths below; the PRA-198 PR checkout and its
`pra198-curve-02` checkpoints. No credentials or network are used by the
numerical check. The checkpoints remain outside git. This is the exact
one-off validation code, not a new production tool.

First set up imports in this worktree only:

```sh
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
```

Save the Python block below to a new scratch directory as `recheck.py`.
Replace the one output JSON path with a path in that scratch directory, then
run `PYTHONPATH=. uv run python /absolute/scratch/recheck.py` from this repo.
It reads the named inputs and prints all numerical verifier metrics. It writes
only that JSON path; choose a new path to preserve earlier evidence. Any hash,
metric or expected-pass-count mismatch raises an assertion and exits nonzero.
Missing files/imports also fail nonzero. Exit 0 confirms reproduction of the
negative result, not candidate acceptance.

```python
import hashlib, json, os, sys, time
from pathlib import Path
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import numpy as np
from tasks.dfthcsos.checks import acceptance_problems

root = Path('/home/cld-main/work/vqcc-data')
upstream = Path('/home/cld-main/work/.paperclip-worktrees/quantum-hackathon/pra198-dfthcsos-factor-pipeline')
report_path = upstream/'ledger/evidence/pra198/rank-curve.json'
report = json.loads(report_path.read_text())
def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

starter = root/'starter-kit'
competition = root/'google-verifiable-quantum-circuit-compilation'
for key, base in [('files', starter), ('competition_files', competition)]:
    for pin in report['input_pins'][key]:
        assert digest(base/pin['path']) == pin['sha256'], pin['path']
sys.path.insert(0, str(starter/'starter_kit'))
from dfthcsos.verify import load_inputs, evaluate_words, heuristic_costs
from verifier.score import SubmissionInputs
from starter.task2_angles.encode import encode_inputs
from starter.task2_angles.trees import log_depth_tree_edges

started = time.monotonic()
rows, checkpoints = [], []
edges = log_depth_tree_edges(76)
for index in (0, 1, 6):
    stage = report['stages'][index]
    path = root/'pra198-curve-02'/stage['file']
    assert digest(path) == stage['sha256'], path
    checkpoints.append(dict(path=str(path), sha256=digest(path), bytes=path.stat().st_size))
    inputs = load_inputs(path)
    encoder = SubmissionInputs('FeMoCo76o113e', None, inputs.params, inputs.ref,
        inputs.w, inputs.W, inputs.S, inputs.beta_1, inputs.energy_upper)
    for bits in (7, 8, 9, 10, 12):
        tick = time.monotonic()
        words = encode_inputs(encoder, edges, bits)
        metrics = evaluate_words(inputs, words, edges, bits)
        original = next(r for r in report['rows'] if r['shape']==stage['shape'] and r['brot']==bits)
        for key in ('error_1', 'error_2', 'Lambda', 'E_gap', 'lambda_eff'):
            assert abs(metrics[key]-original[key]) < 1e-12, (key, metrics[key], original[key])
        problems = acceptance_problems(metrics)
        row = dict(shape=stage['shape'], brot=bits, **metrics, problems=problems,
            heuristic=heuristic_costs(76, *stage['shape'], bits), seconds=time.monotonic()-tick)
        rows.append(row)
        print(json.dumps(row), flush=True)
assert len(report['rows']) == 48
assert sum(not acceptance_problems(r) for r in report['rows']) == 1
assert not any(not acceptance_problems(r) for r in report['rows'] if 7 <= r['brot'] <= 10)
assert sum(not r['problems'] for r in rows) == 1
result = dict(source_commit='3eb0cea1713c317aaec7eeaa30e9cd6769a10608',
    source_report_sha256=digest(report_path), checkpoints=checkpoints,
    input_pins=report['input_pins'], tree_edges=edges.tolist(), numpy=np.__version__,
    python=sys.version, rows=rows, total_seconds=time.monotonic()-started,
    upstream_rows=48, upstream_b7_to_b10_rows=32, upstream_b7_to_b10_passing=0,
    result='negative: no accurate 7-10 bit handoff; control only at 12 bits',
    limitation='numerical recheck only; no refit rerun, ANGLE simulation, G3, G4 or G5')
Path('/tmp/pra201-validation-UWKuIw/recheck.json').write_text(json.dumps(result, indent=2)+'\n')
print('PASS: 15 numerical rechecks match within 1e-12; 14 reject accuracy; control passes.')
```

Observed final output:

```text
PASS: 15 numerical rechecks match within 1e-12; 14 reject accuracy; control passes.
```

The optional local import setup is reversible with `uv run python scripts/uninstall_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation` (dry-run first). No live-system change occurred.
