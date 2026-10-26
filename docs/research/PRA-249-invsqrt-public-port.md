# PRA-249: public-source invsqrt port

## Result: no-go at the 15× floor

The regenerated Gluzdov v7 source route passes the official full verifier but
reaches **13.237727706×**, below the task's **15×** floor. This measured
negative applies to the port and bounded searches below. It is not an upper
bound on Gluzdov's method, the seven busyaprime prose techniques, or a different
schedule. The busyaprime binary was not approved and was not used.

The shipping fallback, ledger generator configuration and submission queue are
unchanged. No candidate zip or G0–G5 bundle receipt is claimed. Building a bundle
below the acceptance floor would not satisfy this task. John Wick owns any next
optimization scope and the subsequent notebook selection on PRA-240.

## Source and implementation

- Repository `clduab11/quantum-hackathon`; branch `op-vqcc/PRA-249-invsqrt-public-port`,
  cut from main `9db5f61785d41636cff13a9116d26aa13c57aeb1`; draft PR #46.
- Gluzdov v7, scriptVersionId `361726742`, declares Apache-2.0 in cell 50.
  Notebook SHA-256 `d689cc89f41a6c9130e9f4c3a6b08dfd5d758fcbbb79f527d55cbd3b48e15280`.
- Source map: [PROVENANCE.md](../../tasks/invsqrt/PROVENANCE.md).
  No saved table, angle file, rewrite patch, packaged circuit or chemistry data
  from that notebook is used.
- CUDA int64/float64 fits the published grouped-curvature recipe; even anchors
  implement the virtual low accumulator bit. Groups above 0.95 relative-error
  units split recursively. Parameters: `(9,19,26,2,drop2=(5,))`, three fractional
  slope bits, maximum group size eight; 50 groups remain after refinement.
- The repository affine compiler independently recomputes rewrites on the
  complete input domain. Angle fitting evaluates all constraints on CUDA and
  solves the small cutting-plane LP with host HiGHS. The bounded angle experiment
  tries all original rotations and one smallest-angle drop.
- **Read before you write / Match the repo:** reuse existing circuit arithmetic,
  affine compilation and peephole helpers. No existing coefficient fitter runs.
- **Test the failure first:** missing-module collection failed before the new
  implementation. A scratch mutation removing the rounding bit failed the
  independent scalar oracle with `AssertionError: (180545, 180547)`.
- **Smallest diff that solves it:** isolated experiment; no fallback or default
  gate-configuration changes and no repair to other open PRs.

## Full verifier

```json
{
  "status": "PASS",
  "score": 156882.98474606057,
  "toffoli_equivalent": 1867.654580310245,
  "toffoli_count": 1553.0002254402652,
  "max_toffoli_count": 1564,
  "t_count": 1.0,
  "rotation_count": 44.0,
  "rotation_eps": 3.051847661949807e-13,
  "num_qubits": 84,
  "reaction_depth": 214,
  "num_ops": 37753,
  "verified_shots": 200540928,
  "worst_error_over_tolerance": 0.9995943415273103,
  "worst_x": 32,
  "circuit_sha256": "17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad",
  "seconds": 433.41393342998344,
  "salt": "PRA171_LOCAL_PUBLIC_FIXED_SALT_0001",
  "ratio": 13.237727705632725
}
```

The fixed public salt is `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`. The unmodified
competition verifier used `ProblemSpecInvSqrt.for_n_p(10)` and `max_workers=2`.
No seed/salt search, cached receipt or Kaggle operation was used. PASS certifies
the full run; this verifier does not emit separate failure counters on PASS.

The local circuit is 255,914 bytes at SHA-256
`17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad`.
It is an experimental artifact, not an approved submission.

## Arithmetic, compilation and determinism

- All **3,133,452** integer inputs checked before circuit construction: worst
  error/tolerance **0.9499016330834485**, at **763987**; minimum margin
  **31,510,146** units of 2^-64 turns. No first bad input.
- Compiled unconditional phase equals that integer model on all 3,133,452 inputs.
  Measurement/feed-forward correctness is covered by the separate full verifier.
- Raw: Q84, 1,577 static Toffoli, 44 rotations. Compiled: Q84, 1,564 static,
  1,553 expected Toffoli, 1 T-like gate, 44 rotations.
- Fresh angle fit: minimum exact margin **78,847,037** phase units; expected-cost
  estimate **156,882.9658090783**, ratio **13.237729303528413×**. Official sampled
  measurement branches give the small cost difference shown above.
