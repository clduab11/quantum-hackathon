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
| Artem1410 (anazemcev / ViberTeam), "Quantum Circuits \| Signed-Digit Memory" | v3 | Apache-2.0 | Immediate parent of `signed_digit.py`. Snapshot SHA-256 `79f6373302cb916a88f65a1b142024d4d2d0b14e41eb58bef3152ebd45ffd0ca`. URL https://www.kaggle.com/code/anazemcev/quantum-circuits-signed-digit-memory |
| Kozykorpesh (kozykappa), "Quantum AI — Complete-Domain Affine Compilation" | v2 | Apache-2.0 | Method parent of `affine.py` and `peephole.py`. PRA-194 attachment SHA-256 `81befe1e69ee286271fa2eb8acf4bb760a727853bf966945318d918482b1ab24` |
| Artem1410 (anazemcev / ViberTeam), "Quantum Circuits \| Source & Exact Compilation" | v4 | Apache-2.0 | Davio orders and the measurement-uncompute rule. PRA-194 attachment SHA-256 `4f017407a40e0988583c9645662407046f04019357adac648b90b2b94598acdb` |
| Kozykorpesh (kozykappa), "Quantum AI LB score" | V3 run 361677445 | Apache-2.0, as stated by that lineage | Method parent of `schedule90.py`. URL https://www.kaggle.com/code/kozykappa/quantum-ai-lb-score-6-68108?scriptVersionId=361677445 |

## Credited, not loaded

These people are credited where their methods are used. The originals are not
inputs. Sumit v1 versus v2, and Gluzdov v6, stay second-hand until
[PRA-205](/PRA/issues/PRA-205) pins them.

| Person | What is credited | Version named by the notebooks | Licence on this record |
| --- | --- | --- | --- |
| Sumit Chongder | centered signed-digit generator and integer pipeline | v2 cited by Kozykorpesh; run 361357149 cited as v1 | second-hand. Not loaded |
| Rudra Bhaskar | derivative split, top-carry reuse, static-high checkpoint | run 361445283 | retained notice in the Apache-2.0 v3 parent. Not loaded |
| Alex Chilton | shared prefix flags and empty-target shifts | v8 | **reference-only**. PRA-194 found no notebook-wide licence. Not loaded |
| Kirill Tymchishin | integration of the Rudra/Alex schedule | run 361491814 | credited by the v3 parent. Not loaded |
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
| `mirror.py` | the integer model | Apache-2.0 (this repository) | none | G2 certificate. SHA-256 `44f9928fe54f84c45977e9cfe637e7ad2068ab7cda7dd9fb2949a6666cd1513d` |
| `gates.py` | the ledger hook contract | Apache-2.0 (this repository) | none | G1/G2 hooks. Not a method parent. SHA-256 `3f569d70c97f3c41f7b627050e7a40494d54c546da196788c1bc08f55162890d` |

## Forbidden inputs (not loaded)

These names are not opens, warm starts, or test oracles in `tasks/invsqrt` Python:

- `code/coefficients.json` (Kaggle dataset version 21136269)
- toolbox `fusion/*.npz`
- `selected/invsqrt.kmb`
- any `.npz` load

A recorded SHA-256 of a circuit we generated is not a load of that file.
