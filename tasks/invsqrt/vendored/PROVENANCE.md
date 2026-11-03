# PRA-325: unchanged licensed invsqrt circuit

Under the board's 2026-10-29 ruling, D-PRA341-01 (PRA-341), this task
vendors a circuit. It does not claim to regenerate it from our own source.
Own-generator work continues on PRA-313.

The accepted source is mrmeows's Kaggle dataset `qcc-1375-open-circuits`,
[version 8](https://www.kaggle.com/datasets/mrmeows/qcc-1375-open-circuits/versions/8),
created 2026-10-27T02:12:53.72Z. The only circuit selected is
`circuits/invsqrt.kmb`, 459,891 bytes, SHA-256
`0766a111a76f241aa57fbbed466436d743be13436943ddb0628c291ca07d67d6`.
`SOURCE.json` contains the version-pinned single-member download URL and local
input path. No other circuit in the dataset is fetched or accepted.

The-adjudicator's [PRA-346 ACCEPT](/PRA/issues/PRA-346), comment
`1f89b270-3343-4d27-83b2-af6a7a9fc517`, covers exactly those bytes under
Apache-2.0. The published lineage is Dmitrii Gluzdov, Phuc Thai (DePie,
EXP-222/225a/226a), Akmal Xodarev (busyaprime), and mrmeows, with marsyas
credited upstream. The record does not independently certify every original
author's licence or undocumented history. Its invsqrt-specific finding does
not accept the separate Schur-descended dqi circuit in the same dataset.
Neither jday96314's repo nor the k256.dev dqi artifact is an input.

The included `LICENSE` is the unchanged version-pinned Apache text, SHA-256
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.
`NOTICE` and `notices/12-invsqrt-vendored.txt` preserve lines 1–8 of the
upstream `circuits/NOTICE.txt` (full upstream file SHA-256
`77a796583fe58d2b3e850b7e849cf0822ecffb0cd28e1d8f4a8c79d4f94b147f`).
The first-person claims remain mrmeows's. A separate correction names the
20.0565x source package instead of the inherited 20.032x predecessor.
The competition zip contains only task files; the licence and notices
accompany it in this repository.

Fetch and stage with:

```sh
uv run python -m tasks.invsqrt.vendored.generate --fetch --out /path/to/staging
```

Without `--fetch`, the command only reads the declared input beneath
`VQCC_DATA` and verifies its SHA-256 before copying. G5 must independently
check the bytes through PRA-345's `vendored_circuit` path, with the licence
record bound in the manifest. G0, G3, and G5 are not waived.
