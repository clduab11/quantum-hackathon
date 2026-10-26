# SPDX-License-Identifier: Apache-2.0
"""Run the pinned Google (65,60,60) control with the unchanged JAX optimizer."""
import argparse
from pathlib import Path
import sys
import time
import numpy as np
from tasks.dfthcsos.factor_support import BASELINE, checked_inputs, sha256, write_npz, json_text
from .mirror import accelerator, physics, compare


def run(args):
    started = time.monotonic()
    if args.out.exists():
        raise ValueError('output exists; choose a new exclusive --out directory')
    pins = checked_inputs(args.starter)
    for item in pins['competition_files']:
        if sha256(args.competition/item['path']) != item['sha256']:
            raise ValueError('competition SHA-256 mismatch: '+item['path'])
    factor = args.starter/BASELINE  # checked_inputs pins this file, too.
    sys.path[:0] = [str(args.competition/'verifiers'), str(args.competition/'kickmix'),
                   str(args.starter/'starter_kit')]
    device = accelerator()
    if device.platform != 'gpu':
        raise ValueError('this control is GPU-only; TPU requires separate approval')
    inputs, fixed = physics(factor)
    if inputs.w.shape != (65, 60, 60):
        raise ValueError('Google control requires exactly (65,60,60)')
    report = dict(input_sha256=sha256(factor), shape=list(inputs.w.shape), bits=12,
                  device=str(device), device_kind=device.device_kind, fit_seconds=300,
                  steps=32, rate=1e-4, dry_run=not args.execute)
    if not args.execute:
        return report
    import jax
    report.update(jax=jax.__version__, seed=251,
        lock_sha256=sha256(Path(__file__).resolve().parents[3]/'uv.lock'),
        source_hashes={p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')})
    from starter.task2_angles.encode import encode_inputs
    from starter.task2_angles.trees import log_depth_tree_edges
    from verifier.score import SubmissionInputs
    from dfthcsos.verify import evaluate_words
    from .loss import terms, admissible
    from .optimizer import fit
    from .profile import profiler
    from .export import arrays
    from .score import score
    args.out.mkdir(parents=True, exist_ok=False)
    encoder = SubmissionInputs('FeMoCo76o113e', None, inputs.params, inputs.ref,
        inputs.w, inputs.W, inputs.S, inputs.beta_1, inputs.energy_upper)
    edges = np.asarray(log_depth_tree_edges(76))
    words = encode_inputs(encoder, edges, 12)
    params = dict(angles=words.astype(np.float64)/2048, w=inputs.w, offsets=inputs.W)
    with jax.default_device(device):
        params, fixed, edges = jax.device_put((params, fixed, edges), device)
        evaluate = jax.jit(lambda p: terms(p, fixed, edges, 12))
        report['initial'] = {k:float(v) for k,v in evaluate(params).items()}
        report['initial_difference'] = compare(report['initial'], evaluate_words(inputs, words, np.asarray(edges), 12))
        if not bool(admissible(evaluate(params))):
            report.update(control_pass=False, reason='rounded Google start is infeasible; no fit or export')
        else:
            def checkpoint(p, record):
                write_npz(args.out/f"checkpoint-{record['iteration']:04d}.npz", arrays(p, edges, 12, inputs.params))
                with (args.out/'steps.jsonl').open('a') as stream:
                    import json
                    stream.write(json.dumps(record, allow_nan=False)+'\n')
            params, report['training'] = fit(params, evaluate, 300, 32, 1e-4, checkpoint, profiler(fixed, edges, 12))
            exported = arrays(params, edges, 12, inputs.params)
            official_inputs, _ = physics(exported)
            report['numeric'] = evaluate_words(official_inputs, exported['angle_words'], exported['tree_edges'], 12)
            report['export_difference'] = compare(evaluate(params), report['numeric'])
            if not bool(admissible({k:report['numeric'][k] for k in report['initial']})):
                raise ValueError('export is infeasible; no candidate promoted')
            output = args.out/'factor.npz'
            write_npz(output, exported)
            report['factor_sha256'] = sha256(output)
            report['cascade'] = score(output, 12, args.out)
            report['control_pass'] = bool(report['cascade']['metrics'].get('stage3_passed'))
    report['seconds'] = time.monotonic()-started
    (args.out/'report.json').write_text(json_text(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Needs uv sync --group gpu and pinned verifier installation. Default is dry run. '
        'Example: timeout --kill-after=5 1190 uv run --locked --group gpu python -m '
        'tasks.dfthcsos.fit_jax.google_control --starter /home/cld-main/work/vqcc-data/starter-kit '
        '--competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation '
        '--out /tmp/google-control --execute. Writes only a new --out. '
        'Bad pins, missing GPU or verification failure exit nonzero. See GOOGLE_CONTROL.md.'))
    for name in ('starter', 'competition', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        report = run(parser.parse_args())
        print(json_text(report))
        return 0 if report['dry_run'] or report['control_pass'] else 1
    except (ValueError, AssertionError, OSError, RuntimeError) as error:
        print(f'Google control: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
