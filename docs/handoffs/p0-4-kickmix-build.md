# Local kickmix setup and scoring

The tools check ZIP files and run the competition's supplied verifiers in WSL.
They do not generate submission circuits or submit to Kaggle. The skill under
`skills/kickmix-verify/` is a draft in this repository, not a company installation.

## Prerequisites and binary identity

Use the extracted competition package at
`/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation`.
For another location, set `VQCC_DATA` before running any command. Do not commit
competition files, `.kmb`, `.npz`, ZIPs, or the extension.

The inventoried binary is Linux x86-64, CPython 3.13 compatible, version `0.1`:

- SHA-256 `c66b3216c4029e0cdfd09054306aa0feadf53ab2f50c1164e37f752874e5005e`
- ELF BuildID `c801b8dfdea5434e28de9b78a95658176992e31d`
- Untagged filename `kickmix.so`; no claim of manylinux/wheel portability.
- Its exact source commit is unknown. The starter notebook pins Qualtran
  `c58703d00b01c346d3e77d3913cf2d6e9e556be3`, which is not binary provenance.

We used the shipped binary. No compiler, source build, `-march=native`, or global
installation was needed. From the repository branch:

```bash
uv sync
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run
uv run python scripts/install_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
uv run python -c 'import kickmix; print(kickmix.__version__, kickmix.__file__)'
```

The installer requires this checkout's own `.venv` and CPython 3.13, verifies the
known binary hash, probes the import, and exclusively creates
`.venv/lib/python3.13/site-packages/vqcc_local.pth`. Identical existing contents
are a no-op. Conflicting contents, symbolic/hard links, linked parent directories,
and targets outside this venv fail nonzero without overwriting anything.
Named data paths are appended, so already-installed modules take precedence.

Rollback removes only this exact path file after checking that its contents match
the original data path. Run from this same checkout, using the same data argument:

```bash
uv run python scripts/uninstall_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run
uv run python scripts/uninstall_kickmix.py /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation
```

An absent file is a no-op. A conflicting or linked file is preserved with exit 1.
This is a path-file rollback, not a full environment rollback: it leaves all
`uv sync` dependencies, the venv, supplied data, metric snapshots and logs intact.
It is valid only for a path file created with the same named data location.

No command here modifies machine settings, the Desktop checkout, or `main`.

## Metric snapshot

G0 calls the unmodified v10 metric's file readers. Keep that external snapshot at
`/home/cld-main/work/vqcc-data/google-quantum-ai-metric-v10.py`, or name it with
`VQCC_METRIC`. The wrapper refuses any other SHA-256:
`e7c5bfafa13cb54e138c70a281ca08ecece3e9203b514f6616fa19bf33475c8f`.

PRA-171's `inventory` evidence attachment contains this exact file. It was restored
from that attachment for this run. Alternatively, download the public metric
notebook source (no login or credentials) and extract its single code cell:

```bash
python - <<'PY'
import hashlib, json, pathlib, urllib.request
url = 'https://www.kaggle.com/api/v1/kernels/pull/metric/google-quantum-ai-metric'
with urllib.request.urlopen(url) as response:
    payload = json.load(response)
notebook = json.loads(payload['blob']['source'])
source = ''.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code')
expected = 'e7c5bfafa13cb54e138c70a281ca08ecece3e9203b514f6616fa19bf33475c8f'
assert hashlib.sha256(source.encode()).hexdigest() == expected, 'Metric changed: use the inventoried v10 evidence snapshot.'
path = pathlib.Path('/home/cld-main/work/vqcc-data/google-quantum-ai-metric-v10.py')
with path.open('x') as out:
    out.write(source)
PY
```

This refuses overwrites and changed metric versions. Do not bypass the hash check
if upstream changes; review the new rules first.

## Reference calibration, ZIP, and scoring

Calibration runs the three full verifiers once on the supplied reference. Its JSONL
records the actual module paths and hashes, Python/dependency versions, one fixed
public salt (`PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`), costs and full verifier output.
Before parsing or simulation, calibration compares the exact file set, sizes and
SHA-256 values to committed `reference_files` in `ledger/p0-4-artifacts.yaml`.
Identical files may move to another root; changed bytes, missing or extra files
are refused. This reference identity is included in the baseline header.
It emits `complete` only after every task passes. Never use a partial log. The
scorer refuses changed/missing reference identity, duplicate/missing task records,
records without matching PASS/full-shot evidence, and different environments.
Old calibration files lacking these fields must be regenerated. Recalibrate after an
import, binary or dependency change; do not edit baselines to force a score.

```bash
uv run python harness/calibrate_reference.py > /home/cld-main/work/vqcc-data/reference-baseline.jsonl
```

There was no ZIP in the supplied package. To make a local test ZIP from the supplied
sample files (not an own-generator submission), run this once. Its output is outside
the repository, and exclusive creation prevents replacement of an existing ZIP.

