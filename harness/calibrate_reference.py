"""Verify the supplied reference once and emit a local baseline JSONL to stdout."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.runtime import DATA, load_metric
from harness.verification import emit, fingerprint, report, verify_all
from ledger.gates.g0_preflight import parse_submission
from harness.reference_identity import reference_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Example: uv run python harness/calibrate_reference.py > /tmp/reference-baseline.jsonl. '
        'Requires installed kickmix, supplied data and metric v10. Runs full shots; may take hours. '
        'Partial output is unusable until the complete record. Failure exits 1.'))
    parser.add_argument('--reference', type=Path, default=DATA / 'sample_submission')
    args = parser.parse_args()
    try:
        identity = reference_identity(args.reference)
        checked = parse_submission(args.reference, load_metric())
        emit({'environment': fingerprint(), 'reference_files': identity})
        for name, result, seconds in verify_all(checked):
            emit(report(name, result, seconds))
        emit({'complete': True})
    except Exception as error:
        print(f'CALIBRATION REJECT: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
