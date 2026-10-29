# invsqrt generator provenance

This generator is a **port**. It is not independent clean-room authorship.
Coefficient provenance is `regenerated; dataset-adapted calibration; licence unresolved`.
Nothing in this map is a shipment.
A ledger candidate still needs G0–G5, the full-shot verifier, and a
candidate-specific Adjudicator sign-off (D-PRA202-05). Historical P0 rows
stay unchanged.

## Coefficient fit (dataset-adapted calibration; licence unresolved)

| Field | Value |
| --- | --- |
| Module | `tasks/invsqrt/fit_coefficients.py` |
| Provenance | `regenerated; dataset-adapted calibration; licence unresolved` |
| Calibration lineage | [kozykappa/quantum-ai-dataset version 1](https://www.kaggle.com/datasets/kozykappa/quantum-ai-dataset?datasetVersionId=21136269), datasetVersionId 21136269; Kaggle licence label "Other (specified in description)" |
| Calibration source | `code/domain_tables.py`, SHA-256 `59cf4d98899433dcc49d9ce512293be20d33da5334211c20e35323555994a4fb`; `valid_residuals`, `calibrate_segment` and `regenerate_tables_exact` follow lines 8–43 |
| Dataset table | `code/coefficients.json`, SHA-256 `98bd211f22b158bf05a4d2d934ab966e5e97e54d8307b82e2ca58910c6830763`; locally regenerated output equals 256 of 256 rows |
| Rights evidence | README SHA-256 `fc19f8538dfbbfe9c8342d6fea10edc2ca178e66cd14eef14c12c3b648cdae70`; `catalog/license_map.csv` SHA-256 `5badf60ae5dc035f890b00e262f8e87345c3f13d323a405e89077b42a4d3fac8`. Neither names the two files; file-specific rights unresolved |
| Caller | `signed_digit.regenerate_tables_exact` |
| Target | `2**((e-1)/2) / sqrt(M)` on each segment, then the phase `1/sqrt(x)` |
| Precision | float64 Lawson (`numpy.linalg.lstsq`, `rcond=None`), then Python ints. Error is in units of `2^-24` |
| Domain | `x = 1..3133452`; segment `(e, a)` with `e` in {0, 1} and `a` in 0..127; `M` in [1, 2) |
| Objective | minimax relative error of the quadratic signed-digit Horner value. Lawson: 80 iterations, 3001-point grid, weight `sqrt(M)/scale`. Then an integer radius search |
| Rounding | Python `round` (half to even) for the K2 and K1 centres. Horner `rd` adds the bit under the kept field for a non-negative value. K0 is an integer argmin |
| Widths | `f2=8`, `f1=19`, `fyr=27`, `gy=1`, `drop2=(5,)` |
| Optimiser start | the rounded Lawson coefficient. Not an imported table |
| Determinism | no random seed. A second in-process fit must match. Drift fails closed on the row digest |
| Output | 256 `[K2, K1, K0]` triples, row-major `(e, a)`, JSON with separators `(',', ':')` |
| Row SHA-256 | `a36d1636d31d6b28a3bd5dce475bb3f8ef451b8b50deefc403853f184d4e6dcc`; different serialization, not the dataset file hash |

The committed recipe object is `RECIPE` in `fit_coefficients.py`.

## Code parents

| Work | Version | Licence | Role |
| --- | --- | --- | --- |
| Artem1410 (anazemcev / ViberTeam), "Quantum Circuits \| Signed-Digit Memory" | v3 = scriptVersionId 361502374 | Apache-2.0, declared by the v3 source itself (cell 5 `SPDX-License-Identifier: Apache-2.0`; cell 20 embeds the Apache-2.0 text and NOTICE). Kaggle's version licence field was not retrievable without credentials: open | Immediate parent of `signed_digit.py`. Snapshot SHA-256 `79f6373302cb916a88f65a1b142024d4d2d0b14e41eb58bef3152ebd45ffd0ca`, equal to the public version-pinned download (22 cells; public metadata `currentVersionNumber` 3, `isPrivate` false). Extraction differs only by the added docstring and the removed `cli()` call (PRA-218). URL https://www.kaggle.com/code/anazemcev/quantum-circuits-signed-digit-memory?scriptVersionId=361502374 |
| Kozykorpesh (kozykappa), "Quantum AI — Complete-Domain Affine Compilation" | v2 | Apache-2.0 | Method parent of `affine.py` and `peephole.py`. PRA-194 attachment SHA-256 `81befe1e69ee286271fa2eb8acf4bb760a727853bf966945318d918482b1ab24` |
| Artem1410 (anazemcev / ViberTeam), "Quantum Circuits \| Source & Exact Compilation" | v4 | Apache-2.0 | Davio orders and the measurement-uncompute rule. PRA-194 attachment SHA-256 `4f017407a40e0988583c9645662407046f04019357adac648b90b2b94598acdb` |
| Kozykorpesh (kozykappa), "Quantum AI LB score" | V3 run 361677445 | Apache-2.0, as stated by that lineage | Method parent of `schedule90.py`. URL https://www.kaggle.com/code/kozykappa/quantum-ai-lb-score-6-68108?scriptVersionId=361677445 |

## Credited, not loaded

These people are credited where their methods are used. The originals are not
inputs. Sumit v1 versus v2, and Gluzdov v6, stay second-hand until
[PRA-205](/PRA/issues/PRA-205) pins them.

| Person | What is credited | Version named by the notebooks | Licence on this record |
| --- | --- | --- | --- |
| Sumit Chongder | centered signed-digit generator and integer pipeline | run 361357149 **is v1** (public version metadata, PRA-218). The inherited "latest version 2" remark is corrected in `signed_digit.py` by D-PRA220-01 | second-hand; no licence declaration in that snapshot: open. Not loaded |
| Rudra Bhaskar | derivative split, top-carry reuse, static-high checkpoint | run 361445283 = v7 (public, PRA-218) | retained notice in the Apache-2.0 v3 parent; no publisher licence label retrieved: open. Not loaded |
| Alex Chilton | shared prefix flags and empty-target shifts | v8 reviewed by PRA-194; the run the parent cites, 361472684, is v3 (public, PRA-218) | **reference-only**. PRA-194 found no notebook-wide licence; PRA-218 found none on v3 either. Not loaded |
| Kirill Tymchishin | integration of the Rudra/Alex schedule | run 361491814 = v11 (public, PRA-218) | credited by the v3 parent; its cell 1 retains upstream Apache material, no licence field for its own integration: open. Not loaded |
| Kozykorpesh | widths `8,19,27,1`, Gray schedule, affine rewrite, peephole | V3 run 361677445; affine v2 | Apache-2.0 for the attached affine v2 and the stated V3 lineage |
| anazemcev / ViberTeam | signed-digit v3 body, v4 Davio orders, measurement uncompute | v3 and v4 | Apache-2.0 |
| Dmitrii Gluzdov | V6 boundary rule used by the 90-qubit schedule | v6, run 361592338 | second-hand. His notebook is not loaded. `femoco_public_words.npz` is not an input |
| LightningV08 and Mizero Lucky Gall | slack-maximising rotation drop | Mizero v1 | **reference-only**. PRA-194 found no notebook-wide licence. `calibrate.py` is our scipy linprog search, not a port of that notebook |

## Module map

Hashes are SHA-256 of the committed file bytes. "Copied material" is none:
these files are ports and new code, not verbatim notebook cells.

| Module | Source | Licence | Copied material | Modifications |
| --- | --- | --- | --- | --- |
| `signed_digit.py` | anazemcev Signed-Digit Memory v3; dataset domain-tables calibration | Apache-2.0 for the notebook parent; dataset-adapted calibration licence unresolved | none verbatim | Port of the quadratic signed-digit body, derivative split, borrowed carry, and promised-input rewrite. Coefficient integers come from the fit below. Retained upstream notices stay in the header. SHA-256 `ab08c1f178405cae9872281fbe73ca41c5de160bea4b5ddeece41b55ac708cd5` |
| `schedule90.py` | Kozykorpesh V3 run 361677445; Davio orders from anazemcev v4 | Apache-2.0 | none verbatim | Port. Gluzdov V6 is the named boundary rule only. SHA-256 `58c88937e18e2c96e5e92f3a2576b3d32661de0d93221d4f288e314bb4c81edb` |
| `affine.py` | Kozykorpesh affine v2 and anazemcev v4 | Apache-2.0 | none verbatim | Port of the exact-domain Toffoli/CSWAP rewrite. SHA-256 `aa351a287c507c264a8aa7d172e1c7b9bfc1d0dcb78c8fa61b92996947eba290` |
| `peephole.py` | Kozykorpesh affine v2 involution pass | Apache-2.0 | none verbatim | Port. SHA-256 `d5ed02b0d28392cc637111fc94fb1760c71feda4f8ca7aad6f73944e81fff54c` |
| `calibrate.py` | our scipy linprog search | Apache-2.0 (this repository) | none | Not a Mizero port. Method credit only. SHA-256 `7fc0c1cac6ff45753c25d98dfa7cd82fb4803332c37fb616af18fabe47cef309` |
| `fit_coefficients.py` | the mathematical target and dataset-adapted calibration in `RECIPE` | `regenerated; dataset-adapted calibration; licence unresolved` | none | The fit. SHA-256 `35d36f95aa4bb7c63bf8cd24d72df594abdd679a3ed770cb2fcced0200cda839` |
| `generate.py` | the modules above | port; coefficient provenance: `regenerated; dataset-adapted calibration; licence unresolved` | none | Entry point. Writes only `invsqrt.kmb`. SHA-256 `9ccdffd0cba53a097c78d99d833b9bcc37e9be387f62ed723a8173cd2cdf498c` |
| `reference.py` | Google's `verifiers/invsqrt/nr_reference_circuit.py` (competition package) | Apache-2.0 (Google) | the script, attributed | Port with `--out DIR`; builds the reference circuit shipped as submission-001, SHA-256 `e2bf8eb64350a4460a271fc7f1d591ef125b1e276377e9a0f64b96ab3ca321e1`. G5 generator for `configs/gates/reference.yaml` only (PRA-211). Not a parent of the candidate and not used by `generate.py` |
| `mirror.py` | the integer model | Apache-2.0 (this repository) | none | G2 certificate. SHA-256 `34fd6e2cd5806776eb881ac5890fd67fa6ed84dbdf8d3e76ab7c481788a1fc42` |
| `gates.py` | the ledger hook contract | Apache-2.0 (this repository) | none | G1/G2 hooks. Not a method parent. SHA-256 `d43b4e21cf1fa5aa7ae1519f6378a981538b769e3d54a2f6eb40b38f73d38265` |

## Public-source evidence (PRA-218, 2026-10-25)

Caine's packet ([PRA-218](/PRA/issues/PRA-218) `invsqrt-licence-evidence`, archive SHA-256
`38f162467df166c0294e00db8dd1beabfad03c6727cfad2182e229c75ed04fe8`) retrieved every source above
without credentials and pinned it by hash and UTC time. John Wick re-ran its verifier at `3404dff`
(eight PASS lines) and re-checked the facts below on `main` after PRA-216.

