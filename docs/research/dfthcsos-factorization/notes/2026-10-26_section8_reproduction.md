# dfthcsos lane — section 8 reproduction (2026-10-26)

**Result:** v7's stored 8-bit `angle_words` reproduce the verifier's metrics on Windows to within 2e-16 Ha (error₁, error₂) and exactly (Λ, E_SOS, E_gap, λ_eff). The baseline's 12-bit words reproduce the README's values exactly. For the `SpinFreeData_V1` cost split, 11 of 14 fields match `chem_verify.json` directly; the other 3 differ only by the ANGLE terms (10,032 ANGLE Toffolis; 32 = J·brot word-register qubits), see §2. Both scores match the verifier exactly. The stored words are therefore the ones the circuits load (as checked by Chris's WSL verifier run), and the Windows harness can be trusted for accuracy gates and the cost model.

Evidence class: **evaluate_words + cost model on Windows**. The only verifier-confirmed numbers here are the ones Chris ran in WSL and v7's `chem_verify.json`.

## 1. Accuracy metrics from the stored words

| | Baseline (65, 60, 60), brot 12 | v7 (4, 303, 128), brot 8 |
|---|---:|---:|
| error₁ (mHa) | 3.1852 | 17.8131 |
| error₂ (mHa) | 18.6396 | 19.7209 |
| Λ | 308.455940 | 289.873633 |
| E_SOS (Ha) | -22144.238827 | -22144.188415 |
| E_gap (Ha) | 3.9654772 | 3.9150652 |
| λ_eff | 49.30136925 | 47.48073950 |
| error₂ margin to 20 mHa | 1.3604 mHa | 0.2791 mHa |
| error₁ margin to 20 mHa | 16.8148 mHa | 2.1869 mHa |
| E_gap margin over 3.914898 Ha | 50.5792 mHa | 0.1672 mHa |
| passes accuracy gates | True | True |

Agreement with the verifier:
- v7 vs `chem_verify.json`: error₁ differs by +1.6e-16 Ha, error₂ by +1.0e-17 Ha; Λ, E_SOS, E_gap and λ_eff are bit-identical.
- Baseline vs README: Λ, E_gap and λ_eff are bit-identical. error₁ and error₂ agree with Chris's WSL run to its 4 decimal places in mHa (3.1852, 18.6396).
- v7's `one_body_requires_refresh` flag is `False`, consistent with the stored one-body words being the shipped ones.

## 2. Cost-model split (`SpinFreeData_V1`, chi = 10, beta = brot)

| | Baseline | v7 |
|---|---:|---:|
| outer prep T | 846 | 378 |
| inner prep T | 9,461 | 11,032 |
| Givens T | 3,450 | 2,250 |
| **T_heur** | **13,757** | **13,660** |
| ANGLES T (from verifier) | 79,480 | 10,032 |
| **T_total** | **93,237** | **23,692** |
| outer / inner persistent qubits | 46 / 44 | 42 / 45 |
| J·brot word registers | 96 | 32 |
| persistent total | 186 | 119 |
| temporaries outer / inner / ANGLES | 370 / 544 / 11 | 96 / 321 / 84 |
| **Q_total** | **730** | **440** |
| score = λ_eff·T·Q | 3,355,599,588.32 | 494,962,019.33 |

Both scores equal the verifier's to the last digit printed (baseline 3,355,599,588.32; v7 494,962,019.33).

Field-level comparison with v7's `chem_verify.json` (`check_resources_against_verifier` in the harness; all assertions pass). `heuristic_costs` and `verify.resource_costs` use the same names for different scopes: the first for state prep plus Givens only, the second for totals (it calls the state-prep part `heuristic_*`). Of the 14 shared field names, 11 match directly. One of those 11, `temporary_qubits`, is also a scope clash and agrees only because max(321 inner, 84 ANGLE) = 321. The other 3 differ only by the ANGLE terms:

| Field | `heuristic_costs` (state prep only) | `chem_verify.json` (total) | Gap |
|---|---:|---:|---|
| `toffoli` | 13,660 | 23,692 | 10,032 ANGLE-circuit Toffolis |
| `persistent_qubits` | 87 | 119 | 32 = J·brot (4 × 8) word-register qubits |
| `qubits` | 408 | 440 | the same 32 |

The baseline's ANGLES figures come from the README (10 circuits × 3,974 Toffolis × 2 passes; 119 qubits − 12 selection − 96 word = 11 temporaries); v7's come from `chem_verify.json`.

**Why inner prep dominates at v7's shape.** The qubit-optimizing rule in `find_qroam_size_to_minimize_global_temp_ancilla` requires the inner QROAM temporaries to stay below brot·(N−1) = 600. With word width b2 = ⌈log2 B⌉ + 11 = 20, that caps the QROAM block exponent at k2 = 4 (unconstrained optimum 6). The main QROAM term is then R·C·⌈(B+1)/16⌉ = 4·128·19 = 9,728 of the 11,032 inner Toffolis, and the 321 temporaries are 7 (uniform) + 14 (address) + 15·20 (QROAM). Consequences for shape choice (cost model only):
- At B = 303, T_heur is close to linear in R·C: about 20.4 T per unit of R·C (C = 64 / 96 / 128 at R = 4 gives 8,449 / 11,049 / 13,660; R = 1 / 2 / 3 / 4 at C = 128 gives 5,836 / 8,449 / 11,049 / 13,660).
- B enters mainly through ⌈(B+1)/16⌉, so the cheapest B in each step is B = 16m − 1. v7's B = 303 already sits at the cheap end of its step (B = 304 jumps to 14,173). The next step down is B = 287 (13,132, −528 T), then B = 271 (12,604). b2 also drops by one bit for B ≤ 256.
- All six target rows in the brief §3 reproduce exactly (T_heur and Q, assuming ANGLES temporaries ≤ inner temporaries).

## 3. Provenance

| Input | Source / licence | SHA-256 |
|---|---|---|
| v7 `dfthcsos/submission.npz` | https://www.kaggle.com/datasets/ahmedberatozer/vqcc-v7-chemistry v1 (2026-10-26T15:31:37Z), downloaded anonymously by Chris. Kaggle licence field "Other (specified in description)"; description: author's parts Apache-2.0, credits mrmeows' Apache-2.0 dataset | `a942a81f892d6fe9210435016bea08b68fe371dff6ce2741f99e0c80f2d0046a` |
| v7 `chem_verify.json` | same | `7199693281412ca001423fd578769b3d20c9e09bffaf0856c390775cc5c7301e` |
| v7 `SHA256SUMS.txt` | same (rebuilt by Chris, does not list itself); all 22 listed files match | `31c3aae47fec199077cc104f57a80b938e2ad8225e1a67cf322f7fd922da5fb6` |
| `FeMoCo76o113e.fcidump` | competition data; matches SCORING_README and `reference.FCIDUMP_SHA256` | `e5a48af746fd075026dec9e8f5df2d363802a121e8c53af9a0b984bde695e1bd` |
| `FeMoCo76o113e.fixed_shifts.npz` | competition data; matches `reference.FIXED_SHIFTS_SHA256` | `7b7facf63fe35a9d9d3d00787ffdb700c863fa845fe4724d7f7c54778151cd87` |
| `verify.py` | competition verifier, Apache-2.0 (`verifiers/LICENSE.txt`) | `0775be7a528922367caebe9e4d051d6199811f1aefeaa4b793eaaa4621b8ec9d` |
| `scoreinfra/dfthc_math.py` | same | `ae82898d47a7a86b96378fb906e0f8a9f46003065cf19c7c09952a123b5b5af8` |
| `scoreinfra/costs_prepare.py` | same | `7f1e190c42fc5325f3e6689fbbef51f95b0cb12f1c828cda92b6c088e72206da` |
| `scoreinfra/reference.py` | same | `a2d5a63191d655729e29f0fde1e85fe4630bf896a91a63bb894d8d7daf71ed39` |
| baseline `sample_submission/dfthcsos/submission.npz` | competition data | `14d5cc25eb3bf82a9ccb87c811db28d127bef6d28697dd190dc1e875de3bfe69` |

Full manifest of all 56 input files: `input_sha256.tsv` (same folder).

## 4. Method and reproducibility

- Harness: `out/harness/vqcc_eval.py` (SHA-256 `0c51e59580976ebab596ebdad6d9321e636b6636e9b5cb08a3cf65e2b038163e`; adds `check_resources_against_verifier`). It imports the unchanged `scoreinfra.reference`, `dfthc_math` and `costs_prepare` from `competition/verifiers`. It runs `native_inputs`, `heuristic_costs`, `passes_accuracy` and the gate constants straight from `verify.py`'s source via AST extraction, because `verify.py` imports kickmix and cannot load on Windows. No metric is reimplemented.
- `load_inputs` follows `verify.load_inputs`: `load_factorization` (allow_pickle=False), fixed shifts forced, then `native_inputs` (S rounded to float32; FCIDUMP two-electron integrals stored as float32 by `load_reference`).
- Hardware: Windows 10, 16 CPUs, 48 GiB RAM, numpy 2.4.6. Wall clock: FCIDUMP load 28.7 s, `evaluate_words` 4.1 s (baseline) and 5.3 s (v7).
- No fits, no seeds, no verifier runs in this step.

## 5. Proposed `docs/DECISIONS.md` row (for Chris)

| Date | Decision | Reason |
|---|---|---|
| 2026-10-26 | Windows-side accuracy gates and cost model come from `out/harness/vqcc_eval.py`, which executes the unchanged verifier code (AST-extracted from `verify.py` and imported from `scoreinfra`). The WSL verifier stays the authority for every candidate. | Reproduces v7 and baseline metrics and costs bit-for-bit (section 8), so fitting can be screened without kickmix. |
