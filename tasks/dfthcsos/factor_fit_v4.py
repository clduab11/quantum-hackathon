# SPDX-License-Identifier: Apache-2.0
"""Full published GPU method at the declared THC shape; see FIT_V4.md."""
import argparse
import os
from pathlib import Path
import sys
import time

# Set before NumPy/PyTorch imports. No verifier seed or salt is changed.
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '2'
os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'

import numpy as np
from tasks.dfthcsos.factor_support import BASELINE, checked_inputs, sha256, json_text
from tasks.dfthcsos.factor_gpu import check_cuda

PUBLIC_SHA = '809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5'


def intake(args):
    if args.out.exists():
        raise ValueError('output exists; use a new --out directory; checkpoints are never replaced')
    pins = checked_inputs(args.starter)
    for item in pins['competition_files']:
        if sha256(args.competition/item['path']) != item['sha256']:
            raise ValueError(f"competition input hash mismatch: {item['path']}")
    google_hash = next(item['sha256'] for item in pins['files'] if item['path'] == BASELINE)
    if args.sha256 not in (PUBLIC_SHA, google_hash) or sha256(args.factor) != args.sha256:
        raise ValueError('factor SHA-256 is not the declared THC input or pinned Google baseline')
    with np.load(args.factor, allow_pickle=False) as z:
        params = {k: np.array(z[k]) for k in z.files}
    lane = 'declared' if args.sha256 == PUBLIC_SHA else 'google'
    if lane == 'declared' and (params['W'].shape != (1, 496, 384) or args.source_bits != 11):
        raise ValueError('declared input must be (1,496,384), with source-bits 11')
    return pins, params, lane


