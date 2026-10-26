# SPDX-License-Identifier: Apache-2.0
"""Validate a pinned, completed v4 continuous stage before restarting QAT."""
import json
from pathlib import Path
import numpy as np
from .factor_support import sha256
from .gpu_fit.geometry import physical_error

ORIGINAL_DRIVER_SHA = '8a5db5feb45f64683008754a046560f19298ae2e756c2d192c29309876a0cb45'


def load_continuous(manifest, digest, input_sha, sources, target):
    if sha256(manifest) != digest:
        raise ValueError('resume manifest hash mismatch; use the recorded SHA-256')
    pins = json.loads(manifest.read_text())
    paths = {key: Path(pins[key]['path']) for key in ('progress', 'factor')}
    for key, path in paths.items():
        if sha256(path) != pins[key]['sha256']:
            raise ValueError(f'resume {key} hash mismatch; preserve the original evidence')
    report = json.loads(paths['progress'].read_text())
    if report['input_sha256'] != input_sha or report['optimizer_seed'] != 95101:
        raise ValueError('resume input or optimizer seed differs from this run')
    expected = {'factor_fit_v4.py': ORIGINAL_DRIVER_SHA, **sources}
    if report['source_hashes'] != expected:
        raise ValueError('resume source differs; only the original v4 driver with unchanged numerical modules is compatible')
    points = [r for r in report['rows'] if r['label'] == 'continuous-best']
    stages = {s['stage']: s for s in report['stages']}
    if len(points) != 1 or 'structural' not in stages:
        raise ValueError('resume requires a completed continuous stage, not an inflight optimizer')
    limits = {'structural': {'limit_steps':8000, 'limit_seconds':700},
              'gauss-newton': {'limit_iterations':300, 'limit_cg':100, 'limit_seconds':450}}
    if stages['structural']['best_error'] > .015 and 'gauss-newton' not in stages:
        raise ValueError('resume requires the completed published GN stage')
    for name in ('structural','gauss-newton'):
        if name not in stages:
            continue
        s = stages[name]
        if any(s.get(k) != v for k,v in limits[name].items()):
            raise ValueError('resume stage used different optimizer budgets')
        if s['stop'] == 'source_time_limit' and s['elapsed'] < s['limit_seconds']:
            raise ValueError('resume stage did not reach its source time limit')
    with np.load(paths['factor'], allow_pickle=False) as z:
        params = {k: np.array(z[k]) for k in z.files}
    point = points[0]
    error = physical_error(params['U'], params['W'], target)
    if list(params['W'].shape) != point['shape'] or not np.isfinite(error) or abs(error-point['detail']['continuous_error']) > 1e-12:
        raise ValueError('resume raw checkpoint does not reproduce the recorded continuous result')
    return params, dict(manifest_sha256=digest, progress_sha256=pins['progress']['sha256'],
        checkpoint_sha256=pins['factor']['sha256'], recomputed_error=error,
        stages=report['stages'], prior_seconds=point['seconds'],
        note='Completed continuous stages retained; full QAT and postprocessing restart with seed95101')
