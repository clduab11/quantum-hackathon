"""The v10 verifier calls and reporting, with full shot counts and one public salt."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
import time

from harness.runtime import LOCAL_SALT, METRIC_SHA256
from harness.costs import dfthcsos_cost, dqi_cost, effective_lambda, invsqrt_cost


def fingerprint():
    import kickmix
    from dqi import verify_submission_dqi as dqi
    from invsqrt import verify_submission_invsqrt as inv
    from dfthcsos import verify as df
    files = {Path(kickmix.__file__)}
    for module in (dqi, inv, df):
        files.update(Path(module.__file__).parent.rglob('*.py'))
        files.update(Path(module.__file__).parent.rglob('*.npz'))
        files.update(Path(module.__file__).parent.rglob('*.fcidump'))
    hashes = {}
    for path in sorted(files):
        with path.open('rb') as f:
            hashes[str(path)] = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'salt': LOCAL_SALT, 'metric_sha256': METRIC_SHA256,
            'python': sys.version, 'files': hashes,
            'packages': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'pandas')}}


def verify_all(checked):
    from invsqrt import verify_submission_invsqrt as inv
    from dqi import verify_submission_dqi as dqi
    from dfthcsos import verify as df
    calls = {
        'invsqrt': lambda: inv.verify(checked['invsqrt'], inv.ProblemSpecInvSqrt.for_n_p(10), salt=LOCAL_SALT),
        'dqi': lambda: dqi.verify(checked['dqi'], dqi.ProblemSpecDQI.benchmark_instance(), salt=LOCAL_SALT),
        'dfthcsos': lambda: df.verify(checked['angles'], checked['factorization'], checked['tree_edges'],
                                    salt=LOCAL_SALT, shots_per_address=df.SHOTS_PER_ADDRESS),
    }
    for name, call in calls.items():
        print(f'Verifying {name} (full shots)...', file=sys.stderr, flush=True)
        start = time.monotonic()
        result = call()
        if result.get('status') != 'PASS' or not math.isfinite(result['score']) or result['score'] <= 0:
            raise ValueError(f'{name}: verifier did not return a finite positive PASS cost')
        yield name, result, time.monotonic() - start


def report(name, result, seconds, baseline=None):
    # T means synthesized total T gates for invsqrt; Toffoli resource T for the other tasks.
    t = result['toffoli_count']
    if name == 'invsqrt':
        from invsqrt.verify_submission_invsqrt import rotation_t_count
        t = result['t_count'] + (result['rotation_count'] * rotation_t_count(result['rotation_eps'])
                                 if result['rotation_count'] else 0)
    if name == 'invsqrt':
        computed = invsqrt_cost(result['num_qubits'], result['toffoli_count'], t)
    elif name == 'dqi':
        computed = dqi_cost(result['num_qubits'], t, result['repetition_factor'])
    else:
        metrics = result['metrics']
        multiplier = effective_lambda(metrics['Lambda'], metrics['E_gap'])
        computed = dfthcsos_cost(result['num_qubits'], t, multiplier)
    if not math.isclose(computed, result['score'], rel_tol=1e-12):
        raise ValueError(f'{name}: accounting formula differs from verifier cost')
    return {'task': name, 'status': result['status'], 'Q': result['num_qubits'],
            'full_verification': {'shot_divisor': 1, 'salt_label': LOCAL_SALT},
            'Toffolis': result['toffoli_count'], 'T': t,
            'T_unit': 'synthesized_T_gates' if name == 'invsqrt' else 'Toffoli_resource',
            'failures': result.get('value_errors', 0) + result.get('phase_errors', 0),
            'epsilon_plus': result.get('effective_error_rate'), 'cost': result['score'],
            'ratio': baseline / result['score'] if baseline is not None else None,
            'seconds': seconds, 'verifier': result}


def emit(record):
    print(json.dumps(record, allow_nan=False), flush=True)
