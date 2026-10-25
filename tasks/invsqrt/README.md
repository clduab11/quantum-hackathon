# tasks/invsqrt

**invsqrt** (fusion): phase |x⟩ by β/√x for x ∈ 1..3,133,452 in one 22-qubit register `x` (β = 1, n_p = 10).
Tolerance is 2⁻²⁴·β/√x turns. There are 64 shots per x, so 200,540,928 shots, and **zero failures are allowed**.
Cost = Q × (Toffoli + T/4), with rotations priced at 0.56·log₂(1/ε) + 5.3 T. Reference: Q 260, 7,735 Toffolis,
37 rotations → cost 2,076,774. The submission has exactly one register.

PRA-176 lineage: 12.6136× (92 qubits, 1,472 static Toffolis, 45 rotations).

PRA-200 generator: `generate.py`. This circuit is a port. Coefficients are fitted by `fit_coefficients.py` (provenance `own`). The module map is `PROVENANCE.md`. The circuit is the 90-qubit Gray curvature schedule, an exact-domain affine Toffoli/CSWAP rewrite, and one dropped rotation (44). Modelled cost is about 13.16× before the full-shot verifier. Apache-2.0 parents are named in `NOTICE`. Alex v8 and Mizero v1 are reference-only. The integer mirror is `mirror.py`. `.kmb` files are never committed.
