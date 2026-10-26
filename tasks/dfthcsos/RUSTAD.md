# Rustad chemistry catch-up (PRA-280)

`tasks.dfthcsos.rustad` generates 25 exact three-word ANGLE circuits from the
published rustad v1 (10,129,60), 8-bit factor. It copies the declared non-circuit
NPZ unchanged. No circuit, decomposition certificate or private gauge is an input.
Source versions, URLs, hashes and licence observations are recorded in
`ledger/manifests/inputs/pra280-rustad.json` and `notices/35-chem-catchup.txt`.

## Prerequisites and use

Run `uv sync`, then install the organizer Kickmix/verifier paths with the existing
`uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation`.
Place the published `fact/dfthc_r10_b129_c60_brot8.npz` under
`/home/cld-main/work/vqcc-data/inputs/rustad/`. The input manifest pins its hash.
Download a nested Kaggle file using its percent-encoded filename (`fact%2F…`),
with `datasetVersionNumber=1`; no Kaggle credentials are needed for this file.

```sh
uv run python -m tasks.dfthcsos.rustad --help
uv run python -m tasks.dfthcsos.rustad --data /home/cld-main/work/vqcc-data \
  --out /tmp/pra280-build --dry-run
uv run python -m tasks.dfthcsos.rustad --data /home/cld-main/work/vqcc-data \
  --out /tmp/pra280-build
OPENBLAS_NUM_THREADS=1 uv run pytest -q tests/test_rustad_compiler.py
```

Dry run validates the hash and builds circuits in memory without writing files.
A normal build writes only `OUT/dfthcsos/submission.npz` and `angle_k_0..24.kmb`.
It prints file hashes and circuit resource counts as JSON. A hash mismatch,
invalid table/tree, oversized layout or nonempty output directory raises an
error and exits nonzero. Use a fresh output directory; there is no overwrite
flag. `--data` is explicit; G5 supplies its isolated root through `VQCC_DATA`.
No download, GPU work or submission occurs in the generator.

## Exact construction

The integer projective gauge replaces each tree-encoded vector by itself or its
negative. It uses only negation and half-turn addition modulo 256; there is no
refit or rounding. This preserves each vector's outer product and makes the two
highest angle bits equal. The embedded raw words remain in the unchanged NPZ;
the verifier recovers the gauged words from the generated circuits.

Split 11 selection bits into four low bits and seven high bits. There are 86
legal high-address monomials and 16 low-address monomials. Cache the 89 nonlinear
monomials with ANDs. Factor each of the 21 independent output-bit matrices over
GF(2). Pair two mixed products using
`(h1+l2)(h2+l1) + h1*h2 + l1*l2 = h1*l1 + h2*l2`.
The high-only and low-only corrections use the cache and Clifford gates.
Each circuit uses 168 paired products plus 89 cache ANDs: 257 Toffolis, 124
qubits. HMR erases the cache in reverse dependency order with its exact phase
correction. The XOR oracle holds for arbitrary incoming word registers.

This is the deterministic factorization path from mrmeows's public compiler.
It does not use his output-basis/kernel search or saved decomposition plans.
The source port is split into algebra, emission and projective gauge modules;
the older ANF compiler remains usable for its existing candidates.

## Verification and hand-off

Use `configs/gates/pra280-rustad.yaml` for the exact three-task candidate. It
pairs this chemistry with our committed Schur DQI and current invsqrt builders.
All G0–G5 gates are non-waivable. G3 requires 87,424 chemistry shots at the fixed
public salt. G4 requires chemistry >=7.679x and strict portfolio improvement.
G5 stages only the declared NPZ and rebuilds all circuit bytes from the generator
commit. The input pin has a negative test; dirty-target, phase, inverse, partial
address-bank, gauge and rebuild tests cover the compiler.

Tooling lenses: **No hidden state** (one pinned runtime input), **Fail loudly,
fail early** (input/output checks), and **The check must be able to fail** (bad
input and below-floor cases). The full result belongs in
`docs/reports/pra280-chemistry.md` and the ticket's `chem-catchup-log`.

Only the board merges. The Adjudicator must sign off before merge or submission;
John Wick owns any later upload. Rollback is a board-applied revert of this PR,
then selection of the prior candidate config. This PR does not change defaults
or execute tools against a live service.
