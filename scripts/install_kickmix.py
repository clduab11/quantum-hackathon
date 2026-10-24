"""Make the supplied kickmix and verifiers importable in the active project venv."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import sysconfig

BINARY_SHA256 = 'c66b3216c4029e0cdfd09054306aa0feadf53ab2f50c1164e37f752874e5005e'


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Example: uv run python scripts/install_kickmix.py /home/cld-main/work/'
        'vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run. '
        'Requires CPython 3.13 and uv sync. Errors exit nonzero; no source files change.'))
    parser.add_argument('data', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Print the venv path and proposed contents only.')
    args = parser.parse_args()
    if sys.prefix == sys.base_prefix or sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 13):
        parser.error('Run with uv run in the CPython 3.13 project venv.')
    data = args.data.resolve()
    binary = data / 'kickmix/kickmix.so'
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA256:
        parser.error('kickmix SHA-256 differs from the inventoried binary; review its ABI first.')
    if not (data / 'verifiers/dqi/verify_submission_dqi.py').is_file():
        parser.error('Data directory must contain the supplied verifiers/.')
    contents = f'{data / "kickmix"}\n{data / "verifiers"}\n'
    if '\n' in str(data) or '\r' in str(data):
        parser.error('Data path must not contain newline characters.')
    target = Path(sysconfig.get_path('purelib')) / 'vqcc_local.pth'
    print(f'{"Would write" if args.dry_run else "Writing"} {target}\n{contents}', flush=True)
    if not args.dry_run:
        # Probe in a fresh interpreter before creating the venv-only path file.
        subprocess.run([sys.executable, '-c',
                        'import sys; sys.path.append(sys.argv[1]); import kickmix; '
                        'print("kickmix", kickmix.__version__, kickmix.__file__)',
                        str(data / 'kickmix')], check=True)
        target.write_text(contents)


if __name__ == '__main__':
    main()
