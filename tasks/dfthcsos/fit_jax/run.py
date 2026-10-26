# SPDX-License-Identifier: Apache-2.0
"""Fit the declared public factor on GPU, then run the official circuit cascade."""
import argparse
import os
from pathlib import Path
import sys
import time
os.environ.setdefault('XLA_PYTHON_CLIENT_PREALLOCATE','false')
from tasks.dfthcsos.factor_support import write_npz,sha256,json_text
from tasks.dfthcsos.factor_progress import checkpoint_callback
from .mirror import accelerator,intake,physics,compare


def run(args):
    import jax
    from .loss import terms,admissible
    from .optimizer import fit
    from .export import arrays
    from .profile import profiler
    from .score import score
    started = time.monotonic()
    device = accelerator()
    inputs,params,fixed,edges,_ = intake(args.starter,args.competition,args.factor)
    if args.out.exists():
        raise ValueError('output already exists; choose a new exclusive --out directory')
    if args.dry_run:
        return dict(dry_run=True,device=str(device),out=str(args.out),bits=args.bits,
                    fit_seconds=args.fit_seconds,steps=args.steps,writes='checkpoints, factor, logs and circuit cascade below --out')
    args.out.mkdir(parents=True,exist_ok=False)
    save = checkpoint_callback(args.out,0,1)
    with jax.default_device(device):
        params,fixed,edges = jax.device_put((params,fixed,edges),device)
        evaluate = jax.jit(lambda p:terms(p,fixed,edges,args.bits))
        initial = evaluate(params)
        if not bool(admissible(initial)):
            raise ValueError('rounded start is infeasible; no optimizer step or candidate export permitted')
        def checkpoint(p,record):
            save(arrays(p,edges,args.bits,inputs.params))
            with (args.out/'steps.jsonl').open('a') as stream:
                import json
                stream.write(json.dumps(record,allow_nan=False)+'\n')
            print(json_text(record),flush=True)
        params,training = fit(params,evaluate,args.fit_seconds,args.steps,args.rate,
                              checkpoint,profiler(fixed,edges,args.bits))
        exported = arrays(params,edges,args.bits,inputs.params)
        from dfthcsos.verify import evaluate_words
        official_inputs,_ = physics(exported)
        numeric = evaluate_words(official_inputs,exported['angle_words'],exported['tree_edges'],args.bits)
        difference = compare(evaluate(params),numeric)
        if not bool(admissible({k:numeric[k] for k in initial})):
            raise ValueError('official exported metrics are infeasible; no candidate promoted')
        factor = args.out/'factor.npz'
        write_npz(factor,exported)
    report = dict(device=str(device),device_kind=device.device_kind,seed=251,bits=args.bits,
                  shape=list(exported['W'].shape),factor_sha256=sha256(factor),
                  initial={k:float(v) for k,v in initial.items()},training=training,
                  numeric=numeric,export_mirror_difference=difference)
    report['cascade'] = score(factor,args.bits,args.out)
    report['seconds'] = time.monotonic()-started
    report['smoke_pass'] = (training['accepted_steps'] > 0 and
        bool(report['cascade']['metrics'].get('stage3_passed')) and
        report['cascade']['metrics'].get('ratio',0) >= 4 and report['seconds'] <= 900)
    with (args.out/'report.json').open('x') as stream:
        stream.write(json_text(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,epilog=(
        'Needs pinned public inputs, GPU dependencies and installed local verifier paths. '
        'Example: python -m tasks.dfthcsos.fit_jax.run --starter /home/cld-main/work/vqcc-data/starter-kit '
        '--competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation '
        '--factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz --out /tmp/b1-smoke --dry-run. '
        'Remove --dry-run to fit and verify. Writes only a NEW output directory. '
        'Missing GPU, unsafe start, failed verification or missed smoke threshold exits nonzero.'))
    for name in ('starter','competition','factor','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--bits',type=int,choices=(8,11,12),default=11)
    parser.add_argument('--fit-seconds',type=float,default=300)
    parser.add_argument('--steps',type=int,default=32)
    parser.add_argument('--rate',type=float,default=1e-4)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    if args.fit_seconds <= 0 or args.steps < 1 or not 0 < args.rate <= .01:
        parser.error('fit-seconds and steps must be positive; rate must be in (0, .01]')
    try:
        report = run(args)
        print(json_text(report))
        return 0 if report.get('dry_run') or report['smoke_pass'] else 1
    except (ValueError,AssertionError,OSError,RuntimeError) as error:
        print(f'JAX fit: {error}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
