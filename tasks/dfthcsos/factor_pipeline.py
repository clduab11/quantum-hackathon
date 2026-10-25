# SPDX-License-Identifier: Apache-2.0
"""Refit pinned Google factors and measure a rank/precision curve; no circuits."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time

# Set before NumPy/BLAS imports. No random initialization, GPU or hidden checkpoint.
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'

import numpy as np
import scipy
from tasks.dfthcsos.checks import acceptance_problems
from tasks.dfthcsos.factor_math import compress, packed_target, refit
from tasks.dfthcsos.factor_offsets import refine_offsets
from tasks.dfthcsos.factor_reseed import regroup
from tasks.dfthcsos.factor_quantized import refit_quantized
from tasks.dfthcsos.factor_progress import checkpoint_callback
from tasks.dfthcsos.factor_support import BASELINE, checked_inputs, json_text, markdown, prediction, sha256, write_npz


def shape(value):
    try:
        result = tuple(map(int, value.split(',')))
        if len(result) != 3 or min(result) < 1:
            raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError('shape must be positive R,B,C, e.g. 32,60,30')


def run(args):
    started = time.monotonic()
    sources = [Path(__file__), *(Path(__file__).parent/name for name in
               ('factor_math.py','factor_offsets.py','factor_support.py','checks.py','gates.py',
                'factor_reseed.py','factor_quantized.py','factor_progress.py','factor_optimizers.py'))]
    source_hashes = {p.name:sha256(p) for p in sources}
    pins = checked_inputs(args.starter)
    for item in pins['competition_files']:
        if sha256(args.competition / item['path']) != item['sha256']:
            raise ValueError(f"competition input changed: {item['path']}; restore pinned package")
    previous = (65, 60, 60)
    for current in args.shapes:
        if current[0] > previous[0]:
            raise ValueError('R must not grow in the shape schedule')
        if any(a > b for a, b in zip(current[1:], previous[1:])):
            available = previous[0] // current[0]
            if current[1] > available*previous[1] or current[2] > min(current[1]+1, available*previous[2]):
                raise ValueError('B/C exceed the available merged basis or SVD rank')
        previous = current
    if args.out.exists():
        raise ValueError('output exists; use a new --out directory (never overwrite a run)')
    if args.steps < 1 or args.offset_steps < 1 or not np.isfinite(args.penalty) or args.penalty < 0:
        raise ValueError('steps must be positive; penalty must be finite and nonnegative')
    if min(args.maxcor, args.quantized_steps, args.checkpoint_every) < 1:
        raise ValueError('maxcor, quantized steps and checkpoint interval must be positive')
    if not np.isfinite(args.learning_rate) or args.learning_rate <= 0:
        raise ValueError('learning rate must be finite and positive')
    if not set(args.quantize_bits).issubset(args.bits):
        raise ValueError('quantize bits must be included in measured --bits')
    if args.dry_run:
        print(json.dumps(dict(pinned_files=len(pins['files']), output=str(args.out),
                              shapes=args.shapes, bits=args.bits, steps=args.steps)))
        return 0
    sys.path[:0] = [str(args.competition/'kickmix'), str(args.competition/'verifiers'),
                   str(args.starter/'starter_kit')]
    from dfthcsos.verify import load_inputs, native_inputs, evaluate_words, heuristic_costs
    from verifier.score import SubmissionInputs as EncoderInputs
    from starter.task2_angles.encode import encode_inputs, angles_to_words, words_to_vectors
    from starter.task2_angles.trees import log_depth_tree_edges, tree_angles
    from tasks.dfthcsos.gates import g2_proxy

    args.out.mkdir(parents=True)
    with np.load(args.starter/BASELINE, allow_pickle=False) as archive:
        params = {k: archive[k].astype(np.float64) for k in archive.files}
    inputs = load_inputs(params)
    params.update({k: inputs.params[k] for k in ('H1_I', 'Hsym_lower')})
    target = packed_target(inputs.ref['tei'], inputs.S)
    edges = log_depth_tree_edges(76)
    rows, stages, chosen = [], [], None
    for index, target_shape in enumerate([(65, 60, 60), *args.shapes]):
        stage_start = time.monotonic()
        fit_info, offset_info = None, None
        if index:
            reshape = regroup if any(a > b for a, b in zip(target_shape, params['W'].shape)) else compress
            params = reshape(params, *target_shape)
            params, fit_info = refit(params, target, args.steps, args.penalty,
                maxcor=args.maxcor, method=args.optimizer, learning_rate=args.learning_rate,
                callback=checkpoint_callback(args.out, index, args.checkpoint_every))
            params, offset_info = refine_offsets(params, inputs, args.offset_steps)
        checkpoint = args.out/f'factors-{index:02d}.npz'
        write_npz(checkpoint, params)
        stage = dict(shape=target_shape, structure=fit_info, offsets=offset_info,
                     refit_seconds=time.monotonic()-stage_start,
                     sha256=sha256(checkpoint), file=checkpoint.name)
        stages.append(stage)
        for bits in args.bits:
            tick = time.monotonic()
            point_params, quantized_fit, quantized_offsets = params, None, None
            point_file = checkpoint
            if index and bits in args.quantize_bits:
                def quantize(u):
                    words = angles_to_words(tree_angles(u.reshape(-1, 76), edges), bits)
                    return words_to_vectors(words, edges, bits).reshape(u.shape)
                point_params, quantized_fit = refit_quantized(params, target,
                    args.quantized_steps, args.penalty, quantize, args.maxcor)
                point_params, quantized_offsets = refine_offsets(point_params, inputs, args.offset_steps)
                point_file = args.out/f'factors-{index:02d}-q{bits}.npz'
                write_npz(point_file, point_params)
            w, offsets, shift, beta = native_inputs(point_params)
            point_inputs = replace(inputs, params=point_params, w=w, W=offsets, S=shift, beta_1=beta)
            encoder = EncoderInputs('FeMoCo76o113e', None, point_params, inputs.ref, w,
                                    offsets, shift, beta, inputs.energy_upper)
            encoded = encode_inputs(encoder, edges, bits)
            metrics = evaluate_words(point_inputs, encoded, edges, bits)
            resources = prediction(76, *target_shape[:2], bits, heuristic_costs(76, *target_shape, bits))
            problems = acceptance_problems(metrics)
            if not np.isfinite(metrics['lambda_eff']):
                problems.append('nonfinite lambda_eff')
            cost = float(metrics['lambda_eff'] * resources['T'] * resources['Q'])
            row = dict(shape=target_shape, brot=bits, **metrics, **resources,
                       cost=cost, ratio=3355599588.3/cost if cost > 0 else 0.,
                       seconds=time.monotonic()-tick, problems=problems,
                       margin_19mHa=not problems and max(metrics['error_1'], metrics['error_2']) <= .019,
                       factor_file=point_file.name, factor_sha256=sha256(point_file),
                       quantized_fit=quantized_fit, quantized_offsets=quantized_offsets)
            encoded_file = args.out/f'encoded-{index:02d}-{bits}.npz'
            write_npz(encoded_file, {**point_params, 'angle_words':encoded, 'tree_edges':edges,
                                     'brot':np.array(bits, dtype=np.int64)})
            row.update(encoded_file=encoded_file.name, encoded_sha256=sha256(encoded_file))
            rows.append(row)
            print(json_text(row), flush=True)
            if not problems and (chosen is None or cost < chosen[0]['cost']):
                chosen = (row, {**point_params, 'angle_words': encoded, 'tree_edges': edges,
                                'brot': np.array(bits, dtype=np.int64)})
            (args.out/'progress.json').write_text(json_text(dict(rows=rows, stages=stages)))
        # Preserve completed evidence if a subsequent stage is interrupted.
        (args.out/'progress.json').write_text(json_text(dict(rows=rows, stages=stages)))
    result = dict(label='own-generated, derived from Google baseline', rows=rows, stages=stages,
                  numpy=np.__version__, scipy=scipy.__version__, python=sys.version,
                  threads=1, initialization='pinned Google baseline; deterministic SVD and norm pruning',
                  settings=vars(args) | {'starter':str(args.starter),'competition':str(args.competition),'out':str(args.out)},
                  input_pins=pins, source_hashes=source_hashes, total_seconds=time.monotonic()-started)
    result['chosen'] = None
    if chosen:
        row, arrays = chosen
        write_npz(args.out/'submission.npz', arrays)
        result['chosen'] = dict(shape=row['shape'], brot=row['brot'], ratio=row['ratio'],
                                sha256=sha256(args.out/'submission.npz'), g2=g2_proxy(args.out))
        if result['chosen']['g2']['status'] != 'PASS':
            raise ValueError('chosen output failed G2; inspect run, do not hand off')
    result['floor_met'] = any(r['margin_19mHa'] and tuple(r['shape']) == args.shapes[-1] for r in rows)
    result['floor_65_met'] = any(r['margin_19mHa'] and tuple(r['shape']) == (65,60,30) and r['brot'] == 12 for r in rows)
    result['floor_32_met'] = any(r['margin_19mHa'] and tuple(r['shape']) == (32,60,30) and r['brot'] == 10 for r in rows)
    if source_hashes != {p.name:sha256(p) for p in sources}:
        raise ValueError('pipeline source changed during run; preserve partial evidence and rerun')
    (args.out/'rank-curve.json').write_text(json_text(result))
    (args.out/'rank-curve.md').write_text(markdown(rows))
    print(json.dumps({k:result[k] for k in ('chosen','floor_met','total_seconds')}), flush=True)
    return 0 if result['floor_met'] else 3


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__, epilog='Exit 0: floor met/dry-run; 3: measured floor miss; 1: error. See REFIT_V2.md.')
    parser.add_argument('--starter', type=Path, required=True, help='downloaded, pinned starter-kit v4 root')
    parser.add_argument('--competition', type=Path, required=True, help='pinned competition package root')
    parser.add_argument('--out', type=Path, required=True, help='new directory for factors, chosen NPZ and curve')
    parser.add_argument('--shapes', type=shape, nargs='+', default=[(65,60,30),(55,60,30),(48,60,30),(42,60,30),(36,60,30),(32,60,30),(32,32,30)])
    parser.add_argument('--bits', type=int, choices=range(7,13), nargs='+', default=list(range(7,13)))
    parser.add_argument('--steps', type=int, default=200, help='optimizer iterations per structural cut')
    parser.add_argument('--offset-steps', type=int, default=200)
    parser.add_argument('--penalty', type=float, default=2e-5, help='D(w) penalty weight')
    parser.add_argument('--maxcor', type=int, default=5, help='L-BFGS history size')
    parser.add_argument('--optimizer', choices=['lbfgs','adam','trust-ncg'], default='lbfgs')
    parser.add_argument('--learning-rate', type=float, default=1e-4, help='Adam step size')
    parser.add_argument('--quantize-bits', type=int, choices=range(7,13), nargs='*', default=[], help='independently fit rounded U at these measured widths')
    parser.add_argument('--quantized-steps', type=int, default=100)
    parser.add_argument('--checkpoint-every', type=int, default=25, help='save unverified structural factors every N iterations')
    parser.add_argument('--dry-run', action='store_true', help='validate pins and schedule; write nothing')
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError, ImportError) as exc:
        print(f'factor pipeline: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
