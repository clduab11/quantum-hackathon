# tasks/dqi

**dqi** (combinatorial optimization): a reversible Reed–Solomon RS(4095,4025,71) syndrome decoder over GF(2¹²).
There are 70 syndrome registers S0..S69 (840 qubits) and the classical record is in E0..E4094. 102,400 shots;
failures are allowed. Cost = **R(ε⁺) × Q² × T** with R(ε) = ln2 / (−ln(½ + 2√ε)) (inferred). ε⁺ is a one-sided
Clopper–Pearson bound at δ = 2⁻¹²⁸ (≈ 88.7/N at zero failures), so the zero-failure floor is R = 1.19126. One failure
costs +0.45%. **Q is squared.** Reference: Q 1,893, 5,725,461 Toffolis → cost ≈ 2.44e13; 86M ops, 845 MiB `.kmb`.

The k256.dev dqi artifact is reference only and is never shipped (R10).

Generator: P0-7 (reference rebuild) and P1 (Berlekamp–Massey + Forney). Candidates go in `candidates/`; `.kmb` files
are never committed.
