# tasks/dfthcsos

**dfthcsos** (FeMoCo block encoding, N = 76 orbitals, 113 electrons): K `angle_k_*` QROM circuits (≤ 128 qubits
each) plus `submission.npz` (U (R,B,76), W (R,B,C), H2_I (R,C), H1_I (), Hsym_lower (2926,), tree_edges (75,2)).
A submission is rejected if the Hamiltonian error is > 20 mHa, Λ ≤ 49.0, or Egap ≤ 3.914898 Ha.
Cost = λ_eff × T_total × Q_total with λ_eff = √(Egap(2Λ − Egap)) (inferred). Reference (R,B,C) = (65,60,60),
b_rot 12, J 8, 10 circuits, Λ ≈ 308, λ_eff 49.3 → cost 3,355,599,588. Angle lookups are ≈ 88% of T; Inner-prep
temporaries are ≈ 75% of Q.

Public reports on 2026-10-23 gave 1.44× (681 qubits, 71,958 Toffolis, λ_eff 47.56). That factor is not shipped: its generator is not in the Apache-2.0 notebook, and the notebook traces the file to k256.dev (D-PRA177-01).

`generate.py` rebuilds the package reference instead (10 ordinary-QROM circuits, `b_rot` 12, `J` 8, score 1.0). Candidates go in `candidates/`; `.kmb` and `.npz` files there are never committed.
