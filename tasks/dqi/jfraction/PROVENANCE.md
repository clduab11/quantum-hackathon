# Paired J-fraction source provenance

This is a port, not independent clean-room authorship. John Wick accepted the
source closure and explicitly authorized implementation on PRA-236, comment
05512dbf-e151-4227-9e10-df426d73be11 (2026-10-25). The pre-port report is
[PRA-236 provenance-check](/PRA/issues/PRA-236#document-provenance-check), revision
9d274e8d-9e50-492a-a135-b202ada0cffd. D-PRA236-01 records the scope.

## Parents

- SomeJoint / Agniv Banerjee, public J-fraction decoder and arithmetic, v3:
  https://www.kaggle.com/code/somejoint/quantum-circuits-8-95-lb-cost-breakdown
  Source SHA-256 `1d079146539f555d1a50c46904777838cf59dbff66805655198a0ec63980e01b`.
  The notebook explicitly releases code as Apache-2.0 and includes the licence.
- Immediate parent: anazemcev / Artem1410 / ViberTeam, paired-v6, notebook v6:
  https://www.kaggle.com/code/anazemcev/quantum-circuits-881q-paired-dqi-r6-df-thc
  Source SHA-256 `d4a147523ac07cb2dc5fe4bd5dc9c7da48719e34dfc847402628723b37930682`.
  Apache-2.0 text and NOTICE embedded in cells 24 and 29. Its 42 embedded DQI
  file hashes passed the author manifest check. Twenty SomeJoint DQI files and
  all 21 Manwithacat upstream files independently matched byte-for-byte.
- Phuc Thai: EXP-118c memory/gap-pointer and EXP-119a paired-extraction ideas:
  https://www.kaggle.com/code/phucthaiv02/qcc-verified-portfolio-df-thc-retraining-study
  Inspected v11 source SHA-256 `6d0e9fd742582f73ae891f03d5991b6948f695b7d5d9a0ee9e3af878d705d5e9`.
  Apache-2.0 stated in its credits. No unpublished generator or binary was used.
- Manwithacat projection **method**, v2:
  https://www.kaggle.com/code/manwithacat/dqi-classical-mask-projection-9-13909?scriptVersionId=362021360
  Inspected source SHA-256 `1cc60c4bd041c53ae7b951acd85a7a41d53c979322dbe31ba370c70c69f4bf6f`.
  The original file was read during the audit, but is not copied or transliterated.
  Its own licence grant was unresolved in captured source. `projection.py` is
  new Praxen code using Lagrange interpolation and binary trace-matrix inversion
  from the mathematical specification. It is **not a strict clean room**.
  John Wick accepted this boundary; no final legal determination is claimed.
- Google Quantum AI: Kickmix (pinned repository environment) and our committed
  `tasks/dqi/reference_circuit.py` (Apache-2.0) supply field/builder primitives
  and reference base classes. No external reference circuit is read. The
  reference code's Khattar/Proos-Zalka citation remains in that source; no
  Zenodo implementation or compiled artifact is an input.

The historical whole-notebook Manwithacat digest recorded by the immediate
parent differs from our public API source-string digest. That container was
not recovered; file-level identity was verified independently and is the
basis of the audit. We do not claim whole-notebook identity or a recovered
Phuc v9 / ViberTeam predecessor snapshot.

## Modifications and input boundary

`SOURCE_MAP.json` maps every ported module to the exact parent path and hash,
records the current port hash, and names the edits. Package imports replace
notebook path manipulation; CLI entry points and the unused compact-gap alternative driver are removed. `common.py` imports
the committed reference source directly. `decoder.py` is the paired-v6 branch
of the parent's builder, with our new projection. The matrix threshold is
fixed at 14; fused pairing and the zero-metadata loan are fixed, not selected
by environment variables. The norm-recycle call is explicit instead of a
module monkey-patch. Parent algorithms and approximation limits are retained.

`generate_jfraction.py` is a new source-only CLI. It takes no circuit input: it writes `OUT/dqi.kmb` then hashes those output bytes. No verify-only
path, notebook wrapper, Kaggle salt, network operation, coefficient file,
compiled circuit or numerical toolbox array is present. Field basis maps and
projection constants are regenerated from source and Kickmix field operations.
The generator uses standard Python and Kickmix only. Parent mixed-portfolio
arithmetic, chemistry, datasets, reports and outputs are excluded.

Pure-source model imports are relative package imports. The generator has no
package-data input; G5 declares only the unchanged chemistry task's baseline
factorization. No compiler source is loaded through an external data path.

Full Apache text is in `LICENSE` (SHA-256
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`).
Pertinent upstream attribution and modification notices are in `NOTICE` and
`notices/20-dqi.txt`. The material is a source port, not a claim to invent the
decoder. Numerical correctness and shipping remain separate gates.

## Module map

Parent paths below are relative to the 42-file DQI source embed. Exact SHA-256
values for both parent and port are machine-readable in `SOURCE_MAP.json`.

| Port file | Parent path | Changes |
|---|---|---|
| `compact_euclid.py` | `upstream/dqi/compact_euclid.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `compact_gap_variant.py` | `compact_gap_variant.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `compact_lifetime_kernels.py` | `compact_lifetime_kernels.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `counter.py` | `upstream/dqi/counter.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `cubic.py` | `upstream/dqi/cubic.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `early_a.py` | `upstream/dqi/early_a.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `evaluation.py` | `upstream/dqi/evaluation.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `forney_control.py` | `upstream/dqi/forney_control.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `jfraction_decoder.py` | `upstream/dqi/continued_fraction/jfraction_decoder.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `jfraction_gap_decoder.py` | `upstream/dqi/continued_fraction/jfraction_gap_decoder.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `matrix_pair_kernels.py` | `matrix_pair_kernels.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. Fixed BORROW_ZERO_META=True (paired-v6). |
| `mc4_inverse.py` | `mc4_inverse.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `merge_kernels.py` | `merge_kernels.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `model_fast_extraction.py` | `upstream/dqi/continued_fraction/keyeq/model_fast_extraction.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `model_jfraction.py` | `upstream/dqi/continued_fraction/keyeq/model_jfraction.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `narrow.py` | `upstream/dqi/narrow.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `norm_recycle_inverse.py` | `norm_recycle_inverse.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `paired_kernels.py` | `paired_kernels.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `phase_tensor.py` | `phase_tensor.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `poly_arithmetic.py` | `upstream/dqi/continued_fraction/poly_arithmetic.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `quadratic_cube.py` | `quadratic_cube.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `quotient.py` | `upstream/dqi/quotient.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `quotient_hmr.py` | `upstream/dqi/quotient_hmr.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `recursive.py` | `upstream/dqi/recursive.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `smallspace_inverse.py` | `smallspace_inverse.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. Direct norm-recycle call replaces runtime monkey-patching. |
| `static_divisions.py` | `upstream/dqi/static_divisions.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `sweep.py` | `upstream/dqi/sweep.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `tower.py` | `upstream/dqi/tower.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `zero_chain.py` | `upstream/dqi/zero_chain.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `zero_mask_inverse.py` | `zero_mask_inverse.py` | Package imports; removed notebook sys.path configuration and standalone CLI; model import made relative; phase_tensor uses new projection.dual_basis. |
| `common.py` | `upstream/dqi/common.py` | Replaced notebook/runtime path setup with package import of committed Google reference source; field validation; no verifier import. |
| `decoder.py` | `build_paired_dqi.py` | Selected paired-v6 only; new projection; fixed schedule; no runtime monkey-patching; package imports; no build/verification wrapper. |

`projection.py`, `gates.py`, and the output driver are new Praxen code.
