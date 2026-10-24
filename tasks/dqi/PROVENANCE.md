# DQI decoder provenance

This generator is a **port**. It is not an independent clean-room authorship.
Nothing in this map is a shipment. The three-salt verifier has been run
(D-PRA197-10). A ledger candidate still needs a clean-worktree G5 rebuild
from a commit on GitHub, the PRA-203 re-check, and the PRA-204 sign-off
(D-PRA202-05).

Zenodo record 17301475 (DOI 10.5281/zenodo.17301475) is **not** an input.
No CC-BY-4.0 attribution record is required for it on this generator.

## Transitive code parent

| Field | Value |
| --- | --- |
| Work | `andigu/uncompute` |
| URL | https://github.com/andigu/uncompute |
| Commit | `64b5a13aa249f1360846657392e6c66817b26d0f` (`tasks/dqi/bm_forney/UPSTREAM_COMMIT.txt`) |
| Licence | Apache-2.0. Verbatim `LICENSE` copied to `tasks/dqi/bm_forney/LICENSE`, SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| Authors | Andi Gu, Alek H. Kemeny, Susanne F. Yelin, Mikhail D. Lukin (`pyproject.toml` `authors`) |
| NOTICE | The repository has no NOTICE file. No copyright year is stated. None is added. |
| Paper | Bibliographic citation only: Gu, Kemeny, Yelin, and Lukin, arXiv:2610.22367. No paper prose. No figures (`profile.pdf` is not copied). |

### Used upstream paths

| Upstream path | What was taken | Upstream SHA-256 |
| --- | --- | --- |
| `LICENSE` | verbatim | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `uncompute/classical.py` | verbatim → `gu_classical.py` | `c05c9e7a84a69e3ad0590b972642dcb30c2c29ca2613a821c82d09d53556ba62` |
| `uncompute/gadgets/linear.py` | verbatim → `gu_linear.py` | `d0b89d494ae63ec28e8bac6f33b344c11aaaab378d0cec81683b1a5743ed25d3` |
| `tasks/dqi-reed-solomon/contract.json` | same object, `gf_poly` 4331 → 4179 | `c2a257b333527bf8dabde3a3d2ec0464f0a3439efac9f1e8d2811659bc3bcf42` |
| `tasks/dqi-reed-solomon/circuits/discovered/constants.json` | keys `bm_windows` and `psi_windows` only | `b5e93915f5636cf084456e2ede7cad3f195ddc869c4a4c9942aa98b8a58cc12e` |
| `tasks/dqi-reed-solomon/circuits/discovered/circuit.py` | reached here through the notebook embed below | `d5f7dd55915e3426ab87ec75da5b76a37123cb996cd750f46ecd74be17a5ec30` |
| `tasks/dqi-reed-solomon/circuits/discovered/gen_constants.py` | formula section only, through the notebook embed | `7e211d060edd242c54f5a34447edde4ae08eb8fda9111b37b1886db126abcee3` |

Not used from that commit: `search.c`, `README.md`, `profile.pdf`, `circuit.ops.xz`, `liveness.json`, `meta.json`, `grader.py`, `reference.py`, and every other task directory.

`bm_windows` and `psi_windows` in `windows.json` match those two objects in the upstream `constants.json`. The multiplication tables (`KT12`, `KT6`, `KT3`, `CUBE3Q`, `PAIR3`, `LIN`) are not copied. `gu_formula_derivation.py` regenerates them for modulus 4179 on every run.

## Immediate code parent

The kickmix schedule is the `src/gen_dqi_v6` tree embedded by `%%writefile` cells.
Those cells are byte-identical in both notebooks:

| Notebook | Version | URL | Attachment SHA-256 |
| --- | --- | --- | --- |
| Artem1410 (anazemcev / ViberTeam), "Quantum Circuits \| Source & Exact Compilation" | 4 | https://www.kaggle.com/code/anazemcev/quantum-circuits-source-exact-compilation | `4f017407a40e0988583c9645662407046f04019357adac648b90b2b94598acdb` |
| Kozykorpesh (kozykappa), "Quantum AI — Complete-Domain Affine Compilation" | 2 | https://www.kaggle.com/code/kozykappa/quantum-ai-complete-domain-affine-compilation | `81befe1e69ee286271fa2eb8acf4bb760a727853bf966945318d918482b1ab24` |

Both state Apache-2.0. PRA-194 read the sources. The anazemcev v4 markdown is the base of that embed. Kozykorpesh v2 carries the same decoder bytes. The shipped loan is that embed's affine route (`DQI_BORROW=affine`).

