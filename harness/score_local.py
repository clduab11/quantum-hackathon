"""Preflight a submission ZIP, run full package verifiers, and print the local metric."""
import argparse
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.runtime import DATA, LOCAL_SALT, load_metric
from harness.reference_identity import expected_reference
from harness.verification import emit, fingerprint, report, verify_all
from ledger.gates.g0_preflight import preflight_zip, parse_submission


def load_baseline(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or rows[-1] != {'complete': True}:
        raise ValueError('Incomplete baseline: run harness/calibrate_reference.py successfully first.')
    if rows[0].get('environment') != fingerprint():
        raise ValueError('Baseline environment differs: recalibrate with the same imports and public salt.')
    if rows[0].get('reference_files') != expected_reference():
        raise ValueError('Baseline reference identity differs from committed reference_files; recalibrate.')
    records = rows[1:-1]
    if len(records) != 3 or {r.get('task') for r in records} != {'invsqrt', 'dqi', 'dfthcsos'}:
        raise ValueError('Baseline requires exactly one record per task; duplicates are refused.')
    for row in records:
        verifier = row.get('verifier', {})
        if (row.get('status') != 'PASS' or verifier.get('status') != 'PASS'
                or row.get('full_verification') != {'shot_divisor': 1, 'salt_label': LOCAL_SALT}
                or row.get('cost') != verifier.get('score')):
            raise ValueError('Baseline task lacks matching PASS/full-verification evidence.')
    costs = {r['task']: r['cost'] for r in records}
    if set(costs) != {'invsqrt', 'dqi', 'dfthcsos'} or any(not math.isfinite(v) or v <= 0 for v in costs.values()):
        raise ValueError('Baseline must have finite positive costs for all three tasks.')
    return costs


def score_submission(submission_dir: Path, *, salt_label: str, shot_divisor: int = 1) -> dict:
    """G3 hook. Full shots, fixed public salt, default named local calibration only."""
    try:
        if salt_label != LOCAL_SALT or shot_divisor != 1:
            raise ValueError('Only the fixed public salt and shot_divisor=1 are supported.')
        checked = parse_submission(submission_dir)
        baselines = load_baseline(DATA.parent / 'reference-baseline.jsonl')
        environment = fingerprint()
        tasks = {}
        for name, result, seconds in verify_all(checked):
            report(name, result, seconds, baselines[name])
            tasks[name] = result
        from invsqrt import verify_submission_invsqrt as inv
        from dqi import verify_submission_dqi as dqi
        from dfthcsos import verify as df
        import kickmix
        return {'status': 'PASS', 'kickmix_build_id': environment['files'][kickmix.__file__],
                'qualtran_pin': None,
                'verifier_hashes': {name: environment['files'][module.__file__]
                                    for name, module in [('invsqrt', inv), ('dqi', dqi), ('dfthcsos', df)]},
                'tasks': tasks, 'baseline_costs': baselines,
                'geometric_mean': math.prod(baselines[n] / r['score'] for n, r in tasks.items()) ** (1 / 3)}
    except Exception as error:
        return {'status': f'FAIL: {error}'}


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
