# SPDX-License-Identifier: Apache-2.0
"""Run a bounded, Google-only public-method feasibility fit. See FIT_V3.md."""
import argparse
import os
from pathlib import Path
import sys
import time

for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '2'

import numpy as np
import scipy
from scipy.optimize import minimize
from tasks.dfthcsos.factor_math import packed_target, structure_value_grad
from tasks.dfthcsos.factor_merge import merge_initialize, projectors
from tasks.dfthcsos.factor_gauss_newton import refine
from tasks.dfthcsos.factor_measure import measure
from tasks.dfthcsos.factor_offsets import refine_offsets
from tasks.dfthcsos.factor_progress import checkpoint_callback
from tasks.dfthcsos.factor_support import BASELINE, checked_inputs, json_text, sha256, write_npz


def train(params, target, steps, callback):
    u, w = params['U'], params['W']
    start = np.r_[u.ravel(), w.ravel()]
    def unpack(flat):
        raw = flat[:u.size].reshape(u.shape)
        return {**params, 'U':raw / np.linalg.norm(raw, axis=-1, keepdims=True),
                'W':flat[u.size:].reshape(w.shape).copy()}
    def objective(flat):
        loss, grad = structure_value_grad(flat, u.shape, w.shape, target, 2e-6)
        return 1000*loss, 1000*grad
    opt = minimize(objective, start, jac=True, method='L-BFGS-B',
                   callback=lambda x: callback(unpack(x)),
                   options=dict(maxiter=steps, maxcor=20, maxls=30,
                                ftol=1e-13, gtol=1e-10))
    return unpack(opt.x), dict(iterations=int(opt.nit), evaluations=int(opt.nfev),
                               objective=float(opt.fun), converged=bool(opt.success),
                               message=str(opt.message), method='SciPy L-BFGS-B; no bounds')


def run(args):
    if min(args.steps, args.gn_steps, args.cg_steps, args.offset_steps, args.checkpoint_every) < 1 or args.sweeps < 0:
        raise ValueError('iteration limits must be positive; sweeps nonnegative')
    if args.out.exists():
        raise ValueError('output exists; choose a new --out directory')
    pins = checked_inputs(args.starter)
    for item in pins['competition_files']:
        if sha256(args.competition/item['path']) != item['sha256']:
            raise ValueError(f"competition input changed: {item['path']}; restore pinned package")
    shape = (6, 144, 127) if args.shape == 'r6' else (1, 496, 384)
    if args.dry_run:
        print(json_text(dict(shape=shape, steps=args.steps, gn_steps=args.gn_steps,
                             pinned_files=len(pins['files']), out=str(args.out))))
        return 0
    sys.path[:0] = [str(args.competition/'kickmix'), str(args.competition/'verifiers'),
                   str(args.starter/'starter_kit')]
    from dfthcsos.verify import load_inputs
    sources = sorted(Path(__file__).parent.glob('factor_*.py'))
    source_hashes = {p.name:sha256(p) for p in sources}
    started = time.monotonic()
    args.out.mkdir(parents=True)
    with np.load(args.starter/BASELINE, allow_pickle=False) as z:
        params = {k:z[k].astype(np.float64) for k in z.files}
    inputs = load_inputs(params)
    params.update({k:inputs.params[k] for k in ('H1_I', 'Hsym_lower')})
    target = packed_target(inputs.ref['tei'], inputs.S)
    report = dict(shape=shape, initialization='pinned Google baseline only', seed=None,
                  deterministic=True, numpy=np.__version__, scipy=scipy.__version__,
                  python=sys.version, threads=2, input_pins=pins, source_hashes=source_hashes,
                  settings={k:str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
                  stages=[], rows=[], complete=False)
    def persist():
        (args.out/'progress.json').write_text(json_text(report))
    def stage(label, p, info):
        x = (projectors(p['U']) @ p['W']).transpose(1, 0, 2).reshape(len(target), -1)
        error = float(np.linalg.norm(x @ x.T - target))
        path = args.out/f'{label}.npz'
        write_npz(path, p)
        row = dict(stage=label, continuous_error=error, file=path.name,
                   sha256=sha256(path), details=info, elapsed=time.monotonic()-started)
        report['stages'].append(row)
        persist()
        print(json_text({k:v for k,v in row.items() if k != 'details'}), flush=True)
        return error
    persist()
    params, info = merge_initialize(params, target, shape, args.sweeps,
                                    checkpoint_callback(args.out, 0, 1))
    stage('merge', params, info)
    params, info = train(params, target, args.steps,
                         checkpoint_callback(args.out, 1, args.checkpoint_every))
    stage('structural', params, info)
    params, info = refine(params, target, args.gn_steps, args.cg_steps,
                          checkpoint_callback(args.out, 2, 1))
    error = stage('gauss-newton', params, info)
    # Preserve the source driver's 30 mHa gate. No inaccurate point is passed
    # off as a completed progressive-quantisation or joint-barrier experiment.
    report['quantisation_training'] = ('SKIPPED_CONTINUOUS_ABOVE_30mHa' if error > .030
                                      else 'NOT_IMPLEMENTED_REQUIRES_CONTINUATION')
    params, info = refine_offsets(params, inputs, args.offset_steps)
    stage('offsets', params, info)
    for bits in (10, 11, 12):
        row = measure(params, inputs, bits, args.out, 'rounded-diagnostic')
        report['rows'].append(row)
        persist()
        print(json_text(row), flush=True)
    if source_hashes != {p.name:sha256(p) for p in sources}:
        raise ValueError('fitting source changed during run; preserve partial run and repeat')
    report.update(complete=True, seconds=time.monotonic()-started,
                  floor_met=any(not row['problems'] for row in report['rows']))
    persist()
    (args.out/'report.json').write_text(json_text(report))
    print(json_text(dict(floor_met=report['floor_met'], continuous_error=error,
                         quantisation_training=report['quantisation_training'])), flush=True)
    return 0 if report['floor_met'] else (3 if error > .030 else 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog='Exit 0: floor/dry-run; 3: measured continuous-stage miss; 4: needs quantisation continuation; 1: error.')
    parser.add_argument('--starter', type=Path, required=True, help='pinned Google starter-kit v4 root')
    parser.add_argument('--competition', type=Path, required=True, help='pinned competition package root')
    parser.add_argument('--out', type=Path, required=True, help='new directory; never overwritten')
    parser.add_argument('--shape', choices=('r6', 'thc'), default='r6')
    parser.add_argument('--sweeps', type=int, default=8)
    parser.add_argument('--steps', type=int, default=500, help='structural L-BFGS iterations')
    parser.add_argument('--gn-steps', type=int, default=30)
    parser.add_argument('--cg-steps', type=int, default=30)
    parser.add_argument('--offset-steps', type=int, default=400)
    parser.add_argument('--checkpoint-every', type=int, default=25)
    parser.add_argument('--dry-run', action='store_true', help='validate inputs and print schedule without writes')
    try:
        return run(parser.parse_args())
    except (ValueError, OSError, ImportError, np.linalg.LinAlgError) as exc:
        print(f'factor fit v3: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
