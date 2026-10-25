# SPDX-License-Identifier: Apache-2.0
"""Run a fixed factor-experiment plan sequentially, with logs and completion records.

Example: python -m tasks.dfthcsos.run_experiments --plan PLAN.json --out NEW_DIR
Add --dry-run to validate without writes. Requires the pinned inputs named in
PLAN.json and the repository Python environment. Run from a committed snapshot.
Exit 0: every job completed (including measured misses); 1: operational error;
2: invalid plan/output. No shell, circuit, network, credential or upload actions.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from tasks.dfthcsos.factor_support import json_text, sha256


def validate(plan):
    names = set()
    for job in plan['jobs']:
        name, args = job['name'], job['args']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) or name in names:
            raise ValueError('job names must be unique lowercase names, not paths')
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError('job args must be a list of strings')
        if any(a.split('=')[0] in {'--out','--starter','--competition','--dry-run'} for a in args):
            raise ValueError('job args cannot override fixed input/output paths or dry-run')
        names.add(name)
    if not names or not plan.get('starter') or not plan.get('competition'):
        raise ValueError('plan needs jobs and explicit starter/competition roots')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        validate(plan)
        if args.out.exists():
            raise ValueError('output exists; use a new directory')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json_text(dict(jobs=[j['name'] for j in plan['jobs']], out=str(args.out))))
        return 0
    args.out.mkdir(parents=True)
    records = []
    (args.out/'plan.json').write_text(json_text(plan))
    for job in plan['jobs']:
        command = [sys.executable, '-m', 'tasks.dfthcsos.factor_pipeline',
                   '--starter', plan['starter'], '--competition', plan['competition'],
                   '--out', str(args.out/job['name']), *job['args']]
        started = time.monotonic()
        record = dict(name=job['name'], command=command, status='running',
                      plan_sha256=sha256(args.plan))
        records.append(record)
        (args.out/'jobs.json').write_text(json_text(records))
        with (args.out/(job['name']+'.log')).open('x') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        record.update(exit_code=result.returncode, seconds=time.monotonic()-started,
                      status='complete' if result.returncode in (0,3) else 'error')
        (args.out/'jobs.json').write_text(json_text(records))
        if record['status'] == 'error':
            print(f"experiment {job['name']} failed; inspect its log", file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
