# PRA-232: measured circuit-half negative result

The fixed eleven-point ablation did not meet the 1.2× floor. The best G2-passing point is **direct12-j9**, verified at **1.077784065×** (T=85,109, Q=742, cost=3113424754.7759748). The target was 1.4×. This closes the permitted measured-negative path; it is not a shipping candidate.

The reference parent is submission-001 because submission-003 has no manifest on the branch base. Its chemistry cost is 3,355,599,588.3155365. The Google baseline NPZ is unchanged at 12 bits; only lower-precision experiments replace its angle_words. All weights, vectors and the Givens tree remain unchanged.

## Method and model

For unchanged 12-bit words, λ_eff is constant, so the ratio is (93,237 × 730)/(T × Q). The initial historical planning point of T=71,958 and Q=681 implied 1.389×, but was not a reproduced baseline result. At Q=730, the floor requires T≤77,697 and the target T≤66,597. These were budgets, not measured predictions.

The table below uses static circuit counts plus the unchanged verifier heuristic model for the predicted column. The real verifier then simulates every legal address at 64 shots, forward and reverse, with public salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`. No seeds or salts were selected. Precision-failing predictions are hypothetical resource ratios, not valid scores.

| Point | T | Q | ANGLE Q | Predicted ratio | Measured ratio / rejection | Seconds |
|---|---:|---:|---:|---:|---|---:|
| direct12-j9 | 85109 | 742 | 128 | 1.077784065× | 1.077784065× | 58.50 |
| direct12-six | 85595 | 742 | 126 | 1.071664513× | 1.071664513× | 51.64 |
| bank2-12-j4 | 93965 | 682 | 114 | 1.062088383× | 1.062088383× | 59.52 |
| bank2-12-j5 | — | — | >128 | — | ANGLE qubit cap exceeded by requested layout | 0.56 |
| bank4-12-five | 98049 | 658 | 113 | 1.054974808× | 1.054974808× | 62.78 |
| bank4-12-six | 97669 | 658 | 114 | 1.059079390× | 1.059079390× | 63.11 |
| bank4-12-j3 | — | — | >128 | — | ANGLE qubit cap exceeded by requested layout | 0.01 |
| direct11-j9 | 84809 | 733 | 119 | 1.092635036× | error_1 = 76.9091 mHa > 20 mHa; error_2 = 29.7238 mHa > 20 mHa | 91.30 |
| bank2-11-j5 | 76975 | 689 | 128 | 1.280713891× | error_1 = 76.9091 mHa > 20 mHa; error_2 = 29.7238 mHa > 20 mHa | 98.04 |
| direct10-j10 | 76581 | 734 | 120 | 1.203337154× | error_1 = 133.4933 mHa > 20 mHa; error_2 = 43.8206 mHa > 20 mHa | 81.74 |
| bank2-10-j5 | 76529 | 684 | 118 | 1.292177810× | error_1 = 133.4933 mHa > 20 mHa; error_2 = 43.8206 mHa > 20 mHa | 93.88 |

Five/six-wire four-address banking saves 380 Toffolis at unchanged total Q; it does not meet the floor. Two-address J=5 and four-address J=3 at 12 bits exceed the circuit cap. Direct J=9 with eight traversal wires wins because it needs nine circuits; the narrower banks require more circuits. The six-wire direct schedule recomputes more products and cannot reduce total Q because heuristic temporary workspace is already larger.

## Selected physical and stage metrics

λ_eff=49.30136925057439; Λ=308.45593973309445; E_gap=3.965477244291833 Ha; E_upper=−22140.27335 Ha; error_1=0.0031851950317986553 Ha; error_2=0.018639570630974208 Ha. Verified shots=254464; verifier time=47.462 seconds.

| Stage | Toffolis | Persistent Q | Temporary Q |
|---|---:|---:|---:|
| ANGLE, both passes | 71,352 | 108 | 8 |
| Outer preparation | 846 | 46 | 370 |
| Inner preparation | 9,461 | 44 | 544 |
| Givens | 3,450 | uses shared registers | uses shared registers |
| Total | 85,109 | 198 | 544 |

ANGLE circuits additionally contain 12 selection qubits and individually use 128 qubits. Score Q follows the verifier formula, 198 + max(544, 370, 8) = 742.

## Verification and boundaries

```text
uv sync
Resolved 50 packages; Installed 12 packages
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
kickmix 0.1 .../kickmix/kickmix.so
uv run pytest -q
249 passed, 1 skipped in 62.26s (0:01:02)
```

The baseline suite before edits was 222 passed, 1 skipped. The one skipped module requires the optional notebook dependency group. New tests cover dirty targets, all addresses of partial and complete banks, inverse application, phase/workspace cleanup, static counts, non-power-of-two pebbling, invalid/cap inputs, deterministic output and the G2 precision regression. The latter failed with `assert 12 == 4` before the fix. The first new-QROM test run failed collection before the module existed.

Clean-worktree reproduction at commit `2367006c81e0fd020c41960ebe7fb828690695b8` passed with only the declared hash-pinned NPZ visible as VQCC_DATA: `missing=[]`, `extra=[]`, `changed=[]`. All nine circuits and the NPZ matched. `ledger/experiments/pra232/rebuild.json` is the exact helper report. Later changes isolate the proxy/docs to avoid conflicts with the factor PR; they do not change circuit generation.

No complete three-task zip, submission candidate, G0–G5 shipping claim or durable submission-queue entry was created: the requested 1.2× floor failed. The full chemistry verifier and isolated chemistry rebuild are evidence for the explicitly permitted negative-result deliverable, not substitutes for full-bundle gates. Other task circuits were not rebuilt or reverified. No Kaggle upload, merge or live-system change was performed.

This is a bounded negative result for the eleven named configurations, not a proof that all circuit optimizations or lower-precision encodings fail. Signed-gauge canonicalization, nonlinear output compression and factor refitting remain untested. PRA-201 can use this parameterized builder after its factor input passes accuracy checks.

## Selected file receipts

| File | Bytes | SHA-256 |
|---|---:|---|
| dfthcsos/submission.npz | 4537436 | `14d5cc25eb3bf82a9ccb87c811db28d127bef6d28697dd190dc1e875de3bfe69` |
| dfthcsos/angle_k_0.kmb | 2508048 | `ab81100daa029b69ff979effae6ff862373017d39fd10344846ed4f21ceafaa3` |
| dfthcsos/angle_k_1.kmb | 2507528 | `c001e0051b887b2f7fe0bcf39ffff9a1ad223f987b577253cb7e39501440b2d8` |
| dfthcsos/angle_k_2.kmb | 2507584 | `b41c7e0329eed8ffa554d8a439ae6612749cd10b9ab922395b30dbac33a00471` |
| dfthcsos/angle_k_3.kmb | 2773781 | `02385346ae092a8a37e5ea535d0f17c48c11a6b8f75e513d944868a07f06854f` |
| dfthcsos/angle_k_4.kmb | 2990235 | `43211fc5e243f97142389470bcaba4f211902d1aa2477d74edcebd9bdf20a2b4` |
| dfthcsos/angle_k_5.kmb | 2997807 | `b46355d2012c9c671a024b19aa620aab61c5d7f095f9e2bd73539e5596bdcd44` |
| dfthcsos/angle_k_6.kmb | 2991854 | `1c5d402a69faf6e3c6dc0abcc6db716acb8c489f5574f88b683c5343ddb187c8` |
| dfthcsos/angle_k_7.kmb | 2991738 | `1337e5efcac9a4e72f636135d4d244c3fe68b7422f7a519b4f1516515d98727c` |
| dfthcsos/angle_k_8.kmb | 2991725 | `8393466f691323c3f1888a4d069e08144a48176201ca9e79003bad22bafe1da9` |

All experiment-family receipts, complete verifier outputs, parameters and run times are stored in `ledger/experiments/pra232/results.json`; the generated binaries stay under `/home/cld-main/work/vqcc-data/pra232-circuit/ablation`. Source notebook hashes/licences and module provenance are in `notices/30-dfthcsos.txt`.

## Complete verifier output (selected point)

```json
{
  "status": "PASS",
  "score": 3113424754.7759748,
  "lambda_eff": 49.30136925057439,
  "toffoli_count": 85109.0,
  "num_qubits": 742,
  "brot": 12,
  "batch_size": 9,
  "num_circuits": 9,
  "reaction_depth": 90,
  "num_ops": 2789965,
  "verified_shots": 254464,
  "submission_sha256": "557248822c476bf249bafdeb76b59922473ba9cf6766d4e1e63f405ef309f934",
  "resources": {
    "brot": 12,
    "keep_bits": 10,
    "angles_toffoli_per_pass": 35676.0,
    "angles_toffoli": 71352.0,
    "angles_qubits": 128,
    "angles_selection_qubits": 12,
    "angles_persistent_qubits": 108,
    "angles_temporary_qubits": 8,
    "outer_state_prep_toffoli": 846,
    "inner_state_prep_toffoli": 9461,
    "givens_rotations_toffoli": 3450,
    "outer_state_prep_persistent_qubits": 46,
    "outer_state_prep_temporary_qubits": 370,
    "outer_state_prep_qubits": 416,
    "inner_state_prep_persistent_qubits": 44,
    "inner_state_prep_temporary_qubits": 544,
    "inner_state_prep_qubits": 588,
    "heuristic_persistent_qubits": 90,
    "heuristic_temporary_qubits": 544,
    "heuristic_toffoli": 13757,
    "heuristic_qubits": 634,
    "persistent_qubits": 198,
    "temporary_qubits": 544,
    "toffoli": 85109.0,
    "qubits": 742,
    "angles_within_cap": true
  },
  "metrics": {
    "error_1": 0.0031851950317986553,
    "error_2": 0.018639570630974208,
    "Lambda": 308.45593973309445,
    "E_SOS": -22144.23882724429,
    "E_gap": 3.965477244291833,
    "lambda_eff": 49.30136925057439,
    "gap_in_domain": true
  }
}
```
