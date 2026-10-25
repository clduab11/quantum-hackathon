## PRA-232 circuit-half experiment

The existing `generate.py` remains the reference builder. The sibling
`circuit.py` accepts any declared factor NPZ containing `angle_words`, with
explicit source precision. It leaves factor weights/vectors/tree unchanged;
reducing `--b-rot` only requantizes the angle words. With unchanged precision,
`submission.npz` is copied byte-for-byte. The default source is Google's
SHA-256-pinned package baseline.

```sh
uv run python -m tasks.dfthcsos.circuit --out /path/to/fresh-output \
  --b-rot 12 --batch-size 9 --bank-bits 0 --scratch 8 --pebble-degree 4
# For PRA-201, add --factorization /path/to/declared-factor.npz --source-brot 12.
OPENBLAS_NUM_THREADS=1 uv run python -m tasks.dfthcsos.experiment \
  --out /path/to/fresh-ablation
```

`--bank-bits 0/1/2` selects direct, two-address or four-address ANF lookup.
Nonzero difference columns get bank qubits; the bank is measured and its
phase repaired with an exact ANF polynomial. Prefix pebbling trades repeated
AND operations for fewer live traversal qubits. Every generated circuit must
fit the verifier's 128-qubit cap. Outputs reject a nonempty destination, so
changing batch size cannot silently retain stale ANGLE files.

The fixed experiment compares eleven structural points, calls the existing
G2 hook to choose the lowest-cost passing point, and records full official
verification with 64 shots per address and the fixed public salt. Each JSON
record includes every generated file's hash/size, explicit parameters,
stage costs, physical errors, predicted/measured ratios and run time.
Static costs are estimates until verified; measurement-conditioned Clifford
corrections do not change this builder's Toffoli count. G2 evaluates the
NPZ's word table and cannot establish that circuits load it: the real verifier
remains necessary.

The measured baseline results and limitations are in
`docs/reports/pra232-dfthcsos.md`. Method sources and module ownership are in
`notices/30-dfthcsos.txt`. No external factorization or compiled notebook
artifact is consumed. This experiment does not refit factors, implement the
parents' signed-gauge canonicalization, or claim that other precision
optimizers cannot work. A result below the 1.2× floor is a negative result,
not a shipping candidate.
