# SPDX-License-Identifier: Apache-2.0
"""Measure smaller public-factor proposals on GPU; reject before fitting or promotion."""
import argparse
from pathlib import Path
import sys
import time
from tasks.dfthcsos.factor_support import json_text
from .mirror import accelerator,intake,physics,compare


def probe(starter,competition,factor,shapes):
    import jax
    from .loss import terms,admissible
    from .reduce import reduce
    from .export import arrays
    device = accelerator()
    inputs,p,f,e,_ = intake(starter,competition,factor)
    from dfthcsos.verify import evaluate_words
    rows = []
    with jax.default_device(device):
        p,f,e = jax.device_put((p,f,e),device)
        for shape in shapes:
            started = time.monotonic()
            proposal = jax.jit(lambda x:reduce(x,shape))(p)
            for bits in (12,11,8):
                actual = jax.jit(lambda x:terms(x,f,e,bits))(proposal)
                exported = arrays(proposal,e,bits,inputs.params)
                official_inputs,_ = physics(exported)
                expected = evaluate_words(official_inputs,exported['angle_words'],exported['tree_edges'],bits)
                differences = compare(actual,expected)
                rows.append(dict(shape=list(shape),bits=bits,admissible=bool(admissible(actual)),
                    metrics=expected,max_mirror_error=max(differences.values()),seconds=time.monotonic()-started))
    return dict(device=str(device),points=rows,full_circuit_verified=False,fit_performed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__,epilog=(
        'Needs the mirror GPU dependencies and pinned inputs. Example: python -m '
        'tasks.dfthcsos.fit_jax.probe_shapes --starter /home/cld-main/work/vqcc-data/starter-kit '
        '--competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation '
        '--factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz --shape 1,496,383. '
        'Read-only JSON output; no factor promotion or circuit score. Exit 1 if all proposals fail '
        'the hard physical guard, 2 for invalid arguments. Pipe stdout to a new evidence file.'))
    for name in ('starter','competition','factor'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--shape',action='append',required=True,help='smaller R,B,C, e.g. 1,496,383; repeat to probe more shapes')
    args = parser.parse_args()
    try:
        shapes = [tuple(map(int,s.split(','))) for s in args.shape]
        report = probe(args.starter,args.competition,args.factor,shapes)
        print(json_text(report))
        if not any(p['admissible'] for p in report['points']):
            print('JAX shape probe: every proposal rejected; retain the feasible start',file=sys.stderr)
            return 1
        return 0
    except (ValueError,AssertionError,OSError,RuntimeError) as error:
        print(f'JAX shape probe: {error}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
