# Provenance and licence record: syed3000 `vqcc-own-circuit-portfolio` v12

Hermes-authored record under D-HERMES-20261112-02. It replaces the retired Adjudicator licence-record
ticket that D-PRA341-01 required for a `vendored_circuit`. `licence_record` in
`configs/gates/hermes-syed-v12.yaml` points at this file.

## What this record is, and is not

- It records what the published files say, which exact bytes were pinned, and what Chris approved.
- It is **not** a legal opinion and it does **not** certify who authored the circuits or how they were made.
- The statements about authorship, originality and measured results below are **author-claimed**: they
  come from the dataset's own `README.md` and `NOTICE` files. Nobody here has independently confirmed them.
  The repository did not run the builders, and no circuit was loaded or verified when this record was written.
- This is a vendoring route (D-PRA341-01 / D-HERMES-20261112-02), not an own-generator claim (R10's own-generator
  requirement is not met by this candidate). `tasks/public_portfolio/generate.py` only copies pinned bytes.

## Source

| Field | Value |
|---|---|
| Dataset | `syed3000/vqcc-own-circuit-portfolio`, version **12** |
| URL | https://www.kaggle.com/datasets/syed3000/vqcc-own-circuit-portfolio/versions/12 |
| Licence label | Apache-2.0 (`LICENSE` in the dataset, SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`) |
| Copyright line | "Copyright 2026 Syed Asad Ali. Licensed under Apache-2.0." (dataset `README.md` and `NOTICE`) |
| Dataset `README.md` SHA-256 | `f705cd243e22775f128ac4761cd3c3a49b8ae0400ef416f765964bc282635c6e` |
| Dataset `SHA256SUMS` SHA-256 | `0324a756234ec6f0900b31543267618410f888ed7fb1a5d32c4eaf5885f25964` |
| `SHA256SUMS` entries | 23, every one checked against the extracted files by the parent session (an earlier child note that said 24 was wrong) |
| Local copy | `C:/Users/cld-main/Desktop/ops/quantum-hackathon-phase0-data/public-frontier/dataset/extracted` (not in the repository) |
| Stage path | `inputs/syed3000/vqcc-own-circuit-portfolio-v12/<dataset file>` beneath `VQCC_DATA` |

The licence hash is the hash of the standard Apache-2.0 text. The same hash already appears elsewhere in this
repository for other Apache-2.0 sources, so it identifies the licence text, not the licensor. The copyright holder
is known only from the dataset's own statements.

## Author attribution (from the dataset, as published)

- Copyright 2026 **Syed Asad Ali**. The README asks that anyone building on the work "credit the lineage starting from Syed Asad Ali".
- README credits: "Syed Asad Ali, working with a team of AI agents (GPT-6 Astra Pro, Gemini 4 Argon, Fable 5.2,
  Mythos 5.2 and Opus 5.5), with Claude Science supporting the research." Those names are reproduced from the source, not verified.
- README claim, author-claimed and not certified: "This is our 100% original setup ... All three circuits are produced by builders we wrote
  ourselves, and nothing in them is taken from any public code."
- The three builder archives (`invsqrt_source_zip`, `dqi_source_zip`, `dfthcsos_source_zip`) each carry the same Apache `LICENSE`
  and the same two-line `NOTICE` (SHA-256 `3e0eea3a45192471eb7d3f9ceb8f47c070d45a9e46ee6553ccd60ed17f8bfa13`). They are
  **not** staged, imported or committed (about 12 MB zipped).
- A string search of the text-sized members of those three archives (members over 3 MB were skipped, including a 32 MB
  `cases.json` in the dqi archive) found no occurrence of `jday96314`, `k256`, `Schur`, `mrmeows`, `Gluzdov`, `anazemcev`, `kozykappa`,
  `Chilton`, `SomeJoint` or `busyaprime`. That is a limited negative check. It is not a lineage audit and it cannot show that the
  circuits have no public ancestry.

## What is pinned

Seventeen circuits are declared inputs of kind `vendored_circuit`. The one dfthcsos factor archive is a declared non-circuit
package input that may ship as a recorded copy (D-PRA211-05). Hashes were read from `SHA256SUMS` and re-hashed on disk.

| Dataset file | Task | Output path | Kind | Bytes | SHA-256 |
|---|---|---|---|---:|---|
| `invsqrt.kmb` | invsqrt | `invsqrt.kmb` | vendored_circuit | 291,626 | `321aff83636214196daa9cbc9dcc9c5e12a155bcff8d9989e98b8cee40935177` |
| `dqi.kmb` | dqi | `dqi.kmb` | vendored_circuit | 455,590,024 | `7cbe8ecf6f6e9743529b574f019504bb1712ce06fbb570c719ce9d9e2c914cd9` |
| `dfthcsos__angle_k_0.kmb` | dfthcsos | `dfthcsos/angle_k_0.kmb` | vendored_circuit | 407,750 | `ce7ebaf342c5b49f7d539637359fb8a282718fb3057e7b25dd193f2a6a4b8974` |
| `dfthcsos__angle_k_1.kmb` | dfthcsos | `dfthcsos/angle_k_1.kmb` | vendored_circuit | 420,156 | `3eac70665f021b0e304106fd62749277d4d69db775df008aacd6d950e4934193` |
| `dfthcsos__angle_k_2.kmb` | dfthcsos | `dfthcsos/angle_k_2.kmb` | vendored_circuit | 421,220 | `c3e1454e29a05c3c28bcfd16c2aee02340b5d439d9466774424fedf0ed7601d1` |
| `dfthcsos__angle_k_3.kmb` | dfthcsos | `dfthcsos/angle_k_3.kmb` | vendored_circuit | 415,439 | `d26b576ae789b0471ec6c11b7317c7c69eb3d7190472af8120ccf25cf217a8ea` |
| `dfthcsos__angle_k_4.kmb` | dfthcsos | `dfthcsos/angle_k_4.kmb` | vendored_circuit | 366,414 | `2efacc9d944aa5a855acf780e6bbc3c07af16c0275eb9549bb24adc70acca344` |
| `dfthcsos__angle_k_5.kmb` | dfthcsos | `dfthcsos/angle_k_5.kmb` | vendored_circuit | 364,423 | `7e4ed9a363c8f56d85410185c7b4449211788bc61e81b3dc7cbdd10ab7ce8a42` |
| `dfthcsos__angle_k_6.kmb` | dfthcsos | `dfthcsos/angle_k_6.kmb` | vendored_circuit | 367,137 | `26ab1d5df8132bbc28e068a4eef0b247ea21a96fa4034f89a6d1bf306f07e284` |
| `dfthcsos__angle_k_7.kmb` | dfthcsos | `dfthcsos/angle_k_7.kmb` | vendored_circuit | 372,920 | `1ae98642315e7aaedfde99773af4ae48198bf8b4f2e11e97883d6aa1bfe12bee` |
| `dfthcsos__angle_k_8.kmb` | dfthcsos | `dfthcsos/angle_k_8.kmb` | vendored_circuit | 353,772 | `e69c554c360c709e52126a6f773afeaa3564da7be0927d6293665f342203771f` |
| `dfthcsos__angle_k_9.kmb` | dfthcsos | `dfthcsos/angle_k_9.kmb` | vendored_circuit | 359,601 | `38848ce19bd553e4007a454d9b7d392d05ac105cf4b269f41521bd1003bf838e` |
| `dfthcsos__angle_k_10.kmb` | dfthcsos | `dfthcsos/angle_k_10.kmb` | vendored_circuit | 360,179 | `fdb67807154e35d9f41471c22b38bbc3ed07e5c93efef30a57f0599fb8400ff7` |
| `dfthcsos__angle_k_11.kmb` | dfthcsos | `dfthcsos/angle_k_11.kmb` | vendored_circuit | 360,339 | `d22baf8e2d294165618bcee40d958ef2806f0b35352c8b92e0d201aff3269c37` |
| `dfthcsos__angle_k_12.kmb` | dfthcsos | `dfthcsos/angle_k_12.kmb` | vendored_circuit | 359,705 | `b1b6af502f4bf02e521ab888600f645aa5a5bed028290466b54a835423eb2517` |
| `dfthcsos__angle_k_13.kmb` | dfthcsos | `dfthcsos/angle_k_13.kmb` | vendored_circuit | 359,237 | `1843d7993215656e4e0eee69169966ba269d544bc0b90e855e4ed5e6e113accc` |
| `dfthcsos__angle_k_14.kmb` | dfthcsos | `dfthcsos/angle_k_14.kmb` | vendored_circuit | 361,106 | `b763f0cd2fdeaaa31e7811084e51fde5d51575b036fa22854fb28172c1712a8e` |
| `dfthcsos__submission.npz` | dfthcsos | `dfthcsos/submission.npz` | package_input | 1,847,692 | `6418ec8e10b1a8da967ee26278434f9ac950474741185f4d61363e17a03da77f` |

The dataset files `LICENSE`, `README.md`, `SHA256SUMS` and the three source archives are not staged and not shipped.

## Approvals and rules applied

- D-PRA341-01: a `vendored_circuit` must be Apache-2.0 (or another accepted licence), pinned by URL, version and SHA-256, and
  G5 passes it only when the shipped file is byte-identical to the pin. The k256.dev dqi artifact stays banned and reference-only. Nothing here uses it.
- D-HERMES-20261112-02: Chris approved Hermes-authored provenance records in place of the Adjudicator ticket, and lifted the jday96314
  exclusion for **pinned Apache-2.0** sources. That is not blanket acceptance of unexamined lineage or unlicensed sources. No gate is waived,
  and no gate implementation was changed for this candidate. The `source_url` here does not trip the legacy URL-substring check in `ledger/benchmark_health.py`.
- D-PRA211-05: the dfthcsos `.npz` factor input.
- AGENTS.md: 3 submissions per UTC day, reservation before upload, G0/G3/G5 never waived, no unverified task ships.

## Reported numbers (author-claimed; none is measured here)

The README reports these as "measured with the official verifiers". They are the author's figures.

| Task | Qubits | Cost | Ratio |
|---|---:|---:|---:|
| invsqrt | 46 | 80,162.76 | 25.91x |
| dqi | 889 | 3.6073e11 (at zero failed shots) | 67.75x |
| dfthcsos | 427 | 296,635,967.59 | 11.31x |

Author-stated geometric mean 27.0784 (the rounded ratios above give 27.0778). The README says Kaggle's own draw for the dqi file had
two failed shots and gave a public score of 27.00209. The parent session reports a leaderboard CSV with the public author at 27.02795 for the
latest submission. This record has not checked that CSV, and neither figure is a claim that this candidate will score the same.
Only the full-shot G3 run on this machine, with the unchanged verifier, produces a number this repository can use.

## Conditions before upload

1. G0..G5 all PASS on the exact zip, with no waiver (G3 shots 200540928 / 102400 / 78080, G5 byte-identical rebuild with timeout 7200 s).
2. The shipped bytes equal the pins above. G5 enforces this.
3. This file is committed and `licence_record` still names it.
4. `notices/50-public-portfolio.txt` is committed with the zip's source tree.
5. Reservation before upload, and no more than 3 submissions per UTC day.
