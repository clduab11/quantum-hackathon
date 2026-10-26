# SPDX-License-Identifier: Apache-2.0
"""GPU constraint evaluation for the repository's rotation-angle fitter.

The small cutting-plane linear program uses SciPy/HiGHS on the host. All
3,133,452-row constraint evaluations and violated-row selection use CUDA
float64. Integer verification of the rounded result remains independent.
No saved angle or verifier receipt is an input.
"""
import numpy as np
from scipy.optimize import linprog
from tasks.invsqrt.calibrate import (
    MAX_X, reference_target_tolerance, _angle_key, _exact_margin,
    _estimate, _rewrite,
)
from tasks.invsqrt.peephole import optimize

def _fit(error, tolerance, bits, free, fixed, bound_units, scale=2.0**28):
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required for rotation fitting')
    residual = torch.as_tensor((error.astype(np.float64)+fixed)/scale, device='cuda')
    limit = torch.as_tensor(tolerance.astype(np.float64)/scale, device='cuda')
    matrix_all = torch.as_tensor(bits[:, free].astype(np.float64), device='cuda')
    width = len(free)
    active = set(np.linspace(0, MAX_X-1, 4096, dtype=np.int64).tolist())
    active.update(torch.topk(limit-residual.abs(), 4096, largest=False).indices.cpu().tolist())
    converged = False
    for iteration in range(1, 61):
        chosen = sorted(active)
        block = matrix_all[chosen].cpu().numpy()
        matrix = np.vstack([np.c_[block, np.ones(len(chosen))], np.c_[-block, np.ones(len(chosen))]])
        rhs = torch.cat([limit[chosen]-residual[chosen], limit[chosen]+residual[chosen]]).cpu().numpy()
        result = linprog(np.r_[np.zeros(width), -1.], A_ub=matrix, b_ub=rhs,
                         bounds=[(-bound_units/scale, bound_units/scale)]*width+[(None, None)], method='highs')
        if not result.success:
            raise RuntimeError(result.message)
        delta, margin = result.x[:width], float(result.x[width])
        correction = matrix_all @ torch.as_tensor(delta, device='cuda')
        slack = limit-(residual+correction).abs()
        actual = float(slack.min())
        print(f'GPU calibration LP {iteration}: rows {len(chosen)} lp {margin*scale:.3f} exhaustive {actual*scale:.3f}', flush=True)
        if actual >= margin-1e-9*max(1., abs(margin)):
            converged = True
            break
        added = set(torch.topk(slack, 400, largest=False).indices.cpu().tolist())
        if added.issubset(active):
            break
        active.update(added)
    return np.rint(delta*scale).astype(np.int64), dict(iterations=iteration, lp_converged=converged,
                                                     active_inputs=len(active), device='cuda')

def calibrate(compiled, resources: dict) -> dict:
    """Try the original angles and each single counted drop. Keep the cheapest legal one."""
    rotations = compiled.rotations
    counted = [index for index, rotation in enumerate(rotations) if rotation['counted']]
    if not counted:
        raise RuntimeError('The compiled circuit has no counted rotation')
    bits = np.column_stack([rotation['bits'] for rotation in rotations])
    xs = np.arange(1, MAX_X + 1, dtype=np.int64)
    _target, tolerance = reference_target_tolerance(xs)
    target = _target
    error = (compiled.phase - target).view(np.int64)
    order = sorted(counted, key=lambda index: _angle_key(rotations[index]['theta']))
    candidates = [(), (order[0],)]
    best = None
    trials = []
    for dropped in candidates:
        fixed = np.zeros(MAX_X, dtype=np.float64)
        bound = float(1 << 36)
        for index in dropped:
            units = rotations[index]['units']
            fixed += bits[:, index] * float(-units)
            bound = max(bound, 4.0 * abs(units))
        free = [index for index in counted if index not in dropped]
        rounded, fit_report = _fit(error, tolerance, bits, free, fixed, bound)
        deltas = np.zeros(len(rotations), dtype=np.int64)
        for column, index in enumerate(free):
            deltas[index] = rounded[column]
        for index in dropped:
            deltas[index] = -int(rotations[index]['units'])
        margin, worst = _exact_margin(error, tolerance, bits, deltas)
        kept = len(counted) - len(dropped)
        estimate = _estimate(resources['qubits'], resources['expected_toffoli'], resources['t_like'], kept, margin)
        trial = {'dropped': [int(index) for index in dropped], 'margin_units': margin, 'worst_index': worst, 'rotations': kept, 'fit': fit_report, **estimate}
        trials.append({key: trial[key] for key in ('dropped', 'margin_units', 'rotations', 'ratio')})
        print(f'calibration drop {list(dropped) or 'none'}: margin {margin} rotations {kept} ratio {estimate['ratio']:.6f}', flush=True)
        if margin <= 0:
            continue
        if best is None or estimate['estimated_expected_cost'] < best['estimate']['estimated_expected_cost']:
            best = {'deltas': deltas, 'dropped': set(dropped), 'trial': trial, 'estimate': estimate}
    if best is None:
        raise RuntimeError(f'No calibration kept a positive margin: {trials}')
    lines = compiled.text.splitlines()
    rewritten = _rewrite(lines, rotations, {index: int(best['deltas'][index]) for index in range(len(rotations))}, best['dropped'])
    peepholed, cancelled = optimize(rewritten)
    return {'text': peepholed, 'margin_units': best['trial']['margin_units'], 'worst_x': int(best['trial']['worst_index']) + 1, 'rotations': best['trial']['rotations'], 'dropped_rotation_indexes': best['trial']['dropped'], 'peephole_cancelled': cancelled, 'estimate': best['estimate'], 'trials': trials}
