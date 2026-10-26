"""Measure our regenerated decoder once with the unmodified fixed-salt verifier."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from harness.runtime import LOCAL_SALT, load_metric
from harness.verification import fingerprint, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('circuit', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    baseline = next(json.loads(line)['cost'] for line in args.baseline.read_text().splitlines()
                    if json.loads(line).get('task') == 'dqi')
    load_metric()
    from dqi import verify_submission_dqi as dqi
    import kickmix as km

    with args.circuit.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'sha256': digest, 'bytes': args.circuit.stat().st_size,
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True)),
        'salt': LOCAL_SALT, 'baseline_cost': baseline, 'fingerprint': fingerprint()}), flush=True)
    started = time.monotonic()
    result = dqi.verify(km.Circuit.from_file(str(args.circuit), format='kmb'),
        dqi.ProblemSpecDQI.benchmark_instance(), salt=LOCAL_SALT)
    print(json.dumps(report('dqi', result, time.monotonic()-started, baseline)), flush=True)
    if result.get('status') != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
