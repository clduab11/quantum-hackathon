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

## Replacement branch and review gate

The High Table's 2026-10-26 replacement ruling supersedes the earlier
merge-into-feature publication route. The replacement branch
`op-vqcc/PRA-251-jax-loss-rebase` starts at main `3432001ec2d8eb0ed077e9f7dbab2e1586d89cc7`.
Reapplying reviewed repair `2cca62c8b4a0074b307665802d9888cc1a2f4200`
produced tree `b0356b267ab871517a7b7b8ec236d3c1b53530c5`, exactly equal to
its diagnostic integration with that main. No merge commit was created.

The two Phase M commits `b6e3c09` and `a9be778` were then cherry-picked.
Their 20 changed files are byte-identical to source `a9be778`. All 32
historical numerical/evidence files remain byte-identical to `c76ba79`,
including run04 and D-PRA251-02/03/04. The combined tree before this
explanatory documentation update is `45f31ea1a8583d48bdf40248d57cfa1686dc2991`.
Phase M is a recorded negative result, not a new measurement in this rebase.

Validate this checkout with `uv sync --locked`, `uv sync --locked --group gpu`,
`uv lock --check`, `uv run --group gpu pytest`, and
`uv run --group gpu python -m ledger.registers check`. Install the pinned
verifier paths in this checkout's venv first, following `fit_jax/README.md`.
A failure exits nonzero; restore the pinned inputs or resolve the reported
constraint before publication. The current complete queue report belongs
in the replacement PR body. A passing actual queue and a scoped PRA-266
review of the replacement commit are both required for readiness.

Close PR43 as superseded only after the replacement PR exists. Chris alone
merges. To undo the replacement on its feature branch, revert its published
single-parent candidate commit; this removes the JAX/Phase M additions and
restores the base dependencies. Never run that rollback on main or in a
measured environment. To remove only this checkout's verifier path file:

```sh
uv run --group gpu python scripts/uninstall_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
```