- Two independent GPU fits produced identical tables, encodings, refinement
  groups and arithmetic certificate. Canonical JSON (`sort_keys=True`) SHA-256:
  `5b6e9f70e5724f899ba7049562863f903a213cfe185c4d31962786c82a99733d`.
- The final CLI rebuilt from the mathematical target without reading the first
  fit. Byte-identical full-circuit rebuilding and G5 were not run: this candidate
  fails the floor before bundle acceptance. Do not treat table determinism as G5.

## Negative experiments

1. Unrefined groups of eight fail the exhaustive mirror: worst error/tolerance
   **1.0837493283301227**, at **870557**, first failure **202149**, minimum margin
   **−98,692,137**. No kickmix circuit was built for that failing fit.
2. The smallest rotation drop (index 18) fails exact positive-margin checking:
   **−36,750,310** units. An exploratory next drop (19) also failed at
   **−183,254,333**. The broader drop search was interrupted; it produced no
   selected circuit. The final bounded generator tests only original/no-drop
   and the smallest drop, retaining the former.
3. Narrower curvature updates increased lookup cost. Raw screening after G2:

| Update width | Q | Static Toffoli | Expected Toffoli | Rotations |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 84 | 1761 | 1750 | 44 |
| 2 | 84 | 1719 | 1708 | 44 |
| 3 | 84 | 1665 | 1654 | 44 |
| 4 | 84 | 1613 | 1602 | 44 |
| 5 | 84 | 1591 | 1580 | 44 |
| 6 | 84 | 1581 | 1570 | 44 |
| 7 | 84 | 1579 | 1568 | 44 |
| 8 | 84 | 1577 | 1566 | 44 |

These widths are raw resource screens, not eight verified circuit variants.
The full verifier ran only on the final width-eight circuit.

## Commands and actual output

```text
uv sync --group gpu
Resolved 96 packages; CUDA torch 2.8.0+cu128 installed.
CUDA available: True; NVIDIA GeForce RTX 4060 Ti

UV_NO_SYNC=1 uv run pytest tests/test_invsqrt_public_port.py -q
5 passed in 6.39s

UV_NO_SYNC=1 uv run python -m tasks.invsqrt.public_port.generate --out /tmp/pra249-implementation-6AvJmF/final
integer_mirror: passed=true; tested_inputs=3133452
compiled: phase_match=true; inputs=3133452
sha256: 17fc223d79d3f1f15ef448389072209972b373403dd0a45352f4fe7eaff541ad
(exit 0)

uv sync
Resolved 96 packages in 3ms
Uninstalled 22 packages in 1.42s
(exit 0; removes optional GPU group after fitting)

uv run pytest
355 passed, 8 skipped in 193.55s (0:03:13)
(exit 0)

uv run pytest tests/test_invsqrt_public_port.py -q
4 passed, 1 skipped in 0.11s
(exit 0; CUDA-only comparison skipped without optional torch group)
```

The first scratch-mutation invocation used the resolved base Python and failed
because NumPy was absent; that was a setup failure, not test evidence. Repeating
with the worktree venv produced the intended assertion failure quoted above.

## Full-verifier command

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 UV_NO_SYNC=1 uv run python - <<'PYVERIFY'
import json, time, pathlib
from harness.runtime import load_metric, LOCAL_SALT
load_metric()
import kickmix as km
from invsqrt import verify_submission_invsqrt as inv
root = pathlib.Path('/tmp/pra249-implementation-6AvJmF')
c = km.Circuit.from_file(str(root / 'final/invsqrt.kmb'))
start = time.monotonic()
r = inv.verify(c, inv.ProblemSpecInvSqrt.for_n_p(10), salt=LOCAL_SALT, max_workers=2)
r.update(seconds=time.monotonic()-start, salt=LOCAL_SALT,
         ratio=2076774.233715282/r['score'] if r.get('score') else None)
(root / 'full-verifier.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps(r), flush=True)
PYVERIFY
```

The raw JSON output is reproduced in the full-verifier section above.

## Merge and review boundary

The whole queue gate includes every open PR returned by the governed GitHub
connection: #43, #44, #45 and this branch. It is **red** because #43 conflicts
with current main in `notices/30-dfthcsos.txt`, `pyproject.toml`, and `uv.lock`.
There were 24 permutations, zero clean; no conflict path belongs to this change.
PRA-251's owner must refresh that PR before the queue gate can pass. This branch
remains draft and is not reported ready for board merge. Caine neither merges
nor signs off on the change entering main.

Rollback before merge: leave the draft unmerged. A later board-selected code
rollback must preserve `D-PRA249-01` and `D-PRA249-02`; this experiment does not
change a runtime service, existing generator selection or live machine.