| Item (PRA-179 provenance review) | Closed with public evidence | Still open |
| --- | --- | --- |
| Immediate parent and attribution | v3 = 361502374, public, snapshot equal to the committed pin, Apache-2.0 declared in its own source, extraction diff recorded | Kaggle's version-specific licence field (public `GetKernelVersion` returns 403) |
| Transitive code | Sumit 361357149 = v1, Rudra 361445283 = v7, Alex 361472684 = v3, Kirill 361491814 = v11, Kozykorpesh 361456406 = v2 (slug now `quantum-ai-lb-score-6-68108`); all public, cell-level AST comparison recorded | a publisher licence declaration for each of the five versions |
| Numeric table and calibration dataset | `kozykappa/quantum-ai-dataset`, dataset id 12801707, datasetVersionId 21136269 = version 1, public; licence label **"Other (specified in description)"**; README: "New atlas tooling and derived numerical generation code: Apache-2.0"; `catalog/license_map.csv` does not name `code/coefficients.json` or `code/domain_tables.py` | file-specific rights for both files unresolved; affected candidate held (D-PRA220-01) |
| Public-source inventory | every listed source is anonymously retrievable today | historical absence of private sharing cannot be proved from present public access |

Finding recorded on PRA-211, now ruled by [D-PRA220-01](../../docs/decisions/D-PRA220-01.md):
the locally regenerated fit reproduces the dataset table 256 of 256 rows, and the calibration
is adapted from its domain-tables module (version and file hashes above). The
[Adjudicator verdict](/PRA/issues/PRA-220#document-adjudicator-verdict), revision
`a70476a7-9756-406e-abdb-f7985a26c96e`, supersedes D-PRA200-01's `own` and
licence-closure conclusion and resolves D-PRA211-04(b) as **unresolved rights; affected candidate held**.
No Kaggle upload of a zip whose `invsqrt.kmb` comes from `tasks/invsqrt/generate.py`'s current coefficient lineage until the Adjudicator accepts file-specific rights evidence for both files ([PRA-222](/PRA/issues/PRA-222)) or clears an independently implemented replacement ([PRA-223](/PRA/issues/PRA-223)). Ledger enforcement is [PRA-224](/PRA/issues/PRA-224); this correction records the hold and does not implement it.
Historical decisions and manifests remain unchanged.

## Forbidden inputs (not loaded)

These names are not opens, warm starts, or test oracles in `tasks/invsqrt` Python:

- `code/coefficients.json` (Kaggle dataset version 21136269)
- toolbox `fusion/*.npz`
- `selected/invsqrt.kmb`
- any `.npz` load

A recorded SHA-256 of a circuit we generated is not a load of that file.


## Public source experiment (PRA-249)

Immediate parent: Dmitrii Gluzdov, *Quantum circuit compilation from source*,
v7 / `361726742`, [version-pinned notebook](https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361726742).
Notebook SHA-256 `d689cc89f41a6c9130e9f4c3a6b08dfd5d758fcbbb79f527d55cbd3b48e15280`;
Apache-2.0 declaration in cell 50. This is a source port, not clean-room authorship.
The source packet is attached to [PRA-249](/PRA/issues/PRA-249#document-invsqrt-source-route).

| Module under `public_port/` | Source and changes | Data inputs |
| --- | --- | --- |
| `model.py` | Centered integer pipeline, cells 22/29; pure numpy/torch interface and independent exhaustive integer certificate | mathematical target only |
| `fit.py` | Cell 22 base/slope enumeration plus cell 34 even anchors; CUDA int64/float64, deterministic adaptive subdivision of groups above 0.95 error | none; no saved coefficient table |
| `arithmetic.py` | Cell 23 `prepare` and `shift`; reuse existing signed-digit arithmetic helpers | regenerated triples |
| `deferred.py` | Cell 20 demolition and ANF repair | regenerated lookup truth tables |
| `virtual_low.py` | Cell 40 virtual low accumulator bit, credited to Zongao Bian | circuit registers |
| `schedule.py` | Cell 42 virtual time multiplexing; package imports, no setup/environment changes or notebook driver | regenerated triples and interpolation encoding |
| `calibration.py` | Repository angle fitter with CUDA full-domain constraint evaluation and host HiGHS cutting planes; bounded to original angles and smallest single drop | newly compiled truth vectors; no angle replay |
| `generate.py` | New entry point; recomputes G2 before importing kickmix, then existing affine compiler and new GPU calibration | none; optional output directory only |

The generic circuit helpers imported from `signed_digit.py` do not call its
coefficient fitter or load its coefficient lineage. All new triples come from
the published v7 recipe and the mathematical target. `affine.py` and
`peephole.py` retain their existing parents and licences described above.
No source cell containing stored tables, calibration values, exact rewrite
patches, packaged circuits or chemistry data is executed or adopted. The
busyaprime binary-parent option was not selected by the board. The fallback
`tasks/invsqrt/generate.py` remains the submission generator unless a separate
candidate passes the required floor and gates.

## PRA-285 storage study

`public_port/storage.py` implements idle-wire parking from the method described
by [mrmeows, qcc-1375-open-circuits v6](https://www.kaggle.com/datasets/mrmeows/qcc-1375-open-circuits/versions/6):
README invsqrt items 1–8 and `source/invsqrt_63q/README.txt` stages 23–27.
The published Apache-2.0 attribution is recorded here; no new licence check
was used as a gate. The prior Gluzdov/DePie/busyaprime lineage remains credited.
The prose and the source files `phase/deferred_carries.py`,
`qubit/optimize_memory.py`, and `qubit/complete_cap77.py` were read as reference.
No source file is executed or imported, and no frozen circuit, certificate,
proof, seed, coefficient, or angle from that dataset is loaded.

This implementation searches for affine or single-product recovery identities
against the port's regenerated truth vectors. Every accepted identity is
checked on the entire legal input domain, including at its restoration point.
The port's coefficient fitter, integer model, and rotation calibration are
unchanged. This is a storage experiment, not a shipping approval.

Reference hashes: README.txt `458598e9189e4e5da87933f9f0623814fd119b5d9be22d3afad0b146a0723eb0`;
deferred_carries.py `9e13167b71fee5dbe14f1a603f94a2d34bd8b2c575040354f738e9e1d7c6c971`;
optimize_memory.py `d9f68c987a6f9b07a2c33cc5caf08d92eef01f9308a30ecae0a1b65ea6d8ef9a`.
