# Public submission notebook

`vqcc_submission.ipynb` is the source for the public Kaggle notebook. Publication is a separate, reviewed action owned by John Wick. This build does not call Kaggle.

The notebook embeds 30 source files from main commit `c8bbfbde18bb27f4f89aac90f4b62437877b60f4`, with each file's SHA-256. It rebuilds submission-003 using only the competition package and checks the 13 output hashes against the pinned candidate manifest. It runs fresh competition verifiers, then builds the deterministic archive with `ledger.archive.build_zip`.

Run locally on Linux with the extracted competition data:

```sh
uv sync --group notebooks
VQCC_DATA=/path/to/google-verifiable-quantum-circuit-compilation \
  uv run --group notebooks python harness/run_notebook.py notebooks/vqcc_submission.ipynb --timeout 3600
```

`VQCC_DATA` must contain `kickmix/`, `verifiers/` and `sample_submission/`. The Kaggle default is `/kaggle/input/google-verifiable-quantum-circuit-compilation`. The pinned native library requires CPython 3.13. NumPy and SciPy are supplied by `uv.lock` locally; the notebook prints their actual versions. No package is installed from a cell.

Full verification is the default. Only if the confirmed kernel budget prevents it, set `VQCC_VERIFY_MODE=sample` before running. This reduces invsqrt to one shot per input, dqi to 1,536 shots and dfthcsos to one shot per address. The output explicitly labels this as a sample; it is not full verification or authorization to submit.

The output archive is beside the notebook locally and in the kernel working directory on Kaggle. Each execution also creates a fresh `vqcc-rebuild-*` workspace there, so previous circuits or coefficients cannot be reused. Those generated workspaces and binary outputs must never be committed.

To update the embedded source, deliberately change the full commit pin in `build_submission_notebook.py`, then run:

```sh
uv run --group notebooks python notebooks/build_submission_notebook.py
```

This clears execution outputs. Re-execute before committing. The builder requires the pin to be an ancestor of `origin/main`, extracts source with `git show`, and takes expected hashes from the candidate manifest at that same commit. Tests execute the notebook's helper cell without the expensive circuit build.

The notebook retains the complete pinned task notices. The existing invsqrt dataset-adapted calibration rights remain unresolved; the prior board ruling is not a new third-party licence grant. The environment/compliance checklist from PRA-239 and the Adjudicator's publication verdict remain required before release.
