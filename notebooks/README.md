# Public submission notebook

`vqcc_submission.ipynb` rebuilds submission-011 from pinned main-commit source. It checks every one of the 18 member hashes and the deterministic archive hash against the submission manifest, then runs fresh full competition verifiers. Publication remains John Wick's separate action under PRA-243; this build does not call Kaggle.

The notebook embeds generator source and complete notices with a SHA-256 for each file. The only non-circuit input is SomeJoint's version 1 factor `submission.npz`; it is validated by filename, 1,995,236-byte size, and SHA-256 before being staged alone in a fresh input root. Every circuit is regenerated. The notebook requires CPython 3.13 on Linux, NumPy, SciPy, CUDA-enabled PyTorch and a CUDA GPU; it prints versions and installs nothing.

Run locally from a fresh directory with an extracted competition package and the declared factor:

```sh
uv sync --group notebooks --group gpu
mkdir -p /path/to/fresh-run
cp notebooks/vqcc_submission.ipynb /path/to/fresh-run/vqcc_submission.ipynb
VQCC_DATA=/path/to/google-verifiable-quantum-circuit-compilation \
VQCC_FACTOR=/path/to/submission.npz \
  uv run --group notebooks --group gpu python harness/run_notebook.py /path/to/fresh-run/vqcc_submission.ipynb --timeout 7200
```

On Kaggle the explicit defaults are `/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation` and `/kaggle/input/qcc-our-chemistry-b143-c60-xor2/submission.npz`. Verification uses a fixed public salt, full shots, at most two workers, and one BLAS thread. `submission.zip`, `LICENSE`, `NOTICE`, verifier reports, and a fresh workspace are created next to the notebook. Existing outputs are refused; generated binaries and workspaces must not be committed.

To refresh the notebook, configure the new candidate and its source pin in `build_submission_notebook.py`, then run `uv run --group notebooks python notebooks/build_submission_notebook.py --candidate submission-011`. This clears outputs; execute it again before committing. The builder checks that its 40-hex source pin is on `origin/main` and extracts source via `git show`.

The complete pinned notices retain third-party attribution and the unresolved invsqrt calibration-rights limitation. The Adjudicator's publication verdict and Kaggle-native checks remain required under PRA-243.
