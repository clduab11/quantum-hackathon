"""Preflight a submission ZIP, run full package verifiers, and print the local metric."""
import argparse
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.runtime import DATA, load_metric
from harness.verification import emit, fingerprint, report, verify_all
from ledger.gates.g0_preflight import preflight_zip


def load_baseline(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or rows[-1] != {'complete': True}:
        raise ValueError('Incomplete baseline: run harness/calibrate_reference.py successfully first.')
    if rows[0].get('environment') != fingerprint():
        raise ValueError('Baseline environment differs: recalibrate with the same imports and public salt.')
    costs = {r['task']: r['cost'] for r in rows if 'task' in r}
    if set(costs) != {'invsqrt', 'dqi', 'dfthcsos'} or any(not math.isfinite(v) or v <= 0 for v in costs.values()):
        raise ValueError('Baseline must have finite positive costs for all three tasks.')
    return costs


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Example: uv run python harness/score_local.py /home/cld-main/work/vqcc-data/reference.zip. '
        'Requires v10 metric, kickmix, data and a full local reference calibration. '
        'Only scratch extraction is written. Any failure exits 1; no total score is emitted.'))
    parser.add_argument('submission', type=Path)
    parser.add_argument('--baseline', type=Path, default=DATA.parent / 'reference-baseline.jsonl')
    args = parser.parse_args()
    try:
        metric = load_metric()
        with preflight_zip(args.submission, metric) as checked:
            emit({'G0': 'PASS', 'simulation_started': False})
            baselines = load_baseline(args.baseline)
            ratios = []
            for name, result, seconds in verify_all(checked):
                row = report(name, result, seconds, baselines[name])
                emit(row)
                ratios.append(row['ratio'])
            emit({'geometric_mean': math.prod(ratios) ** (1 / len(ratios)), 'scope': 'fixed public local salt'})
    except Exception as error:
        print(f'REJECT: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
