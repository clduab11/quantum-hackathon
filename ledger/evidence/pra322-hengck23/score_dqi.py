"""dqi-only local scorer: python score_dqi.py CIRCUIT [SALT|--seed N ...]"""
import sys,json,time,argparse
from pathlib import Path
sys.path.insert(0,'.')
from harness.runtime import LOCAL_SALT, load_metric
ap=argparse.ArgumentParser();ap.add_argument('path',type=Path);ap.add_argument('--salt',default=LOCAL_SALT);ap.add_argument('--seed',type=int,default=None)
a=ap.parse_args()
metric=load_metric()
from dqi import verify_submission_dqi as dqi
spec=dqi.ProblemSpecDQI.benchmark_instance()
circ=metric.read_circuit(a.path,spec.n+spec.m)
t=time.time()
res=dqi.verify(circ,spec,seed=a.seed) if a.seed is not None else dqi.verify(circ,spec,salt=a.salt)
print(json.dumps(dict(path=str(a.path),salt=None if a.seed is not None else a.salt,seed=a.seed,status=res.get('status'),Q=res.get('num_qubits'),mean_T=res.get('toffoli_count'),value_errors=res.get('value_errors'),phase_errors=res.get('phase_errors'),score=res.get('score'),seconds=round(time.time()-t,1))))
