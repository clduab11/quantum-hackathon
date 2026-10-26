# PRA-260: shared GPU dependency reconciliation candidate

The root optional `gpu` group now declares JAX 0.12.0.1 and PyTorch
2.8.0+cu128 together. `uv lock` generated the lock from main's existing lock;
no lock entries were edited by hand. The resolver retained every main package
version and added nine packages. Default groups remain dev and search.

The installed JAX CUDA plugin metadata permits all of PyTorch's exact shared
NVIDIA pins. For example, JAX requires cuDNN >=9.10.2.21,<10.0 and PyTorch
requires exactly 9.10.2.21. This proves package constraint compatibility, not
numerical equivalence to the historical measured environment.

## Explicit changes from the measured JAX environment

| package | measured PR43 lock | shared candidate |
| --- | --- | --- |
| nvidia-cublas-cu12 | 12.9.2.10 | 12.8.4.1 |
| nvidia-cuda-cupti-cu12 | 12.9.79 | 12.8.90 |
| nvidia-cuda-nvrtc-cu12 | 12.9.86 | 12.8.93 |
| nvidia-cuda-runtime-cu12 | 12.9.79 | 12.8.90 |
| nvidia-cudnn-cu12 | 9.27.0.42 | 9.10.2.21 |
| nvidia-cufft-cu12 | 11.4.1.4 | 11.3.3.83 |
| nvidia-cusolver-cu12 | 11.7.5.82 | 11.7.3.90 |
| nvidia-cusparse-cu12 | 12.5.10.65 | 12.5.8.93 |
| nvidia-nccl-cu12 | 2.32.3 | 2.27.3 |
| nvidia-nvjitlink-cu12 | 12.9.86 | 12.8.93 |

JAX, jaxlib, jax-cuda12-pjrt and jax-cuda12-plugin remain 0.12.0.1.
JAX-only CUDA compiler 12.9.86, CCCL 12.9.27 and NVSHMEM 3.8.0 remain unchanged.
No new fit or historical score is attributed to this candidate environment.

## Historical replay

The measured environment remains defined by PR43 remote commit
`6d684d1f56de899badb18819eee7de9279c26faf` (tree
`bb69dd7c76f947a8dbc6d7cdfbd3951af585c99f`, identical to local `c76ba79`).
Its original lock SHA-256 is
`60df647763ecc14560509fcaf224087b1f0ad950a1d926ce89074ec0d4174cab`.
The run04 launch, result, monitor and D-PRA251-02/03/04 files stay byte-identical.
Historical scores describe that earlier runtime only.

To reconstruct the historical environment without changing the current venv,
run from a repository containing the recorded commit, with uv and Python 3.13:

```sh
replay_dir=$(mktemp -d)
git show 6d684d1f56de899badb18819eee7de9279c26faf:pyproject.toml > "$replay_dir/pyproject.toml"
git show 6d684d1f56de899badb18819eee7de9279c26faf:uv.lock > "$replay_dir/uv.lock"
uv sync --project "$replay_dir" --locked --group gpu
```

This installs packages into the scratch project's .venv; it starts no fit.
A missing commit, unavailable package or inconsistent lock fails nonzero.
Use the recorded code/input hashes when separately authorizing a replay.

## Candidate environment and notice

From this worktree, `uv sync --locked --group gpu --dry-run` prints planned
changes. To validate in a separate environment, set `UV_PROJECT_ENVIRONMENT`
to an absolute scratch path before `uv sync --locked --group gpu`.
`uv lock --check` must pass before using the lock. GPU packages remain optional.
No system packages or services are touched.

The unchanged PRA-251 notice follows the two merged PRA-245 input bullets in
`notices/30-dfthcsos.txt`. Numerical Python sources and all historical evidence
remain unchanged.

## Branch history and review gate

PR43 and main share pre-squash base `c196150`. A scratch three-way merge of
main `9db5f61` with a forward candidate commit still conflicts in
`pyproject.toml`, `uv.lock`, and `notices/30-dfthcsos.txt`, even though the
candidate content reconciles those files. This candidate is not merge-ready.
The no-merge and no-force-push rules prevent advancing its ancestry by the
usual branch-update methods. The High Table must obtain or identify the
specific permitted branch update before the full queue can pass.

The scoped Adjudicator review must cover dependency downgrades, historical
replay instructions, notice retention and the eventual final tree. The board
alone decides and executes merges. Roll back this maintenance change with
`git revert <maintenance-commit>` on the owned branch; do not change main.
