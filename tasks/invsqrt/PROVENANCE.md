# invsqrt generator provenance

This generator is a **port**. It is not independent clean-room authorship.
Only the coefficient fit is labeled `own`. Nothing in this map is a shipment.
A ledger candidate still needs G0–G5, the full-shot verifier, and a
candidate-specific Adjudicator sign-off (D-PRA202-05). Historical P0 rows
stay unchanged.

## Coefficient fit (`own`)

| Field | Value |
| --- | --- |
| Module | `tasks/invsqrt/fit_coefficients.py` |
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
| Row SHA-256 | `a36d1636d31d6b28a3bd5dce475bb3f8ef451b8b50deefc403853f184d4e6dcc` |

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
| Sumit Chongder | centered signed-digit generator and integer pipeline | run 361357149 **is v1** (public version metadata, PRA-218). The inherited "latest version 2" remark in the `signed_digit.py` header comments is unsupported; this map supersedes it, and the comment is corrected with the next change to that pinned file | second-hand; no licence declaration in that snapshot: open. Not loaded |
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
| `signed_digit.py` | anazemcev Signed-Digit Memory v3 | Apache-2.0 | none verbatim | Port of the quadratic signed-digit body, derivative split, borrowed carry, and promised-input rewrite. Coefficient integers come from the fit below. Retained upstream notices stay in the header. SHA-256 `f106ea0a6f3a5d37d3e44cbe79d8f2f4777c86636d52ee9888ede09595db0c72` |
| `schedule90.py` | Kozykorpesh V3 run 361677445; Davio orders from anazemcev v4 | Apache-2.0 | none verbatim | Port. Gluzdov V6 is the named boundary rule only. SHA-256 `48adbc9ae7adb0e40f0290ef8d0b5ecb467c510288c887bb1324cca856439f2d` |
| `affine.py` | Kozykorpesh affine v2 and anazemcev v4 | Apache-2.0 | none verbatim | Port of the exact-domain Toffoli/CSWAP rewrite. SHA-256 `aa351a287c507c264a8aa7d172e1c7b9bfc1d0dcb78c8fa61b92996947eba290` |
| `peephole.py` | Kozykorpesh affine v2 involution pass | Apache-2.0 | none verbatim | Port. SHA-256 `d5ed02b0d28392cc637111fc94fb1760c71feda4f8ca7aad6f73944e81fff54c` |
| `calibrate.py` | our scipy linprog search | Apache-2.0 (this repository) | none | Not a Mizero port. Method credit only. SHA-256 `7fc0c1cac6ff45753c25d98dfa7cd82fb4803332c37fb616af18fabe47cef309` |
| `fit_coefficients.py` | the mathematical target and `RECIPE` | `own` | none | The fit. SHA-256 `1e97f77e6d3498e8dde2fe9312bfbf5c505c62e5c68938c846e0c8fc0d39aba3` |
| `generate.py` | the modules above | port, with an `own` table | none | Entry point. Writes only `invsqrt.kmb`. SHA-256 `c6248e89382cacd193123da35188c63b9b5e7cf390b1182eccdb588c171a14a1` |
| `reference.py` | Google's `verifiers/invsqrt/nr_reference_circuit.py` (competition package) | Apache-2.0 (Google) | the script, attributed | Port with `--out DIR`; builds the reference circuit shipped as submission-001, SHA-256 `e2bf8eb64350a4460a271fc7f1d591ef125b1e276377e9a0f64b96ab3ca321e1`. G5 generator for `configs/gates/reference.yaml` only (PRA-211). Not a parent of the candidate and not used by `generate.py` |
| `mirror.py` | the integer model | Apache-2.0 (this repository) | none | G2 certificate. SHA-256 `44f9928fe54f84c45977e9cfe637e7ad2068ab7cda7dd9fb2949a6666cd1513d` |
| `gates.py` | the ledger hook contract | Apache-2.0 (this repository) | none | G1/G2 hooks. Not a method parent. SHA-256 `3f569d70c97f3c41f7b627050e7a40494d54c546da196788c1bc08f55162890d` |

## Public-source evidence (PRA-218, 2026-10-25)

Caine's packet ([PRA-218](/PRA/issues/PRA-218) `invsqrt-licence-evidence`, archive SHA-256
`38f162467df166c0294e00db8dd1beabfad03c6727cfad2182e229c75ed04fe8`) retrieved every source above
without credentials and pinned it by hash and UTC time. John Wick re-ran its verifier at `3404dff`
(eight PASS lines) and re-checked the facts below on `main` after PRA-216.

| Item (PRA-179 provenance review) | Closed with public evidence | Still open |
| --- | --- | --- |
| Immediate parent and attribution | v3 = 361502374, public, snapshot equal to the committed pin, Apache-2.0 declared in its own source, extraction diff recorded | Kaggle's version-specific licence field (public `GetKernelVersion` returns 403) |
| Transitive code | Sumit 361357149 = v1, Rudra 361445283 = v7, Alex 361472684 = v3, Kirill 361491814 = v11, Kozykorpesh 361456406 = v2 (slug now `quantum-ai-lb-score-6-68108`); all public, cell-level AST comparison recorded | a publisher licence declaration for each of the five versions |
| Numeric table and calibration dataset | `kozykappa/quantum-ai-dataset`, dataset id 12801707, datasetVersionId 21136269 = version 1, public; licence label **"Other (specified in description)"**; README: "New atlas tooling and derived numerical generation code: Apache-2.0"; `catalog/license_map.csv` does not name `code/coefficients.json` or `code/domain_tables.py` | whether those terms cover the table and `domain_tables.py` |
| Public-source inventory | every listed source is anonymously retrievable today | historical absence of private sharing cannot be proved from present public access |

Finding recorded on PRA-211: the `own` fit (`fit_coefficients.py`, D-PRA200-01) reproduces the
dataset's `code/coefficients.json` (SHA-256 `98bd211f22b158bf05a4d2d934ab966e5e97e54d8307b82e2ca58910c6830763`)
exactly, 256 of 256 rows in order, and the calibration it runs (`valid_residuals`,
`calibrate_segment`, `regenerate_tables_exact`) is adapted from the dataset's `code/domain_tables.py`
(SHA-256 `59cf4d98899433dcc49d9ce512293be20d33da5334211c20e35323555994a4fb`). Whether `own` is the
right label for a table that equals the dataset's is a board and Adjudicator call (D-PRA211-04); it
is not changed here.

## Forbidden inputs (not loaded)

These names are not opens, warm starts, or test oracles in `tasks/invsqrt` Python:

- `code/coefficients.json` (Kaggle dataset version 21136269)
- toolbox `fusion/*.npz`
- `selected/invsqrt.kmb`
- any `.npz` load

A recorded SHA-256 of a circuit we generated is not a load of that file.
