# Formal Schur candidate verification

Run in the `op-vqcc/PRA-261-schur-candidate` worktree, based on
`6babc95e1ed3a61d399ac2a5e3643d023b635ae3`. The manifest was created while
the tree was clean, before these evidence files were written. Its generator
identity is that merged main commit, not a later evidence-only commit.

## Environment

```sh
uv sync
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
```

Initial sync: exit 0, CPython 3.13.13, resolved 105 packages in 1ms,
installed 36 packages in 107ms. Installer: exit 0, verified Kickmix 0.1 and
created only this worktree's `.venv/lib/python3.13/site-packages/vqcc_local.pth`.

## Manifest creation

Used `ledger.gates.runner.start_candidate`, with candidate id `pra261-schur`,
parent `pra250-hankel`, fixed public salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`,
and the existing zip at
`/home/cld-main/work/vqcc-data/pra261-schur-port/pra261-schur.zip`.
Before creation, asserted the full zip SHA-256
`9fcb5fe2e82d052568e2c5857965cf87cb51ab0dd1f107ae00c188f8e07b11d5`,
that parent and submission-006 zip hashes agree, and that all ten non-DQI
member hashes agree. The unchanged tasks inherit the parent's provenance.
DQI records `no-licence`, parent URL `https://github.com/jday96314/QuantumAI`,
source commit `2b9227095bf2c76f9f64a572645d7dce54998298`, and notebook
scriptVersionId 362573669/source SHA-256
`28e0f08476df85323f9d25589f3cf781f13b5df105233193edfe8a5d1cff149c`.
The exact serialized provenance and notes are in the candidate manifest.
`write_manifest(..., exclusive=True)` prevents replacing an existing history.

## Real gates

The following command ran without waivers. `package_root` names the directory
containing the declared `inputs/thc/femoco_thc_r5.npz`; the verifier package
remains at its normal separate path. G5 stages only the declared input.
The runner persists each gate as it completes, so continuation skips completed
gates for the same zip. A failure is preserved in the manifest.

```sh
set -o pipefail
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run python -u - <<'PY' 2>&1 | tee ledger/evidence/pra261-schur/formal/gates.log
from pathlib import Path
import json,time
from ledger.gates.runner import load_config,run_pipeline
from ledger.run_manifest import read_manifest
repo=Path.cwd()
path=repo/'ledger/manifests/candidates/pra261-schur.json'
manifest=read_manifest(path)
start=time.monotonic()
records=run_pipeline(manifest,Path('/home/cld-main/work/vqcc-data/pra261-schur-port/pra261-schur.zip'),load_config(repo/'configs/gates/pra261-schur.yaml'),manifest_file=path,package_root=Path('/home/cld-main/work/vqcc-data'))
for r in records: print(r.gate,r.status,r.reason,flush=True)
print(json.dumps({'shipping_problems':manifest.shipping_problems(),'geometric_mean':manifest.geometric_mean,'elapsed_seconds':time.monotonic()-start}),flush=True)
raise SystemExit(bool(manifest.shipping_problems()))
PY
```

## Repository checks

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run pytest
uv run python -m ledger.registers check
uv run python scripts/merge_gate.py --ref mine=HEAD
```

## Existing rollback evidence

The completed PRA-278 rehearsal is reused, not rerun. Evidence commit:
`298ca0dbcad79349ad1cb559ba0fef0333e36a3d`, branch
`op-vqcc/PRA-261-schur-rollback`, directory
`ledger/evidence/pra261-schur/rollback/`. It pins source generation to
`e1b379b8692bf4d0091c6a46baaed5699859176f` and replaces only DQI, preserving
all ten other members byte-for-byte. It returned exit 0 and produced
`/home/cld-main/work/vqcc-data/pra278-schur-rollback-20261026/fallback.zip`,
SHA-256 `459b2f11778f5bbd576ce69b9f85156ca2c301bd2a3f74752adca5c2dadcbec7`.
The source Schur hash equals this formal candidate's hash.

Exact original command (refuses the existing output root):

```sh
bash /home/cld-main/work/.paperclip-worktrees/quantum-hackathon/PRA-261-schur-rollback/ledger/evidence/pra261-schur/rollback/rehearsal-command.sh
```

[Full command, raw logs, member inventory and prior test output](/api/attachments/b2741456-e761-4d17-b2ad-4caa6ce73f8e/content)
are attached directly to PRA-261, byte-identical to the PRA-278 attachment
`ef1544a3-922a-4bb4-924c-c9355c2680fe` (packet SHA-256
`4dc296e9c8b3b396c8b5911ac53e95dfa63ce13f6566da0ca194a9216d0dceaf`).
No rollback operation changes a shipping default or performs an upload.