Dmitrii Gluzdov's V6 memory schedule is the schedule those notebooks name. His notebook is not vendored. `femoco_public_words.npz` is not an input (D-PRA202-03).

## Module map

"Copied material" is the notebook `%%writefile` body. "Trailing newline" means the committed file is that body plus one final newline. Hashes are of the committed bytes.

| Module | Immediate source | Transitive source | Licence | Copied material | Modifications |
| --- | --- | --- | --- | --- | --- |
| `bm_forney/gu_classical.py` | notebook `ref/gu_classical.py` | `uncompute/classical.py` | Apache-2.0 | verbatim upstream, trailing newline | none. SHA-256 `c05c9e7a84a69e3ad0590b972642dcb30c2c29ca2613a821c82d09d53556ba62` |
| `bm_forney/gu_linear.py` | notebook `ref/gu_linear.py` | `uncompute/gadgets/linear.py` | Apache-2.0 | verbatim upstream, trailing newline | none. SHA-256 `d0b89d494ae63ec28e8bac6f33b344c11aaaab378d0cec81683b1a5743ed25d3` |
| `bm_forney/gu_port.py` | notebook `gu_port.py` | `discovered/circuit.py` | Apache-2.0 | notebook body, trailing newline | none relative to the notebook. The notebook already changed imports, the constants path, `final_bb_l`, the empty fixed-mask Z loop, and the borrow hook. SHA-256 `93a753e54e0ae28e0ca37a168f0c4e8a740f6e1ab82ff7106b1fdd24bb487250`. Its header mentions `REPORT.md` and `ref/gu_README.md`; those files are not in this tree. |
| `bm_forney/gu_formula_derivation.py` | notebook `gu_formula_derivation.py` | `discovered/gen_constants.py` formula section | Apache-2.0 | notebook body, trailing newline | none relative to the notebook. The window census (`search.c` and the Psi search) is not in this file. SHA-256 `d55e238aa5c7ccb26b0d5cea8fdb911ecbb4ae54782df3e50950140164204dbb` |
| `bm_forney/round2_gadgets.py` | notebook `round2_gadgets.py` | Gu algebra, schedule text in the notebook | Apache-2.0 | notebook body, trailing newline | none. SHA-256 `76dd907a2f19f16c38c49f6a631909cdb732d17fc7809d3797bb7c08e67c5645`. The sentence "developed in this workspace (OpenAI Codex, 2026-10-23)" is the notebook's own notice. It is not a Praxen authorship claim. |
| `bm_forney/symbolic_runtime.py` | notebook `symbolic_runtime.py` | kickmix adapter in the same embed; schedule credited to Gluzdov V6 by the notebook | Apache-2.0 | notebook body, identical including newline | none. SHA-256 `f25047e0138bfe75cf177afd6d50e7694d047ed8cacf26ac83b7eaa6224058a4` |
| `bm_forney/port_runtime.py` | notebook `port_runtime.py` | Gu `Builder` / `Journal` behaviour, reimplemented against kickmix in the notebook | Apache-2.0 | notebook adapter | **Modified.** Import paths point at `gu_classical`, `gu_linear`, and `contract.json`. `load_contract` stops unless `kickmix.GF2Field(12)` has modulus 4179 and primitive element 2. SHA-256 `cbfc4562cd110bce7f3d214ec179e02ec00e1165446504be28c0c3e44fbdf293` |
| `bm_forney/borrow.py` | `borrow_template` in notebook `run_gu_port.py` | same embed | Apache-2.0 | affine branch of that function | **Modified extract.** Names were expanded. The notebook trie route is not copied. The loan stays an approximate support claim. SHA-256 `8fd2f83cc831d9d60b6a13d75e0a36dd5ed9033dfe9d8b5ec0ee899780cdfe39` |
| `bm_forney/contract.json` | notebook `ref/gu_contract.json` | Gu `contract.json` | Apache-2.0 | Gu contract object | **Modified data.** `gf_poly` is 4179, not 4331. Every other parsed field matches the Gu file. SHA-256 `b5fa02899021142b7f265f1e18f366b0d6f55944023b3cf249f976c655d2097e` |
| `bm_forney/windows.json` | the two window keys of notebook `ref/gu_constants.json` | Gu `constants.json` | Apache-2.0 | `bm_windows`, `psi_windows` | **Extract, not a rewrite.** Formula tables are omitted so they cannot be loaded. SHA-256 `a5dff27decbf564d6b810ece4dd345099eac5e4ba3d8260dcbf263f22dc9da99` |
| `bm_forney/LICENSE` | notebook `ref/GU_LICENSE` | Gu `LICENSE` | Apache-2.0 | verbatim | none |
| `bm_forney/UPSTREAM_COMMIT.txt` | notebook `ref/GU_COMMIT.txt` | the commit above | Apache-2.0 | the 40-hex commit and a newline | none |
| `generate.py` | replaces notebook `run_gu_port.py` / `dqi_driver.py` | the modules above | Apache-2.0 | driver written for the `--out` contract | Sets `DQI_BORROW=affine`, regenerates tables, merges `windows.json`, and patches the streamed sweep so the symbolic builder forgets those wires. Does not read a `.kmb` or a `.npz`. |
| `algebra.py`, `gates.py` | none | competition field and the G1/G2 hook contract | Apache-2.0 | new | Checks and gate hooks. Not decoder parents. |
| `reference_circuit.py` | competition package `verifiers/dqi/dqi_reference_circuit.py` | Google Quantum AI, Apache-2.0 | Apache-2.0 | the 1.0 reference decoder | Kept beside the port. It is not the shipped BM generator. |

