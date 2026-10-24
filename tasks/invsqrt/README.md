# tasks/invsqrt

**invsqrt** (fusion): phase |x⟩ by β/√x for x ∈ 1..3,133,452 in one 22-qubit register `x` (β = 1, n_p = 10).
Tolerance is 2⁻²⁴·β/√x turns. There are 64 shots per x, so 200,540,928 shots, and **zero failures are allowed**.
Cost = Q × (Toffoli + T/4), with rotations priced at 0.56·log₂(1/ε) + 5.3 T. Reference: Q 260, 7,735 Toffolis,
37 rotations → cost 2,076,774. The submission has exactly one register.

Public lineage on 2026-10-23: 12.61× (92 qubits, 1,472 Toffolis; quadratic signed-digit Horner + 256-entry QROM).

Generator: `generate.py` (P0-6). Parent: Apache-2.0 notebook [Quantum Circuits \| Signed-Digit Memory](https://www.kaggle.com/code/anazemcev/quantum-circuits-signed-digit-memory), v3. The integer mirror is `mirror.py`. Candidates go in `candidates/`; `.kmb` files are never committed.