```bash
python - <<'PY'
from pathlib import Path
import hashlib, shutil, zipfile
root = Path('/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/sample_submission')
out = root.parent.parent / 'reference.zip'
with zipfile.ZipFile(out, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file():
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (2026, 10, 23, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open('rb') as source, archive.open(info, 'w', force_zip64=True) as dest:
                shutil.copyfileobj(source, dest, 1024 * 1024)
with out.open('rb') as source:
    print(out, out.stat().st_size, hashlib.file_digest(source, 'sha256').hexdigest())
PY
uv run python ledger/gates/g0_preflight.py /home/cld-main/work/vqcc-data/reference.zip
uv run python harness/score_local.py /home/cld-main/work/vqcc-data/reference.zip
uv run pytest
```

Use `--baseline PATH` for a named calibration file. stdout is JSONL; progress and
rejection reasons go to stderr. Any error exits 1 and emits no geometric mean.
The command extracts into a temporary directory and deletes it on exit. Keep enough
disk for the uncompressed ZIP (~910 MB for the reference) and RAM for the package
verifiers. Full runs can take tens of minutes or longer; no reduced-shot mode exists.

Local imports take precedence. The invocation uses invsqrt `for_n_p(10)`, DQI's
default 102,400 shots and DFTHC's default 64 shots/address. The task order is fixed
locally for readable logs; Kaggle randomizes it to hide private split information.
The same checks, parameters, cost formulas and geometric mean apply. A passing
local run does not guarantee acceptance under private Kaggle salts.

## What G0 proves

G0 uses the metric's suffix-based parser, instruction whitelist, strict ID bound
(`<699050`), register caps/names, recursive task discovery and NPZ rules. Invsqrt
must have exactly one register; the verifier later checks its name/width/content.
DFTHC is a directory with a consecutive ANGLE family and exactly one recursive
`submission.npz`, not one file. The 64 MiB cap counts required arrays' decoded
bytes, not compressed file size or ignored extras. G0 checks NPZ dimensions and
dtypes; accuracy, factorization validity and task-specific register contracts
remain verifier checks. No simulator is created by G0.

ZIP containment checks additionally reject unsafe paths, duplicate normalized paths,
links and special files before extraction. They are local wrapper protections;
the notebook metric assumes an already extracted submission. G0 parses all files
before verification, and checks small metadata/NPZ failures before large circuits.

Reports distinguish executed Toffolis from static counts. Invsqrt T includes
synthesized rotations; its raw verifier `t_count` does not. DQI's T and DFTHC's T
are Toffoli resources, not T-gate counts. `epsilon_plus` is null outside DQI.
Invsqrt/DFTHC failures are zero on PASS; they throw on the first detected failure.

## Numerical evidence and limits

`tests/test_costs.py` tests the package's Clopper–Pearson and repetition helpers,
the reference Lambda/E_gap pair, rotation synthesis accounting, Q squared for DQI,
and the public lineage's reported scalar/cost. Each report cross-checks its cost
against the accounting formula.

The [public Signed-Digit Memory v3 source](https://www.kaggle.com/code/anazemcev/quantum-circuits-signed-digit-memory)
hardcodes `lambda_eff=47.558542335159316`, Q=681, T=71958. Source snapshot SHA-256:
`79f6373302cb916a88f65a1b142024d4d2d0b14e41eb58bef3152ebd45ffd0ca`.
It inherits factor NPZ `c5b4165e7b1dcacf1d287746642414a9ba6086b4279e5ede2bb73e21e6aebd98`
and does not disclose its Lambda/E_gap pair in source. Thus the 47.56 test is a
reported-value regression, not an independent derivation or lineage acceptance.
No inherited DQI artifact is downloaded or shipped by these tools.

The completed run is summarized in [verification results](p0-4-verify-results.md).

## Gate runner import contract

`ledger.gates.g0_preflight:preflight(submission_dir: pathlib.Path) -> dict` accepts
an extracted directory and returns `{"status": "PASS"}` or `{"status": "FAIL: reason"}`.
The runner owns ZIP safety; the ZIP CLI uses the same safety checks locally.
`parse_submission` is an internal parser returning objects; it is not the gate hook.

`harness.score_local:score_submission(submission_dir, *, salt_label, shot_divisor=1)`
returns the status plus `kickmix_build_id` (binary SHA-256), `qualtran_pin` (null,
because binary source provenance is unknown), the three verifier entry-point
SHA-256 values in `verifier_hashes`, unchanged verifier summaries in `tasks`,
`baseline_costs`, and `geometric_mean`. It independently checks G0 before loading
the baseline or starting simulation. Any exception returns `FAIL: reason`.

Only `salt_label="PRA171_LOCAL_PUBLIC_FIXED_SALT_0001"` and `shot_divisor=1` are
supported. Other values fail before parsing. There is no reduced-shot G2 mode.
The hook reads `DATA.parent / "reference-baseline.jsonl"`; `VQCC_DATA` names DATA
before import. Use the CLI's `--baseline` to select a different calibration file.
Example (after full calibration in the named default location):

```bash
uv run python - <<'PYCODE'
from pathlib import Path
from harness.score_local import score_submission
print(score_submission(
    Path('/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/sample_submission'),
    salt_label='PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'))
PYCODE
```

`tests/test_gate_contract.py` exercises consumer dispatch through both
`module:function` paths, refusal before G3 on invalid input, the G3 defense when
called directly, unchanged summaries, aggregation, and fixed salt/full shots.