`run_gu_port.py` itself is not committed. Only its affine `borrow_template` was extracted.
The notebook `dqi_driver.py` is not committed.

## Forbidden parents (not inputs)

These names do not appear as loads in `tasks/dqi` Python or JSON:

- `selected/dqi.kmb`
- `source/decoder_input.kmb`
- toolbox `dqi/*.npz`
- `femoco_public_words.npz`
- `dfthc_group_32_60_30.npz`

## Two local builds, same bytes (not a candidate)

Both runs used `uv run python tasks/dqi/generate.py --out DIR` with `OMP_NUM_THREADS=1`. Neither read a `.kmb` or a `.npz`. The second run was after commit `c94611c` (the provenance commit). The circuit bytes matched.

| Run | Output (not committed) | Size | SHA-256 | Q | Static Toffoli-like | Build |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `/tmp/pra197/out/dqi.kmb` | 823,297,489 | `529b075009f7758abeda83a63407f0c1feeb51dd70631ae4335dfd28721b7e08` | 1789 | 445229 | 156.5 s |
| 2 | `/tmp/pra197/out-g5b/dqi.kmb` | 823,297,489 | `529b075009f7758abeda83a63407f0c1feeb51dd70631ae4335dfd28721b7e08` | 1789 | 445229 | 143.2 s |
| 3 | `/tmp/pra197/out/dqi.kmb` (rebuilt 2026-10-24, same path) | 823,297,489 | `529b075009f7758abeda83a63407f0c1feeb51dd70631ae4335dfd28721b7e08` | 1789 | 445229 | 143.2 s |

Operations in each log: 93,898,574. Field: modulus 4179, primitive element 2.

PRA-194 records that same byte size for the anazemcev v4 `dqi.kmb` output. This tree did not read that file. Equal size is not a claim that the two files are the public artifact.

## Three public salts (not a ledger G3)

`/tmp/pra197/three-salt.jsonl` is the full verifier on the run-3 file. 102,400 shots, 4 workers. The circuit SHA-256 is the hash above. Value errors are 0 on every salt. Executed Toffolis are 445229.0, equal to the static count.

| Salt | Phase errors | epsilon+ | R | Ratio vs reference dqi |
| --- | ---: | ---: | ---: | ---: |
| `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001` | 3 | 0.000983909102617945 | 1.2055843238398525 | 14.22623531711937 |
| `PRA171_LOCAL_PUBLIC_FIXED_SALT_0002` | 4 | 0.001016763883917165 | 1.209464049815962 | 14.18060031481362 |
| `PRA171_LOCAL_PUBLIC_FIXED_SALT_0003` | 8 | 0.0011344950381555927 | 1.2230139975925918 | 14.02349140675107 |

Reference dqi cost used for the ratio: 24439465632206.816. Salt 0001 is the ledger G3 salt. Salts 0002 and 0003 are the diagnostic labels. They were not used to choose a circuit. This file is not a ledger candidate.

## Clean worktree rebuild of the dqi file

`ledger.benchmark_health.rebuild_in_clean_worktree` checked out commit `e1842978a78a485a1ae8c7fb9803c27a08dbbd2d` into a fresh worktree and ran `tasks/dqi/generate.py`. The output `dqi.kmb` matched SHA-256 `529b075009f7758abeda83a63407f0c1feeb51dd70631ae4335dfd28721b7e08`. Diffs: none. This is the dqi half of the G5 check. It is not a ledger G5: there is no submission zip, invsqrt and dfthcsos were not rebuilt, and this commit is not on GitHub. `git push` cannot authenticate here. The configured helper path does not exist, SSH public-key auth is denied, and the GitHub connection cannot publish an existing commit.
