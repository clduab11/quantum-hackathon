# PRA-280 chemistry catch-up

The source-built public route reproduces rustad's ungauged chemistry cost:
436,969,552.2049674, T=21,922, Q=415, lambda_eff=48.0311413197687.
The exact zip passes **G0–G5**, all real PASS, with full shots and the fixed
public salt. `shipping_problems()` is `[]`. The 7.679x floor is met; the
9.23–9.34x decisive target is not reached.

## Input and method

Rustad dataset `michaelrustad/vqcc-dfthc-r10-merged-groups`, version 1,
`fact/dfthc_r10_b129_c60_brot8.npz`, 3,062,892 bytes, SHA-256
`27dda66f38c60821665cfc74e51d1bd2bfd2a7f0d902dbaffcdc5b26543dadad`.
Its shape is R=10, B=129, C=60, N=76, 8-bit words, 1,366 addresses.
The public file hash equals the README's hash. It is a declared non-circuit
input under D-PRA211-05 and is copied byte-for-byte; all circuits are generated.

The compiler ports mrmeows's v6 `rank_parity.py`, `hyper_native.py`, and exact
integer gauge from `compile_four_address.py`. Each circuit uses the deterministic
per-output matrix factorization: 89 cached nonlinear monomials plus 168 paired
products, 257 Toffolis per call. There are 25 three-word circuits at 124 qubits.
No synthesis seeds, private gauge, external certificate or circuit are inputs.
The integer gauge changes vectors only by an overall sign, preserving their
outer products; it changes neither factor coefficients nor physical precision.

