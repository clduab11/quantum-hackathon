# hengck23 discussion 753607 — nine edits (PRA-322)

Source: https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/discussion/753607
Title: "DQI: The baselines 58.62x" (hengck23). Posted ~2026-10-28.
Licence of the post: discussion prose/screenshots; underlying decoder lineage is SomeJoint Apache-2.0 (our vendored fused). No Schur/jday96314 input.
Captured via jina reader + public Google Cloud attachment URLs (screenshots). SHA-256 of attachments recorded beside this file.

Baseline (iter 000) = our vendored fused circuit SHA-256 `7beea291a5de36ef2b4fb50585b2f8d7cce02d3c575b491cf5dcc93e9d9655f6`, Q 889, mean T 474,308, ~54.08× (3 jet-zero-pivot failures in their quick note).

| # | iter | description | ΔT | → mean T | ΔQ | → Q | score notes |
|---|------|-------------|----|----------|----|-----|-------------|
| 1 | 001/002 | `phase_zero` 22-Toffoli ladder only when measurement bit m=1 via `push_condition(m)` | −374 | 473,934 | 0 | 889 | 54.125 (54.382) |
| 2 | 004 | projective left-looking extract for targets ≥ group 5; jets 289→16; parity for ∞ | −15,259 | 458,675 | +12 | 901 | 55.101 (55.056); 0 failures (003 failed smoke) |
| 3 | 005 | low-width reverse extract; streamed 12-bit inverse; `phase_inverse39` | −2,184 | 456,491 | −12 | 889 | 56.869 (56.823) |
| 4 | 006 | rolling-border synthesis; self-inverse 42-Toffoli XOR products | −4,009 | 452,482 | 0 | 889 | 57.373 (57.326) |
| 5 | 007 | one squared product per head in synthesis tail | −2,856 | 449,626 | 0 | 889 | 57.737 (57.690) |
| 6 | 008 | "outerless": drop outer fold `C = q_0·B mod A` | −3,386 | 446,240 | 0 | 889 | 58.175 (58.128) |
| 7 | 011 | convert: clear flags by measurement (not recompute zero test) | −456 | — | — | — | 58.343 / 58.295 |
| 8 | 012 | synthesis: drop zero flags on the last 17 folds | −1,377 | — | — | — | 58.524 / 58.445 |
| 9 | 013 | reverse extract: skip early-termination for targets g ≤ 9 | −765 | 442,818 | — | 889 | **58.625** / 58.541; 0 failures |

Final: Q 889, mean T 442,818, ratio 58.625×, 0 failures.
Iters 009–010 not shown in the captured screenshots.

## Measurement log (Praxen)

| edit | circuit SHA-256 | Q | T_static | notes |
|------|-----------------|---|----------|-------|
| baseline | `7beea291…9655f6` | 889 | 487,331 | vendored pin |
| e001 | `21f8484f…1c9f` | 889 | 487,331 | static T unchanged (push_condition); mean ΔT pending score_local |
| e002 | `210c7e4c…0f2a` | **901** | **496,522** | Q matches hengck (+12). Static T still +9,191 vs baseline 487,331 (mean ΔT pending score_local). linear square + W-park + Di snapshot. |

## Classical projective oracle (edit 002)

`projective_classical.py`: thresh=5 leaves 16 full jets; 20/20 random cases match affine `extract()`. Quantum patch Q=901 (hengck). Static T 496,522 (+9,191 vs baseline). Next: score_local mean ΔT; edits 003–009.

## Discussion drift (2026-10-29)

hengck23 later posts show 59.90× via SomeJoint convert splice / circuit surgery (iters 014–015), not only the original nine edits. New attachments under `new-Selection_547*.png`. Ticket success remains ≥58.0× from the documented nine-edit port on the Apache-2.0 fused lineage.

## Attachment SHA-256 (not committed; kept under vqcc-data / local evidence)

- `att-61d2559da9a9.png`: `4813564442ec7bc43cbab43d882079a0721679a5f55911f3edaf1fcc2e0fc935`
- `att-f4d10388325b.png`: `21842dfdf721bf5f6d592acc2f5dea3a99bc6e4ab038599b739ff1abe42631af`
- `edit-img-1.png`: `e9839bc737de22c8602ead6440a558fb45d3fe0c96643033134954e3987bc32b`
- `edit-img-2.png`: `c42c403336ead22a5e490ca765e6c6f914c6371c0083d412035cb3ce8970e537`
- `edit-img-3.png`: `fdaf3311a43eb867b338d93f7ac56fcaf66d2ac7354b591012687fd36ceaaca5`
- `new-Selection_5471.png`: `d1332476638ba8f5072ef208dbe4a2d7d56dec3ca812fd8e7b21591621a1847a`
- `new-Selection_5472.png`: `91d60355f6ea6f7a7a18df92a5991a87255e084df098ce01835594220e29727e`
- `new-Selection_5475.png`: `7f8f262a5c6a6d20f7a72de3eb5e8a28e3e3787085c43cb84fa78996caf71e1f`
