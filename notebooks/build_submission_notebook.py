# SPDX-License-Identifier: Apache-2.0
"""Generate the public notebook from a fixed main commit; never execute its inputs.

uv run --group notebooks python notebooks/build_submission_notebook.py
Outputs are intentionally cleared; run harness/run_notebook.py before committing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import textwrap

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '1d3b1178e6de84acd76c9ac751b0d88f666bfef0'
MANIFEST_COMMIT = '1d3b1178e6de84acd76c9ac751b0d88f666bfef0'
CANDIDATES = {'submission-011': {'manifest': 'ledger/manifests/submissions/submission-011.json', 'zip_bytes': 31514298}}
REPO_URL = 'https://github.com/clduab11/quantum-hackathon'

HELPERS = '''\
# SPDX-License-Identifier: Apache-2.0
import hashlib
from pathlib import Path, PurePosixPath


def check_hash(path, expected):
    path = Path(path)
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(f'{path.name}: SHA-256 {actual}', flush=True)
    if actual != expected:
        raise ValueError(f'SHA-256 mismatch for {path.name}: {actual} != {expected}')
    return actual


def check_files(root, expected):
    root = Path(root)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected):
        raise ValueError(f'File set mismatch: missing={sorted(set(expected)-actual)}, '
                         f'extra={sorted(actual-set(expected))}')
    for name, digest in sorted(expected.items()):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'Unsafe output path: {name}')
        print(name, end=': ')
        check_hash(path, digest)


def restore_sources(root, sources, hashes):
    if set(sources) != set(hashes):
        raise ValueError('Source inventory mismatch')
    for name, source in sources.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\\\' in name:
            raise ValueError(f'Unsafe source path: {name}')
        if hashlib.sha256(source.encode('utf-8')).hexdigest() != hashes[name]:
            raise ValueError(f'SHA-256 mismatch for vendored source: {name}')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    for name, source in sorted(sources.items()):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode('utf-8'))
        print(f'{name}: SHA-256 {hashes[name]}')


def competition_root(override=None, candidates=None):
    if candidates is None:
        candidates = [Path('/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation')]
    roots = [Path(override)] if override is not None else candidates
    for root in roots:
        root = Path(root).resolve()
        if all((root / name).is_dir() for name in ('kickmix', 'verifiers', 'sample_submission')):
            return root
    raise FileNotFoundError('No competition root with kickmix/, verifiers/ and sample_submission/; set VQCC_DATA')


def stage_factor(path, root, size, digest):
    import shutil
    path, root = Path(path), Path(root)
    if path.name != 'submission.npz':
        raise ValueError('Factor filename must be submission.npz')
    if path.stat().st_size != size:
        raise ValueError('Factor size mismatch')
    check_hash(path, digest)
    dest = root / 'inputs/somejoint/qcc-our-chemistry-b143-c60-xor2-v1/submission.npz'
    dest.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(path, dest)
    check_hash(dest, digest)
    return dest


def check_archive(path, expected):
    # Call only after every member hash has passed.
    try:
        return check_hash(path, expected)
    except ValueError as error:
        raise ValueError('R2: member-identical, container differs; check zlib versions') from error
'''


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', choices=sorted(CANDIDATES), default='submission-011')
    args = parser.parse_args()
    candidate = CANDIDATES[args.candidate]
    manifest_path = candidate['manifest']
    commit = git('rev-parse', COMMIT + '^{commit}')
    subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'], cwd=ROOT, check=True)

    def read(name, ref=commit):
        return subprocess.check_output(['git', 'show', f'{ref}:{name}'], cwd=ROOT).decode()

    paths = ['LICENSE', 'NOTICE', 'tasks/__init__.py', 'tasks/invsqrt/__init__.py',
             'tasks/dfthcsos/generate.py', 'tasks/dfthcsos/b143.py',
             'tasks/dqi/generate_fused.py', 'ledger/__init__.py', 'ledger/archive.py']
    paths += ['tasks/invsqrt/' + name + '.py' for name in ('affine', 'calibrate', 'peephole', 'signed_digit')]
    paths += ['tasks/invsqrt/public_port/' + name + '.py' for name in
              ('__init__', 'generate', 'fit', 'model', 'schedule', 'calibration', 'arithmetic', 'deferred', 'virtual_low')]
    paths += ['tasks/dfthcsos/full_xor/' + name for name in
              ('__init__.py', 'emitter.py', 'paired_anf.py', 'scheduler.py', 'validation.py', 'planio.py', 'plans.json')]
    source_map = json.loads(read('tasks/dqi/fused/SOURCE_MAP.json'))
    paths += ['tasks/dqi/fused/SOURCE_MAP.json'] + ['tasks/dqi/fused/' + row['file'] for row in source_map['files']]
    paths += git('ls-tree', '-r', '--name-only', MANIFEST_COMMIT, 'notices').splitlines()
    paths = sorted(set(paths))
    sources = {p: read(p, MANIFEST_COMMIT if p.startswith('notices/') else commit) for p in paths}
    hashes = {p: hashlib.sha256(v.encode()).hexdigest() for p, v in sources.items()}
    manifest_text = read(manifest_path, MANIFEST_COMMIT)
    manifest = json.loads(manifest_text)
    expected = {p: h for task in manifest['tasks'].values() for p, h in task['files'].items()}
    config = {'commit': commit, 'repository': REPO_URL, 'manifest': manifest_path, 'candidate': args.candidate,
              'manifest_commit': MANIFEST_COMMIT,
              'manifest_sha256': hashlib.sha256(manifest_text.encode()).hexdigest(),
              'files': expected, 'zip_sha256': manifest['zip_sha256'], 'zip_bytes': candidate['zip_bytes'], 'factor_bytes': 1995236,
              'kickmix_sha256': manifest['kickmix_build_id'],
              'verifiers': {t: info['verifier_sha256'] for t, info in manifest['tasks'].items()}}
    cells = []

    def md(id, text):
        cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(text).strip(), id=id))

    def code(id, text):
        source = textwrap.dedent(text).strip()
        if not source.startswith('# SPDX-License-Identifier: Apache-2.0'):
            source = '# SPDX-License-Identifier: Apache-2.0\n' + source
        cells.append(nbf.v4.new_code_cell(source, id=id))

    md('introduction', '''
        # Rebuild our quantum circuit submission

        **Released under the Apache License 2.0.** Third-party notices and the existing
        calibration-rights limitation are retained below.

        Google Quantum AI's [Verifiable Quantum Circuit Compilation competition](https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation)
        asks us to make three quantum calculations cheaper while preserving their answers.
        **invsqrt** computes inverse square-root arithmetic with an interpolated polynomial.
        **dqi** decodes an error-correcting code with a fused decoder.
        **dfthcsos** loads angle words for a chemistry simulation using five-word XOR batches.

        A higher ratio means a lower cost than Google's reference. Our recorded local ratios are
        **13.24× / 54.73× / 9.78×** (geometric mean about **19.20572**); the same submission received
        **19.20572 on the public leaderboard**. These are historical results, not
        a claim that this run reproduces the hidden evaluation's score.

        This notebook rebuilds submission-011 from source, compares every output byte by SHA-256,
        and runs fresh checks using the competition verifiers. The final file is `submission.zip`.
        No earlier notebook output or verifier receipt is used.
        ''')
    md('setup-notes', f'''
        ## Run this notebook

        Attach the competition data and SomeJoint dataset `qcc-our-chemistry-b143-c60-xor2` version 1. The default path is
        `/kaggle/input/competitions/google-verifiable-quantum-circuit-compilation`.
        No other competition directory is searched or read.
        For a local run, set **VQCC_DATA** to the extracted competition package root (the directory
        containing `kickmix`, `verifiers`, and `sample_submission`). Set **VQCC_FACTOR** to the explicit local path to `submission.npz`; on Kaggle the default is `/kaggle/input/qcc-our-chemistry-b143-c60-xor2/submission.npz`.
        The packaged native library requires **CPython 3.13 on Linux**. NumPy, SciPy, CUDA-enabled PyTorch and a CUDA GPU must be
        available; this notebook installs nothing and makes no network request. It prints their
        versions and fails if the source, native library, verifier, generated files or archive differ.

        The generator source is embedded verbatim from [{commit}]({REPO_URL}/tree/{commit}),
        a commit on `main`. Every embedded file has its own SHA-256 below. This avoids a runtime
        clone and works with internet disabled. The notebook builder extracts these files with
        `git show`; its source remains beside this notebook in the repository.

        Verification defaults to **full**: 64 invsqrt shots for each of 3,133,452 inputs,
        102,400 dqi shots, and 64 dfthcsos shots per address. Budget roughly 30 minutes for
        verification plus the build; actual times are printed. The public salt is fixed once;
        no seed or salt search occurs. At most two verifier workers and one BLAS thread bound CPU use.
        ''')
    code('hash-helpers', HELPERS)
    code('pinned-source', 'CONFIG = ' + repr(config) + '\nSOURCES = ' + repr(sources) + '\nSOURCE_HASHES = ' + repr(hashes))
    code('prepare', r'''
        import importlib.metadata
        import json
        import os
        import platform
        import subprocess
        import sys
        import tempfile
        import time
        import zlib

        STARTED = time.monotonic()
        DATA = competition_root(os.environ.get('VQCC_DATA'))
        MODE = 'full'
        WORKERS = min(2, os.cpu_count() or 1)
        for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            os.environ[variable] = '1'
        if sys.version_info[:2] != (3, 13) or platform.system() != 'Linux':
            raise RuntimeError('The pinned competition kickmix requires CPython 3.13 on Linux')
        for name in ('kickmix', 'verifiers', 'sample_submission'):
            if not (DATA / name).is_dir():
                raise FileNotFoundError(f'VQCC_DATA must contain {name}/')
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA-enabled torch and a CUDA GPU are required for invsqrt fitting')
        print('CUDA device:', torch.cuda.get_device_name(0), 'torch CUDA:', torch.version.cuda)
        print('Source commit:', CONFIG['commit'])
        print('Manifest:', CONFIG['manifest'], 'at', CONFIG['manifest_commit'], 'SHA-256', CONFIG['manifest_sha256'])
        memory = next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:'))
        environment = {'python': sys.version, 'platform': platform.platform(),
                       'packages': {p: importlib.metadata.version(p) for p in ('numpy', 'scipy', 'torch')},
                       'cpu_count': os.cpu_count(), 'memory': memory,
                       'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION,
                       'workers': WORKERS, 'blas_threads': 1, 'mode': MODE,
                       'source_commit': CONFIG['commit'], 'kickmix_sha256': CONFIG['kickmix_sha256']}
        print(json.dumps(environment, indent=2))
        print('Verification mode:', MODE)
        check_hash(DATA / 'kickmix/kickmix.so', CONFIG['kickmix_sha256'])
        for task, relative in {'invsqrt': 'invsqrt/verify_submission_invsqrt.py',
                               'dqi': 'dqi/verify_submission_dqi.py', 'dfthcsos': 'dfthcsos/verify.py'}.items():
            check_hash(DATA / 'verifiers' / relative, CONFIG['verifiers'][task])
        factor = Path(os.environ.get('VQCC_FACTOR', '/kaggle/input/qcc-our-chemistry-b143-c60-xor2/submission.npz'))
        # Validate before creating the isolated input root or running a generator.
        if factor.name != 'submission.npz' or factor.stat().st_size != CONFIG['factor_bytes']:
            raise ValueError('Factor filename or size mismatch')
        check_hash(factor, CONFIG['files']['dfthcsos/submission.npz'])
        # A new directory on each run prevents stale circuits or cached coefficient tables.
        WORK = Path(tempfile.mkdtemp(prefix='vqcc-rebuild-', dir=Path.cwd()))
        INPUT = WORK / 'input'
        stage_factor(factor, INPUT, CONFIG['factor_bytes'], CONFIG['files']['dfthcsos/submission.npz'])
        SOURCE = WORK / 'source'
        OUTPUT = WORK / 'submission'
        OUTPUT.mkdir()
        if any(OUTPUT.iterdir()):
            raise ValueError('Submission output directory must start empty')
        REPORTS = WORK / 'reports'
        REPORTS.mkdir()
        for name in ('submission.zip', 'LICENSE', 'NOTICE', 'reports'):
            if (Path.cwd() / name).exists():
                raise FileExistsError(f'Prior output {name} exists; use a fresh working directory')
        (REPORTS / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
        (REPORTS / 'sources.json').write_text(json.dumps(
            {'commit': CONFIG['commit'], 'files': SOURCE_HASHES, 'expected': CONFIG}, indent=2) + '\n')
        restore_sources(SOURCE, SOURCES, SOURCE_HASHES)
        (Path.cwd() / 'LICENSE').write_text(SOURCES['LICENSE'])
        notice = SOURCES['NOTICE'].rstrip() + '\n\n' + ''.join(
            text for name, text in sorted(SOURCES.items()) if name.startswith('notices/'))
        (Path.cwd() / 'NOTICE').write_text(notice)
        sys.path[:0] = [str(SOURCE), str(DATA / 'kickmix'), str(DATA / 'verifiers')]
        import kickmix as km
        check_hash(Path(km.__file__), CONFIG['kickmix_sha256'])
        ENV = {
            'VQCC_DATA': str(DATA),
            'PYTHONPATH': os.pathsep.join(
                [str(SOURCE), str(DATA / 'kickmix'), str(DATA / 'verifiers')]),
            'OMP_NUM_THREADS': '1',
            'OPENBLAS_NUM_THREADS': '1',
            'MKL_NUM_THREADS': '1',
            'NUMEXPR_NUM_THREADS': '1',
        }
        print('Fresh workspace:', WORK.name)
    ''')
    md('build-notes', '''
        ## Build all three tasks

        The arithmetic circuit adapts Dmitrii Gluzdov's invsqrt work; the decoder ports Agniv Banerjee (SomeJoint)'s fused DQI compiler; the chemistry circuits port Agniv Banerjee (SomeJoint)'s full-XOR compiler using our committed plans. Their exact source names, URLs, licences, and additional parents are in the complete notices below. Our orchestration, deterministic packaging and
        byte checks are in this repository. The only copied output is SomeJoint's declared non-circuit
        factorization `dfthcsos/submission.npz`; every `.kmb` is newly generated.
        The verifiers also use the reference physics data inside the same competition package.
        ''')
    for task, module, extra in (
        ('invsqrt', 'tasks.invsqrt.public_port.generate', ['--circuit-only']),
        ('dqi', 'tasks.dqi.generate_fused', []),
        ('dfthcsos', 'tasks.dfthcsos.b143', []),
    ):
        code('build-' + task, f"""
            started = time.monotonic()
            command = [sys.executable, '-m', {module!r}, '--out', str(OUTPUT)] + {extra!r}
            if {task!r} == 'dfthcsos':
                command += ['--data', str(INPUT)]
            subprocess.run(command, cwd=SOURCE, env=ENV, check=True)
            print('{task} build seconds:', round(time.monotonic() - started, 2))
        """)
    code('check-build', '''
        check_files(OUTPUT, CONFIG['files'])
        print(f"All {len(CONFIG['files'])} generated/copied file hashes match submission-011.")
    ''')
    md('verify-notes', '''
        ## Fresh verifier results

        These calls use the competition's unchanged verifiers. Each cell raises on failure.
        The run uses the fixed public salt `PRA171_LOCAL_PUBLIC_FIXED_SALT_0001`.
        No stored verifier receipts are consulted.
        ''')
    code('verify-setup', r'''
        import math
        from invsqrt import verify_submission_invsqrt as inv
        from dqi import verify_submission_dqi as dqi
        from dfthcsos import verify as df

        SALT = 'PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'
        receipts = {}

        def record(task, result, started):
            if result.get('status') != 'PASS' or not math.isfinite(result.get('score', float('nan'))) or result['score'] <= 0:
                raise ValueError(f'{task} verifier failed: {result}')
            receipt = {'task': task, 'mode': MODE, 'salt': SALT,
                       'seconds': round(time.monotonic() - started, 2), 'result': result}
            receipts[task] = receipt
            (REPORTS / (task + '.json')).write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
            print(json.dumps(receipt, indent=2, allow_nan=False))
    ''')
    code('verify-invsqrt', '''
        started = time.monotonic()
        spec = inv.ProblemSpecInvSqrt.for_n_p(10, shots_per_x=64)
        record('invsqrt', inv.verify(km.Circuit.from_file(OUTPUT / 'invsqrt.kmb'), spec,
                                    seed=None, salt=SALT, max_workers=WORKERS), started)
    ''')
    code('verify-dqi', '''
        started = time.monotonic()
        spec = dqi.ProblemSpecDQI.benchmark_instance(num_shots=102400)
        record('dqi', dqi.verify(km.Circuit.from_file(OUTPUT / 'dqi.kmb'), spec,
                                seed=None, salt=SALT, log2_delta=-128, max_workers=WORKERS), started)
    ''')
    code('verify-dfthcsos', '''
        started = time.monotonic()
        record('dfthcsos', df.verify(OUTPUT / 'dfthcsos', seed=None, salt=SALT,
                                     shots_per_address=64), started)
    ''')
    code('archive', r'''
        from ledger.archive import build_zip

        if set(receipts) != {'invsqrt', 'dqi', 'dfthcsos'}:
            raise RuntimeError('All three fresh verifier results are required')
        check_files(OUTPUT, CONFIG['files'])
        archive = build_zip(OUTPUT, WORK / 'submission.zip')
        check_archive(archive, CONFIG['zip_sha256'])
        if archive.stat().st_size != CONFIG['zip_bytes']:
            raise ValueError('Archive size differs from the ledger')
        # Publish the local output name only after all checks have passed.
        import shutil
        shutil.copyfile(archive, Path.cwd() / 'submission.zip')
        (REPORTS / 'reproduction.json').write_text(json.dumps(
            {'files': CONFIG['files'], 'zip_sha256': CONFIG['zip_sha256'],
             'zip_bytes': archive.stat().st_size, 'verification_mode': MODE,
             'wall_seconds': round(time.monotonic() - STARTED, 2)}, indent=2) + '\n')
        shutil.copytree(REPORTS, Path.cwd() / 'reports')
        print('submission.zip:', archive.stat().st_size, 'bytes; SHA-256', CONFIG['zip_sha256'])
        print('Verification:', MODE, '; Kaggle hidden-score equivalence is not asserted.')
    ''')
    md('licence', f'''
        ## Licence and attribution

        The notebook's Praxen-authored code is released under the **Apache License, Version 2.0**.
        The full licence is included in the source cell and at [{REPO_URL}/blob/{commit}/LICENSE]({REPO_URL}/blob/{commit}/LICENSE).
        Ported code retains its original notices. This statement does not grant new rights to
        third-party material. The invsqrt coefficient table is regenerated with dataset-adapted
        calibration; **calibration rights remain unresolved**, as recorded in the repository.
        The board authorized this bundle while retaining that record. Publication review must
        address that existing limitation; this build does not resolve it.

        The following are the repository's complete notices, reproduced verbatim at the pinned
        commit. Some describe other experiments or reference implementations: those are identified
        in the notices and are not claims that this notebook uses those inputs.
        ''')
    for area in ('10-invsqrt', '20-dqi', '30-dfthcsos', '90-not-included'):
        md('notices-' + area, sources['notices/' + area + '.txt'])
    nb = nbf.v4.new_notebook(cells=cells, metadata={
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.13'},
        'vqcc': {'source_commit': commit, 'licence': 'Apache-2.0'}})
    nbf.write(nb, ROOT / 'notebooks/vqcc_submission.ipynb')
    print(f'Wrote {len(cells)} cells, {len(sources)} source files, commit {commit}')


if __name__ == '__main__':
    main()
