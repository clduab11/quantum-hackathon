# tasks/dqi

**dqi** (combinatorial optimization): a reversible Reed–Solomon RS(4095,4025,71) syndrome decoder over GF(2¹²).
There are 70 syndrome registers S0..S69 (840 qubits) and the classical record is in E0..E4094. 102,400 shots;
failures are allowed. Cost = **R(ε⁺) × Q² × T** with R(ε) = ln2 / (−ln(½ + 2√ε)) (inferred). ε⁺ is a one-sided
Clopper–Pearson bound at δ = 2⁻¹²⁸ (≈ 88.7/N at zero failures), so the zero-failure floor is R = 1.19126. One failure
costs +0.45%. **Q is squared.** Reference: Q 1,893, 5,725,461 Toffolis → cost ≈ 2.44e13; 86M ops, 845 MiB `.kmb`.

The k256.dev dqi artifact is reference only and is never shipped (R10).

`generate.py --out DIR` restores the pre-PR #18 competition reference decoder (Apache-2.0), byte for byte from `c2874d04d7a3346a7c8e0c3c6dddfd2150a9f947`. `reference_circuit.py` remains the reference config's entry point; `configs/gates/reference.yaml` is unchanged. Both rebuild the same reference circuit. The BM+Forney implementation is withdrawn by the held PRA-231 recovery; its provenance map, attributions, decisions and ledger evidence remain as history. See D-PRA231-01 and D-PRA226-03. The k256.dev artifact is not a parent. `.kmb` files are never committed.