| Public source | Version | Licence field as found | Use |
| --- | --- | --- | --- |
| [Rustad factor](https://www.kaggle.com/datasets/michaelrustad/vqcc-dfthc-r10-merged-groups?datasetVersionNumber=1) | 1, dataset 12856598 | Other (specified in description) | Pinned non-circuit NPZ |
| [mrmeows compiler](https://www.kaggle.com/datasets/mrmeows/qcc-1375-open-circuits?datasetVersionNumber=6) | 6, dataset 12858555 | Apache 2.0 | Source port |
| [alexchilton combination](https://www.kaggle.com/code/alexchilton/toffolis-go-18-3-schur-dqi-at-883-qubits) | v37/run 362577442 | None stated for notebook code; credits label portfolio circuits Apache-2.0 | Method reference only |

Full file SHA-256 values, URLs and UTC observation are in
`ledger/manifests/inputs/pra280-rustad.json`. Licence observations are recorded
for the end-of-hackathon pass, not used as a gate (PRA-273).

## Measured chemistry breakdown

| Quantity | Direct official verifier |
| --- | ---: |
| error_1 (Ha) | 0.01899591608958213 |
| error_2 (Ha) | 0.01965431396009024 |
| Lambda | 294.4750983101894 |
| E_SOS (Ha) | -22144.216878617124 |
| E_gap (Ha) | 3.9435286171246844 |
| lambda_eff | 48.0311413197687 |
| ANGLE Toffolis, both passes | 12850 |
| Outer preparation Toffolis | 399 |
| Inner preparation Toffolis | 6423 |
| Givens Toffolis | 2250 |
| Total T | 21922 |
| Persistent qubits | 111 = 87 heuristic + 24 word |
| Temporary qubits | 304 = max(175 outer, 304 inner, 89 ANGLE) |
| Total Q | 415 |
| ANGLE circuit Q | 124 = 11 selection + 24 word + 89 cache |
| Full shots | 87424 = 1366 x 64 |
| Cost | 436969552.2049674 |
| Reference/candidate cost ratio | 7.679252642164734 |

PRA-282 inferred the ungauged cost from the public notebook; its measured zip
used the private LLM gauge. This work directly verifies the published ungauged
factor with our own generated circuits. The 7.679x floor is numerically met.
The 9.23–9.34x decisive target is not reached. No factor optimization or GPU
training was needed for this catch-up.

## Reproduction

See `tasks/dfthcsos/RUSTAD.md` for input staging, dry run, output guards and the
construction. Actual commands:

```sh
uv sync
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
OPENBLAS_NUM_THREADS=1 uv run python -m tasks.dfthcsos.rustad \
  --data /home/cld-main/work/vqcc-data --out /home/cld-main/work/vqcc-data/pra280/bundle
OPENBLAS_NUM_THREADS=1 uv run python -m dfthcsos.verify \
  /home/cld-main/work/vqcc-data/pra280/bundle/dfthcsos
```

The direct component check is distinct from the fixed-public-salt exact-zip
pipeline. Companion tasks use the existing committed Schur DQI and invsqrt
builders. No Kaggle upload, reservation, main write, merge or live-service action.

## Compiler and repository checks

```text
uv sync
Resolved 105 packages; Installed 36 packages
uv run pytest -q tests/test_rustad_compiler.py  # before implementation
ERROR: ModuleNotFoundError: tasks.dfthcsos.paired_qrom
OPENBLAS_NUM_THREADS=1 uv run pytest -q tests/test_rustad_compiler.py
15 passed in 3.88s
OPENBLAS_NUM_THREADS=1 uv run pytest -q
391 passed, 11 skipped in 285.02s (0:04:45)
```

Optional GPU/JAX/notebook checks are outside this environment; all compiler
tests ran. The full suite was followed by compiler/manifest/register checks
after the candidate recipe's provenance-category correction: **45 passed in
1.40s**. The real-input dry run reports 25 circuits and creates no output
directory. Raw logs live in
`ledger/evidence/pra280-rustad/`. No existing circuit algorithm was changed by
that metadata correction.

The input-pin tests reject altered bytes before any output exists. The floor
check rejects 7.6789, NaN and missing measurements, and accepts 7.679. The oracle
tests cover dirty targets, phase cleanup, inverse use and partial address banks.
The real factor gauge changes 50,949 word entries and negates 577 vectors;
maximum signed-vector residual is 7.216449660063518e-16.

The first candidate registration failed because raw licence labels are not
valid enum values. The recipe now uses `no-licence` for unspecified terms and
keeps the exact source wording in notes and the input manifest. It does not
change or weaken the ledger schema or provenance gate. The original unused zip
and failure log remain out of tree for traceability.

Published generator: `bcc37c2e4d838907ea1274b3c96628ed69ffedc2`. Its source tree
`b4355fbcf68d75def96ad94e8d52b4497803188e` equals local `d08a909`. Publication used
the governed GitHub connection because the shell credential helper was
unavailable. The execution branch was not switched or repointed.

## Exact-zip full verification

Fixed salt: `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`; shot_divisor=1; no waivers.

| Task | Full shots | Cost | Ratio |
| --- | ---: | ---: | ---: |
| invsqrt | 200540928 | 157751.94999626835 | 13.16480863637127 |
| dqi | 102400 | 513507847124.5177 | 47.59316876861791 |
| dfthcsos | 87424 | 436969552.2049674 | 7.679252642164734 |

The measured portfolio geometric mean is **16.88208344372253**. It beats the
archived 11.283239253337468 parent under G4, but remains below the 17.306
portfolio cutoff. This ticket closes the chemistry gap; it does not supply the
public 19.13x invsqrt or claim a winning portfolio.

G3's chemistry metrics equal the component-check table above. Exact zip
SHA-256: `8e2918400fd033440d350d4af76bc4bdfca3787cdf411dcbb974f03d3b4f8f21`.
G3 evidence SHA-256: `c4a88f2ee7093fd78dbdda2f759781131ba32c26de6add03225ff3d78646d5a5`.
Candidate manifest: `ledger/manifests/candidates/pra280-rustad.json`.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. uv run python -u \
  ledger/evidence/pra280-rustad/run_candidate.py \
  --generator-commit bcc37c2e4d838907ea1274b3c96628ed69ffedc2
```

The recipe resumes uncleared gates on the same zip/manifest. Do not create a
second candidate or rerun cleared gates after an interruption.

## G5 and final hand-off

```text
G0 PASS
G1 PASS
G2 PASS
G3 PASS
G4 PASS
G5 PASS
shipping_problems: []
pipeline_seconds: 634.4217076950008
```

All three tasks returned code 0, `identical=true`, with no missing, extra or
changed files. Only `dfthcsos/submission.npz` is recorded as copied from the
declared input. Every `.kmb` was regenerated. G5 also checked deterministic
zip bytes. Exact candidate: 54,771,505 bytes at
`/home/cld-main/work/vqcc-data/pra280/pra280-rustad.zip`; the queue receipt is
`ledger/queue/pra280-rustad.json`.

Review PR: [#58](https://github.com/clduab11/quantum-hackathon/pull/58), branch
`op-vqcc/PRA-280-chem-catchup`, repository `/home/cld-main/work/quantum-hackathon`.
The PR body carries the fresh whole-queue merge-order report. Source and test
changes are confined to new compiler modules, tests, a candidate config,
source pins and notices; remaining changes are docs and ledger evidence.
The generator writes only its output directory; the recipe writes its named
zip, manifest, gate evidence and queue entry. Builds use WSL and the existing
organizer Python dependencies. No source downloads occur during generation.

The Adjudicator must review the exact source/input provenance and candidate
before merge or submission. The board owns merge; John Wick owns any later
upload. Board rollback command: `git revert <PRA-280-squash-merge-commit>`, then
select the prior candidate config. No production configuration is changed.
