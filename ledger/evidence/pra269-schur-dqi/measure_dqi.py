"""PRA-269: measure the public Schur dqi.kmb with the unmodified official dqi verifier (fixed public salt, full shots).
Measurement only; the circuit is never part of a bundle. No salt or seed search."""
import hashlib, json, sys, time
from pathlib import Path
from harness.runtime import LOCAL_SALT, load_metric
from harness.verification import fingerprint, report

path = Path(sys.argv[1])
load_metric()
from dqi import verify_submission_dqi as dqi
baseline = None
for line in open('/home/cld-main/work/vqcc-data/reference-baseline.jsonl'):
    r = json.loads(line)
    if r.get('task') == 'dqi':
        baseline = r['cost']
fp = fingerprint()
print(json.dumps({'circuit': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'bytes': path.stat().st_size, 'salt': LOCAL_SALT, 'baseline_cost': baseline,
                  'verifier_files': {k: v for k, v in fp['files'].items() if '/dqi/' in k or k.endswith('kickmix/__init__.py')},
                  'metric_sha256': fp['metric_sha256'], 'python': fp['python'], 'packages': fp['packages']}), flush=True)
start = time.monotonic()
import kickmix as km
result = dqi.verify(km.Circuit.from_file(str(path), format='kmb'), dqi.ProblemSpecDQI.benchmark_instance(), salt=LOCAL_SALT)
rec = report('dqi', result, time.monotonic() - start, baseline)
print(json.dumps(rec, default=str), flush=True)
