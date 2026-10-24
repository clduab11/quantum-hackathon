"""Make the supplied kickmix and verifiers importable in this repository's venv."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.kickmix_paths import BINARY_SHA256, existing_matches, path_contents, path_file


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Example: uv run python scripts/install_kickmix.py /home/cld-main/work/'
        'vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run. '
        'Requires uv sync in this repository (CPython 3.13). '
        'Conflicts, links and incorrect environments fail nonzero without overwriting files.'))
    parser.add_argument('data', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Check inputs and print the proposed write only.')
    args = parser.parse_args()
    try:
        target = path_file()
        data = args.data.resolve()
        contents = path_contents(data)
        binary = data / 'kickmix/kickmix.so'
        if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA256:
            raise ValueError('kickmix SHA-256 differs from inventory; review its ABI first.')
        if not (data / 'verifiers/dqi/verify_submission_dqi.py').is_file():
            raise ValueError('Data directory must contain the supplied verifiers/.')
        if existing_matches(target, contents):
            print(f'Unchanged: {target}')
            return 0
        if args.dry_run:
            print(f'Would create: {target}\n{contents}', end='')
            return 0
        subprocess.run([sys.executable, '-c',
                        'import sys; sys.path.append(sys.argv[1]); import kickmix; '
                        'print("kickmix", kickmix.__version__, kickmix.__file__)',
                        str(data / 'kickmix')], check=True)
        with target.open('x') as stream:
            stream.write(contents)
        print(f'Created: {target}')
        return 0
    except Exception as error:
        print(f'INSTALL REJECT: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
