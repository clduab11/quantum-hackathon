# dfthcsos factorization lane (Claude Science)

This folder holds the output of the dfthcsos factorization research lane. It runs in Claude Science (the native Windows
app) as a research bench. The lane looks for FeMoCo factorization shapes (R, B, C) that pass the verifier with 8-bit angle
words at a lower λ_eff·T·Q than the public v7 chemistry
([ahmedberatozer/vqcc-v7-chemistry](https://www.kaggle.com/datasets/ahmedberatozer/vqcc-v7-chemistry), Apache-2.0
per its description).

This folder is evidence and tooling only. It contains no submission candidate, no circuit and no decision row.

## Contents

The files are byte-for-byte copies of the lane's `out\` folder (`C:\Users\cld-main\work\vqcc-dfthcsos\out\`). The notes
refer to them by those `out/...` paths.

| File | What it is | SHA-256 |
| --- | --- | --- |
| `notes/2026-10-26_section8_reproduction.md` | Section 8 reproduction: v7 and baseline metrics from the stored angle words, cost-model split, provenance | `21b53d6436a3bfcdde5ab2b8a976836c6372ef18889e3a79f873e1ef38493b45` |
| `notes/section8_reproduction.json` | The same results as data, including the field-level check against `chem_verify.json` | `49e0fd5a7745919a98a74b5cec5240404c2efe016e968507dfb80d1a90fc6828` |
| `notes/input_sha256.tsv` | SHA-256 manifest of the 56 input files (competition data and v7); CRLF line endings as written | `acaacb581f61d82550da12c71415ec9b5c3a401c0f417e514b39ed3b0213224f` |
| `harness/vqcc_eval.py` | Windows-side screening harness | `0c51e59580976ebab596ebdad6d9321e636b6636e9b5cb08a3cf65e2b038163e` |

## The harness

`vqcc_eval.py` evaluates angle words and the cost model without kickmix:

- It imports the unchanged `dfthcsos.scoreinfra` modules (`reference`, `dfthc_math`, `costs_prepare`).
- It takes `native_inputs`, `heuristic_costs`, `passes_accuracy` and the gate constants straight from `verify.py`'s source by AST extraction. `verify.py` itself imports kickmix, so it can't be imported on Windows. No metric is reimplemented.
- Its results are `evaluate_words` metrics and cost-model values. They are not verifier results. The WSL verifier stays the authority for every candidate.
- `ROOT` is hard-coded to `C:\Users\cld-main\work\vqcc-dfthcsos`, a read-only copy of the competition package and the v7 dataset for the Claude Science sandbox. The originals are in this repo's git-ignored `data/` folder. The module runs the extraction at import, so it doesn't import on Linux or CI. Nothing under `tests/` imports it.

## Section 8 results in brief

From the stored words, the v7 metrics reproduce `chem_verify.json`:

- error₁ and error₂ to within 2e-16 Ha;
- Λ, E_SOS, E_gap and λ_eff bit for bit.

v7 has almost no room left on the accuracy gates: 0.28 mHa on error₂ and 0.17 mHa on E_gap.

In the cost split, 11 of 14 fields match directly. The other 3 differ only by the ANGLE terms: 10,032 Toffolis, and the 32 qubits of J·brot. Both scores match the verifier exactly.

The notes propose a decision row (Windows screening through this harness, with the WSL verifier as the authority). It isn't filed here; under the merge-queue rules it would be a separate `docs/decisions/<id>.md`.
