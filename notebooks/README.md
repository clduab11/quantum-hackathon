# Public submission notebook

`vqcc_submission.ipynb` is the source for the public Kaggle notebook. Publication is a separate, reviewed action owned by John Wick. This build does not call Kaggle.

The notebook embeds 32 source files from main commit `562663a62327ce4d81fdea7d5949ff39ce7667c3`, with each file's SHA-256. It rebuilds submission-003 using only the competition package and checks the 13 output hashes against the pinned candidate manifest. It runs fresh competition verifiers, then builds the deterministic archive with `ledger.archive.build_zip`.

Run locally on Linux with the extracted competition data:

```sh
uv sync --group notebooks
VQCC_DATA=/path/to/google-verifiable-quantum-circuit-compilation \
  uv run --group notebooks python harness/run_notebook.py notebooks/vqcc_submission.ipynb --timeout 3600
```

`VQCC_DATA` must contain `kickmix/`, `verifiers/` and `sample_submission/`. The Kaggle default is `/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation`, with exact-layout fallbacks at `/kaggle/input/google-verifiable-quantum-circuit-compilation` and `/kaggle/input`. The pinned native library requires CPython 3.13. NumPy and SciPy are supplied by `uv.lock` locally; the notebook prints their actual versions. No package is installed from a cell.

Full verification is the default. Only if the confirmed kernel budget prevents it, set `VQCC_VERIFY_MODE=sample` before running. This reduces invsqrt to one shot per input, dqi to 1,536 shots and dfthcsos to one shot per address. The output explicitly labels this as a sample; it is not full verification or authorization to submit.

The output archive, `LICENSE`, complete `NOTICE`, and `reports/*.json` are beside the notebook locally and in the kernel working directory on Kaggle. Existing outputs are refused; use a fresh directory when rerunning. Reports record runtime/zlib/memory, source and output hashes, and fresh verifier receipts. Verification uses at most two workers, with single-thread BLAS. Each execution also creates a fresh `vqcc-rebuild-*` workspace there, so previous circuits or coefficients cannot be reused. Those generated workspaces and binary outputs must never be committed.

To update the embedded source, deliberately change the full commit pin in `build_submission_notebook.py`, then run:

```sh
uv run --group notebooks python notebooks/build_submission_notebook.py
```

This clears execution outputs. Re-execute before committing. The builder requires the pin to be an ancestor of `origin/main`, extracts source with `git show`, and takes expected hashes from the candidate manifest at the separately stated `MANIFEST_COMMIT` (`c8bbfbde18bb27f4f89aac90f4b62437877b60f4`; the candidate record was committed after its generators). Tests execute the notebook's helper cell without the expensive circuit build.

The notebook retains the complete pinned task notices. The existing invsqrt dataset-adapted calibration rights remain unresolved; the prior board ruling is not a new third-party licence grant. The PRA-239 checklist is implemented with one explicit N12 exception: historical vendored Python files keep their original bytes and headers, so files without an SPDX line remain without one. All new notebook code cells carry Apache-2.0 SPDX headers, and the complete licence and notices ship as outputs. This preserves N1's exact-source requirement. The Adjudicator's publication verdict and Kaggle-native checks remain required on PRA-243.
