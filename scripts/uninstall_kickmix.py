"""Remove only this repository's matching vqcc_local.pth; keep dependencies and data."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.kickmix_paths import existing_matches, path_contents, path_file


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Example: uv run python scripts/uninstall_kickmix.py /home/cld-main/work/'
        'vqcc-data/google-verifiable-quantum-circuit-compilation --dry-run. '
        'Requires this repository CPython 3.13 venv and the original data path. '
        'Mismatched contents, links or wrong environments exit 1 and preserve the file. '
        'This removes the path file only; it does not undo uv sync.'))
    parser.add_argument('data', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Check the exact target and print removal only.')
    args = parser.parse_args()
    try:
        target = path_file()
        if not existing_matches(target, path_contents(args.data)):
            print(f'Already absent: {target}')
        elif args.dry_run:
            print(f'Would remove matching path file: {target}')
        else:
            target.unlink()
            print(f'Removed matching path file: {target}')
        return 0
    except Exception as error:
        print(f'ROLLBACK REJECT: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