def run(args):
    pins, params, lane = intake(args)
    gpu = check_cuda()  # Even a dry run refuses CPU fallback.
    if args.dry_run:
        print(json_text(dict(lane=lane, gpu=gpu, input_sha256=args.sha256,
                            shape=[1,496,384], bits=[11,8], out=str(args.out))))
        return 0
    import torch
    from types import SimpleNamespace
    from tasks.dfthcsos.gpu_fit import native, words, continuous, quantize
    from tasks.dfthcsos.gpu_fit.postprocess import prepare, postprocess, repair_two_body
    from tasks.dfthcsos.gpu_fit.reporting import Reporter
    from tasks.dfthcsos.gpu_fit.geometry import physical_error
    from tasks.dfthcsos.factor_merge import merge_initialize
    torch.set_num_threads(2)
    torch.manual_seed(95101)
    torch.cuda.manual_seed_all(95101)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.cuda.reset_peak_memory_stats()
    sys.path[:0] = [str(args.competition/'verifiers'), str(args.competition/'kickmix')]
    from dfthcsos.verify import load_inputs
    from dfthcsos.scoreinfra import dfthc_math
    inputs = load_inputs(params)
    params.update({k: inputs.params[k] for k in ('H1_I', 'Hsym_lower')})
    context = SimpleNamespace(inputs=inputs, reference=inputs.ref,
        fixed_shifts={k:params[k] for k in ('H1_I', 'Hsym_lower')},
        energy_upper=inputs.energy_upper, math=dfthc_math, packed_target=None)
    target = native.packed_target(context, params)
    params['tree_edges'] = quantize.EDGES.copy() if 'tree_edges' not in params else params['tree_edges']
    if not np.array_equal(params['tree_edges'], quantize.EDGES):
        raise ValueError('QAT requires the published log-depth tree')
    sources = [Path(__file__), *sorted((Path(__file__).parent/'gpu_fit').glob('*.py'))]
    hashes = {str(p.relative_to(Path(__file__).parent)): sha256(p) for p in sources}
    args.out.mkdir(parents=True)
    reporter = Reporter(args.out, context, dict(lane=lane, input_sha256=args.sha256,
        input_path=str(args.factor), source_hashes=hashes, gpu=gpu, input_pins=pins,
        optimizer_seed=95101, verifier_seed=None, schedule='published R6 methods adapted to THC, 11 then 8',
        boundaries='CUDA continuous/GN/QAT/two-body repair; source NumPy/SciPy QR/barrier/gauge/one-body helpers'))
    if lane == 'declared':
        reporter.point('input', params, 11, {'unmodified_declared_words': True})
    else:
        params, info = merge_initialize(params, target, (1,496,384), 8)
        reporter.report['stages'].append(dict(stage='google-merge', **info))
        reporter.point('google-merge', prepare(context, params, 11), 11)
    u, w, info = continuous.structural(params['U'], params['W'], target,
                                      reporter.continuous_callback(10, params))
    params = {**params, 'U':u, 'W':w}
    reporter.report['stages'].append(dict(stage='structural', **info)); reporter.save()
    if physical_error(u, w, target) > .015:
        u, w, info = continuous.gauss_newton(u, w, target, reporter.continuous_callback(20, params))
        params = {**params, 'U':u, 'W':w}
        reporter.report['stages'].append(dict(stage='gauss-newton', **info)); reporter.save()
    continuous_error = physical_error(u, w, target)
    reporter.point('continuous-best', prepare(context, params, 11), 11, {'continuous_error':continuous_error})
    if continuous_error <= .030:
        for bits in (11, 8):
            start = time.monotonic()
            i, j = np.tril_indices(76)
            tg = SimpleNamespace(n=76, Ts=torch.tensor(target, dtype=torch.float32, device='cuda'),
                ri=torch.tensor(i,device='cuda'), ci=torch.tensor(j,device='cuda'),
                scale=torch.tensor(np.where(i==j,1.,np.sqrt(2.)),dtype=torch.float32,device='cuda'))
            callback = reporter.continuous_callback(30+bits, params, bits)
            body, weights = quantize.quantize(torch.tensor(params['U'],dtype=torch.float32,device='cuda'),
                torch.tensor(params['W'],dtype=torch.float32,device='cuda'), tg, brot=bits,
                kappa=0., steps=800, final_steps=1600, probes=4,
                fracs=(.2,.4,.6,.75,.85,.92,.97,1.),
                log=lambda msg: print(msg,flush=True), callback=lambda u,w,s:callback(u,w,{'freeze_stage':s}))
            data = prepare(context, {**params,'W':weights}, bits, body)
            reporter.point('qat', data, bits, {'seconds':time.monotonic()-start})
            save = lambda label,data,detail: reporter.point(label,data,bits,detail)
            data = postprocess(context, data, bits, save)
            metrics = native.evaluate_words(context, data, bits)
            if .020 < metrics['error_2'] < .030:
                data = repair_two_body(context, data, bits, save)
                data = postprocess(context, data, bits, save, physical_iters=150, joint_iters=60)
            reporter.point('final', data, bits)
            # Task-specific progressive 11 -> 8 continuation (source driver used independent bit branches).
            params = data
    reporter.report.update(complete=True, continuous_error=continuous_error,
        passed_8bit=any(r['bits']==8 and not r['problems'] for r in reporter.report['rows']),
        quantisation='completed' if continuous_error<=.030 else 'source_30mHa_gate_failed')
    if hashes != {str(p.relative_to(Path(__file__).parent)): sha256(p) for p in sources}:
        raise ValueError('fitting source changed during run; retain partial evidence and repeat')
    reporter.save()
    (args.out/'report.json').write_text(json_text(reporter.report))
    return 0 if reporter.report['passed_8bit'] else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog='Requires uv sync --group gpu, pinned starter/competition files, and declared factor hash. '
               'Only --out is written. Exit 0 pass/dry-run, 3 measured schedule negative, 1 error. '
               'Example commands and stage budgets: tasks/dfthcsos/FIT_V4.md.')
    for flag in ('starter','competition','factor','out'):
        parser.add_argument('--'+flag, type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--source-bits', type=int, default=11)
    parser.add_argument('--dry-run', action='store_true', help='validate input hashes and CUDA without writing')
    try:
        return run(parser.parse_args())
    except (ValueError, OSError, RuntimeError, ImportError, ArithmeticError) as exc:
        print(f'factor fit v4: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
