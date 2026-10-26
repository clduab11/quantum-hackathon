# SPDX-License-Identifier: Apache-2.0
"""Measure 1,000 independent +/-1 LSB jumps on the pinned v8 start; JSON stdout only."""
import argparse
from pathlib import Path
import sys
import time
import numpy as np
from .mirror import accelerator, intake, compare


def samples(shape):
    """500 distinct coordinates, both signs, fixed seed; never accumulate flips."""
    indices = np.random.default_rng(251).choice(np.prod(shape), 500, replace=False)
    return [(int(i//shape[1]), int(i%shape[1]), sign) for i in indices for sign in (-1, 1)]


def summarize(records):
    result = {}
    for key in ('error_2', 'E_gap', 'lambda_eff'):
        values = np.array([r['delta'][key] for r in records])
        result[key] = dict(median=float(np.median(values)), p95=float(np.quantile(values, .95)),
                           absolute_p95=float(np.quantile(abs(values), .95)),
                           minimum=float(values.min()), maximum=float(values.max()))
    return result


def measure(args):
    import jax
    import jax.numpy as jnp
    from .loss import terms
    device = accelerator()
    started = time.monotonic()
    inputs, params, fixed, edges, _ = intake(args.starter, args.competition, args.factor)
    from dfthcsos.verify import evaluate_words
    records = []
    with jax.default_device(device):
        p, f, e = jax.device_put((params, fixed, edges), device)
        evaluate = jax.jit(lambda q: terms(q, f, e, 11))
        def point(q):
            m = {k: float(v) for k, v in evaluate(q).items()}
            m['lambda_eff'] = float(jnp.sqrt(m['E_gap']*(2*m['Lambda']-m['E_gap'])))
            return m
        baseline = point(p)
        words = np.rint(params['angles']*1024).astype(np.int64)
        compare({k:v for k,v in baseline.items() if k != 'lambda_eff'}, evaluate_words(inputs, words, edges, 11))
        for index, (row, column, sign) in enumerate(samples(words.shape)):
            if time.monotonic()-started > 1100:
                raise RuntimeError('jump budget exhausted; no complete distribution; retain partial stderr progress')
            q = {**p, 'angles': p['angles'].at[row, column].add(sign/1024)}
            actual = point(q)
            record = dict(row=row, column=column, sign=sign,
                          delta={k:actual[k]-baseline[k] for k in ('error_2','E_gap','lambda_eff')})
            # Independent official checks for both signs and both row classes.
            if index < 2 or (row < 76 and not any(r.get('one_body_mirror') for r in records)):
                changed = words.copy()
                changed[row,column] = (changed[row,column]+sign) % 2048
                record['mirror'] = compare({k:v for k,v in actual.items() if k != 'lambda_eff'},
                                           evaluate_words(inputs, changed, edges, 11))
                record['one_body_mirror'] = row < 76
            records.append(record)
            if (index+1) % 100 == 0:
                print(f'{index+1}/1000 jumps in {time.monotonic()-started:.2f}s', file=sys.stderr, flush=True)
    return dict(seed=251, bits=11, device=device.device_kind, baseline=baseline,
                count=len(records), summary=summarize(records), records=records,
                seconds=time.monotonic()-started, fitting=False, full_circuit_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog='Requires pinned starter/competition/factor paths and GPU group. Example: python -m tasks.dfthcsos.fit_jax.word_jumps --starter /home/cld-main/work/vqcc-data/starter-kit --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation --factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz. Missing GPU, bad hashes or mirror mismatch exits nonzero. No files are written.')
    for name in ('starter','competition','factor'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    from tasks.dfthcsos.factor_support import json_text
    print(json_text(measure(args)))


if __name__ == '__main__':
    main()
