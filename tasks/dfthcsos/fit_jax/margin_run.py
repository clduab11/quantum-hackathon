# SPDX-License-Identifier: Apache-2.0
"""Run bounded Phase M from v8; promote only a margin-qualified official PASS."""
import argparse
import json
from pathlib import Path
import sys
import time
from .mirror import accelerator, intake, physics, compare
from tasks.dfthcsos.factor_support import write_npz, sha256, json_text
from tasks.dfthcsos.factor_progress import checkpoint_callback


def run(args):
    import jax
    from .loss import terms
    from .margin_loss import targets, eligible
    from .margin_optimizer import fit, RATES
    from .export import arrays
    from .score import score
    started = time.monotonic()
    device = accelerator()
    inputs, params, fixed, edges, _ = intake(args.starter,args.competition,args.factor)
    jumps = json.loads(args.jumps.read_text())
    if jumps.get('count') != 1000 or jumps.get('seed') != 251 or jumps.get('bits') != 11:
        raise ValueError('need the complete seed-251 11-bit jump diagnostic')
    if args.out.exists():
        raise ValueError('output exists; choose a new exclusive --out directory')
    with jax.default_device(device):
        p,f,e = jax.device_put((params,fixed,edges),device)
        evaluate = jax.jit(lambda q: terms(q,f,e,11))
        initial = {k:float(v) for k,v in evaluate(p).items()}
        compare(initial,jumps['baseline'])
        target = targets(jumps['summary'],initial)
        if target['m2'] >= .02:
            raise ValueError('measured jump margin leaves no nonnegative error2 target; escalate the measured limit')
        if args.dry_run:
            return dict(dry_run=True,device=device.device_kind,target=target,out=str(args.out),rates=RATES)
        args.out.mkdir(parents=True,exist_ok=False)
        save = checkpoint_callback(args.out,1,1)
        def checkpoint(q,record):
            save(arrays(q,e,11,inputs.params))
            with (args.out/'steps.jsonl').open('a') as stream:
                stream.write(json.dumps(record,allow_nan=False)+'\n')
            print(json_text(record),flush=True)
        selected,best,training = fit(p,evaluate,target,args.fit_seconds,args.steps,checkpoint)
        report = dict(seed=251,bits=11,shape=list(p['w'].shape),device=device.device_kind,
            input_sha256=sha256(args.factor),jump_sha256=sha256(args.jumps),target=target,rates=RATES,
            initial=initial,training=training,best_metrics={k:float(v) for k,v in evaluate(best).items()},
            source_hashes={x.name:sha256(x) for x in Path(__file__).parent.glob('*.py')},phase_m_pass=False)
        save(arrays(best,e,11,inputs.params))  # explicitly unverified best-penalty state
        if selected is not None:
            exported = arrays(selected,e,11,inputs.params)
            from dfthcsos.verify import evaluate_words
            official_inputs,_ = physics(exported)
            numeric = evaluate_words(official_inputs,exported['angle_words'],exported['tree_edges'],11)
            report['mirror'] = compare(evaluate(selected),numeric)
            if not bool(eligible(numeric,target)):
                raise ValueError('official hard-rounded margins failed; no factor promoted')
            candidate = args.out/'unverified-candidate.npz'
            write_npz(candidate,exported)
            report['numeric'], report['cascade'] = numeric, score(candidate,11,args.out)
            passed = bool(report['cascade']['metrics'].get('stage3_passed'))
            ratio = report['cascade']['metrics'].get('ratio',0)
            report['phase_m_pass'] = passed and ratio >= 4.10 and time.monotonic()-started <= 1200
            if report['phase_m_pass']:
                write_npz(args.out/'factor.npz',exported)
                report['factor_sha256'] = sha256(args.out/'factor.npz')
        report['seconds'] = time.monotonic()-started
        with (args.out/'report.json').open('x') as stream:
            stream.write(json_text(report))
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,epilog='Needs GPU group, pinned public inputs, local verifier paths and word_jumps JSON. Example: python -m tasks.dfthcsos.fit_jax.margin_run --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz --jumps /tmp/jumps.json --out /tmp/phase-m --dry-run. Remove --dry-run to write a NEW output directory. Exit 1 on missing prerequisites or unmet margin/official score; no infeasible factor is promoted. Use an outer timeout of 1200 seconds.')
    for name in ('starter','competition','factor','jumps','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--fit-seconds',type=float,default=900)
    parser.add_argument('--steps',type=int,default=1000)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    if not 0 < args.fit_seconds <= 900 or not 1 <= args.steps <= 1000:
        parser.error('fit-seconds must be in (0,900], steps in [1,1000]; longer runs require review')
    result = run(args)
    print(json_text(result))
    return 0 if result.get('dry_run') or result['phase_m_pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
