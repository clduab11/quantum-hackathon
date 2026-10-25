"""Compare merge covariance against pinned source pure math on synthetic data.

Run: uv run python ledger/evidence/pra242/check_source_parity.py /tmp/pra242-provenance
Needs the reviewed source archive extracted there. No loaders or factors run.
Writes nothing; exits nonzero on a hash mismatch or covariance difference.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ['OPENBLAS_NUM_THREADS'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import numpy as np
from scipy.linalg import qr, eigh, solve_triangular
from tasks.dfthcsos.factor_merge import merge_initialize, projectors

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source_root', type=Path)
args = parser.parse_args()
pins = json.loads((Path(__file__).parent/'source-parity.json').read_text())['upstream_source_sha256']
namespace = dict(np=np, time=time, json=json, qr=qr, eigh=eigh, solve_triangular=solve_triangular)
for filename, names in [('structural_train.py', {'projectors', 'columns', 'physical_error', 'omp'}),
                         ('merge_initialize.py', {'initialize'})]:
    source = args.source_root/'rebuild_source'/filename
    if hashlib.sha256(source.read_bytes()).hexdigest() != pins[filename]:
        raise ValueError(f'Hash mismatch: {filename}; restore the reviewed source archive')
    tree = ast.parse(source.read_text())
    defs = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                            and n.name in names], type_ignores=[])
    exec(compile(defs, str(source), 'exec'), namespace)
rng = np.random.default_rng(95101)
u, w = rng.normal(size=(4, 3, 5)), rng.normal(size=(4, 3, 2))*.1
def covariance(u, w):
    x = (projectors(u) @ w).transpose(1, 0, 2).reshape(15, -1)
    return x @ x.T
h = covariance(u, w)
old_u, old_w, _ = namespace['initialize'](u, w, h, 2, 4, 3, sweeps=3)
new, _ = merge_initialize(dict(U=u, W=w, H2_I=np.zeros((4, 2))), h, (2, 4, 3), 3)
error = float(np.max(np.abs(covariance(old_u, old_w)-covariance(new['U'], new['W']))))
if error >= 1e-10:
    raise ValueError(f'Merge covariance differs by {error}; inspect the implementation')
print(json.dumps(dict(status='PASS', max_covariance_difference=error)))
