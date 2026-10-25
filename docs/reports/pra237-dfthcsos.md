# PRA-237: refit-factor ANGLE integration, measured negative

The best point in this bounded 12-bit sweep passed the complete dfthcsos verifier
but reached **1.0966038528404063×**, below the 2.8× floor and 5× target.
High-penalty factors with direct J=9 ANGLE circuits measured T=80,746, Q=739,
and cost 3,059,992,521.1131754 against the reference cost
3,355,599,588.3155365. This is a measured negative result, not a submission
candidate. The complete verifier output and per-file receipts are in
`ledger/experiments/pra237/verify.json` and `results.json`.

## Inputs and selection

The ANGLE generator is the merged PRA-232 `tasks/dfthcsos/circuit.py` on
`origin/main` at `73d6e49ea7289dd7a55c7001cfd37de7658a0d8f`. It accepts a
declared factor archive through `--factorization` and copies that non-circuit
input byte-for-byte at unchanged precision. No PRA-235 code is bundled into
this branch. PRA-235 [PR #29](https://github.com/clduab11/quantum-hackathon/pull/29)
records the factor-generation source and evidence. The relevant Google baseline
and method-parent licences are recorded in `notices/30-dfthcsos.txt`:
the starter-kit code/input and the kozykappa, anazemcev, magmacot and
ahmedberatozer method notebooks are Apache-2.0. The factor fit uses Google's
pinned baseline and own NumPy/SciPy code. No public competitor factor or
competition-package circuit was loaded.

| Factor point | Shape, width | Encoded SHA-256 | Reported error₂ | λ_eff | Selection role |
| --- | --- | --- | ---: | ---: | --- |
| High penalty | (65,60,30), 12 bits | `44e55a6b70d3da5618e9006b27350cd197e16f18aa256024c90cb19c3bfae4f1` | 18.299842110 mHa | 51.280813872 | Best accepted factor-model cost |
| Adam | (65,60,30), 12 bits | `ec864ac608d42a5e0a3c816aff353ccf8383e6472e3a4ddf88f35f45ce24c371` | 17.459501285 mHa | 51.960839599 | Best factor error margin |

Both local files matched their PRA-235 handoff hashes during intake. Aurelio
reports independent archive reloads and same-environment byte repeats for
both. This integration independently checked the high-penalty factor through
the full circuit verifier; the Adam point received a circuit-aware G2 proxy.
PRA-235's final matrix reports that all later R60–R32 cuts and lower-width
encodings fail accuracy. Its final R32 10-bit error₂ is 243.531672 mHa, so
there is no passing 8-bit input for the inner-preparation temporary-qubit
reduction. Those failed-factor results are PRA-235 evidence, not circuit runs
on this branch.

## Resource model and measured result

For (R,B,C,b_rot)=(65,60,30,12), the unchanged verifier
`scoreinfra/costs_prepare.py` gives 627 outer, 5,317 inner and 3,450 Givens
Toffolis: 9,394 heuristic Toffolis. It gives 88 persistent and 543 maximum
temporary qubits. The ANGLE address register has 12 qubits. With J=9 and
eight traversal qubits, the direct ANGLE circuit uses exactly
12 + 9×12 + 8 = 128 qubits. The score charges
Q = 88 + J×12 + max(543, ANGLE temporary) = 739. Increasing direct J to 10
exceeds the circuit cap. Banking permits smaller J and Q, but the extra
circuits raise total T.

The table lists G2 circuit-aware static counts and the official heuristic
costs. The selected row also ran the full official verifier; its measured
T, Q and cost exactly equal the G2 values. Rejected layouts are recorded
negative results, not valid scores.

| Factor / ANGLE layout | J | ANGLE Q | T | Total Q | Ratio to reference | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| High, direct, scratch 8 | 9 | 128 | 80,746 | 739 | **1.096604×** | G2 PASS; full verifier PASS |
| High, direct, scratch 6 | 9 | 126 | 81,232 | 739 | 1.090043× | G2 PASS |
| High, two-address bank | 4 | 114 | 89,602 | 679 | 1.075543× | G2 PASS |
| High, two-address bank | 5 | >128 | — | — | — | Cap rejection |
| High, four-address bank, scratch 5 | 2 | 113 | 93,686 | 655 | 1.066349× | G2 PASS |
| High, four-address bank, scratch 6 | 2 | 114 | 93,306 | 655 | 1.070691× | G2 PASS |
| High, four-address bank | 3 | >128 | — | — | — | Cap rejection |
| Adam, direct, scratch 8 | 9 | 128 | 80,746 | 739 | 1.082252× | G2 PASS |

The full verifier used the fixed public salt
`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`, 64 shots per address and 254,464
verified shots. It returned PASS in 39.478 seconds. The physical metrics are
error₁=3.224421669 mHa, error₂=18.299842110 mHa,
Λ=325.285029352, E_gap=4.067613184750 Ha and
λ_eff=51.28081387196288. The measured stage costs are:

| Stage | Toffolis | Persistent Q | Temporary Q |
| --- | ---: | ---: | ---: |
| ANGLE, forward and reverse | 71,352 | 108 | 8 |
| Outer preparation | 627 | 44 | 185 |
| Inner preparation | 5,317 | 44 | 543 |
| Givens | 3,450 | shared | shared |
| Total | **80,746** | **196** | **543** |

The selected cost is
51.28081387196288 × 80,746 × (196 + 543) = 3,059,992,521.1131754.
The fixed 2.8× floor would require cost at most 1,198,428,424.398406;
the measured point is far above it. The full verifier's JSON, including the
submission digest, resource and physical breakdown, is preserved verbatim in
`ledger/experiments/pra237/verify.json`.

## Reproduction and boundaries

From a WSL checkout of the generator commit with `uv sync` and the
SHA-pinned supplied kickmix installed through `scripts/install_kickmix.py`:

```sh
uv run python -m tasks.dfthcsos.circuit \
  --out /home/cld-main/work/vqcc-data/pra237-dfthcsos/experiments/high-direct12-j9 \
  --factorization /home/cld-main/work/vqcc-data/pra235-handoff-penalty-high-01/submission.npz \
  --source-brot 12 --b-rot 12 --batch-size 9 --bank-bits 0 \
  --scratch 8 --pebble-degree 4
```

`tasks.dfthcsos.gates:g2_proxy` returned PASS on that output. Calling
`dfthcsos.verify:verify` on its `dfthcsos/` directory with the fixed salt
returned the full PASS above. A fresh same-environment build from the same
declared factor matched all 10 output files byte-for-byte. None of its nine
ANGLE hashes matched a competition-package reference circuit hash.

The binaries remain under `/home/cld-main/work/vqcc-data/pra237-dfthcsos/`.
Every selected file's SHA-256 and size is in `results.json`; no `.kmb`, NPZ or
zip is committed. These measurements cover the named PRA-232 12-bit layouts
on the handed-off factors. They do not prove that every possible circuit
method is inferior. No three-task zip, ledger candidate, G0–G5 shipping
claim, durable queue entry or Kaggle upload was created because the measured
floor failed. This follows the measured-negative route used for PRA-232
(D-PRA232-10).

Repository verification on the PRA-237 branch:

```text
uv sync
Resolved 50 packages; Installed 12 packages
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
kickmix 0.1 .../kickmix/kickmix.so
uv run python -m ledger.registers check
OK registers: 173 decisions, 5 notice files, legacy index unchanged
uv run pytest
266 passed, 1 skipped in 56.22s
```

The skipped module is the repository's optional notebook dependency group.
The verifier and circuit tests ran. The merge-order gate and PR status are
recorded separately when the branch is handed to the board.
