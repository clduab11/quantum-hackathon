# SPDX-License-Identifier: Apache-2.0
"""Measure the declared public THC factor files with the unmodified competition verifier.

Run from the repo:
    uv run python ledger/evidence/pra245/measure_declared_factors.py \
        --competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation \
        /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz \
        /home/cld-main/work/vqcc-data/inputs/thc/thc_submission.npz

Metrics come from `dfthcsos.verify.evaluate_words` on the file's own `angle_words` (the words the
circuits load). The verifier only accepts words in [0, 2**brot); a signed-gauge file is therefore also
measured with its words reduced mod 2**brot, which encodes the same angles (theta + 2*pi). Costs use
`dfthcsos.verify.heuristic_costs` (SpinFreeData_V1(R, B, C, 76, 10, brot)) plus the ordinary-QROM
ANGLE bound of `tasks.dfthcsos.factor_support.prediction`, for every J the 128-qubit cap allows.
A file without `angle_words` (its words live in its circuits) is given as `file.npz:words.npz`, the
author's published word table; the decoded words are compared with the file's own `U`.
No circuit is built or simulated. Prints JSON; writes nothing.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from tasks.dfthcsos.checks import acceptance_problems  # noqa: E402
from tasks.dfthcsos.factor_support import json_text, sha256  # noqa: E402

BASELINE_COST = 3355599588.3  # the reference cost the repo's ratio divides by (factor_measure.py)
QUBIT_CAP = 128


def angle_rows(n, r, b, brot, heuristic, lambda_eff):
    """Ordinary-QROM ANGLE cost at every word count J that fits the 128-qubit cap."""
    addresses = n + r*b
    selection = (addresses-1).bit_length()
    temporary = selection - 1
    rows = []
    for batch in range(1, n):
        if selection + temporary + batch*brot > QUBIT_CAP:
            break
        families = math.ceil((n-1)/batch)
        angle_t = 2*(addresses-2)*families
        t = int(heuristic['toffoli'] + angle_t)
        q = int(heuristic['persistent_qubits'] + batch*brot + max(heuristic['temporary_qubits'], temporary))
        cost = lambda_eff*t*q if np.isfinite(lambda_eff) else math.inf
        rows.append(dict(J=batch, families=families, angle_qubits=selection+temporary+batch*brot,
                         angle_toffoli=angle_t, T=t, Q=q, cost=cost,
                         ratio=BASELINE_COST/cost if cost > 0 else 0.))
    return rows


def measure(spec, default_bits, evaluate_words, heuristic_costs, load_inputs, passes_accuracy):
    path, _, words_path = str(spec).partition(':')
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: np.array(z[k]) for k in z.files}
    words_source = None
    if 'angle_words' not in arrays and words_path:
        with np.load(words_path, allow_pickle=False) as z:
            arrays['angle_words'] = np.array(z['angle_words'])
        words_source = dict(file=Path(words_path).name, sha256=sha256(words_path))
    shapes = {k: dict(shape=list(v.shape), dtype=str(v.dtype)) for k, v in sorted(arrays.items())}
    r, b, c = arrays['W'].shape
    brot = int(arrays['brot']) if 'brot' in arrays else None
    words = arrays['angle_words']
    if brot is None:
        brot = default_bits  # the width the dataset description states; recorded as undeclared
    inputs = load_inputs(path)
    edges = arrays['tree_edges'].astype(np.int64)
    out = dict(file=Path(path).name, bytes=Path(path).stat().st_size, sha256=sha256(path),
               keys=shapes, R_B_C=[r, b, c], brot=brot, brot_declared='brot' in arrays,
               words_min=int(words.min()), words_max=int(words.max()), words_source=words_source)
    try:
        shipped = evaluate_words(inputs, words, edges, brot)
        out['as_shipped'] = dict(metrics={k: float(v) for k, v in shipped.items()},
                                 problems=acceptance_problems(shipped),
                                 passes_accuracy=bool(passes_accuracy(shipped)))
    except ValueError as error:
        out['as_shipped'] = dict(rejected=str(error))
    canonical = np.mod(words.astype(np.int64), 1 << brot)
    metrics = evaluate_words(inputs, canonical, edges, brot)
    problems = acceptance_problems(metrics)
    lambda_eff = float(metrics['lambda_eff'])
    heuristic = heuristic_costs(76, r, b, c, brot)
    rows = angle_rows(76, r, b, brot, heuristic, lambda_eff)
    best = max(rows, key=lambda row: row['ratio']) if rows else None
    out['mod_2_brot'] = dict(metrics={k: float(v) for k, v in metrics.items()}, problems=problems,
                             passes_accuracy=bool(passes_accuracy(metrics)),
                             words_changed=int(np.count_nonzero(canonical != words)))
    if words_source:
        from dfthcsos.scoreinfra.dfthc_math import reconstruct_u_vectors
        decoded = reconstruct_u_vectors(canonical / (1 << (brot - 1)), edges)[76:].reshape(arrays['U'].shape)
        out['words_source']['max_abs_U_difference'] = float(np.abs(decoded - arrays['U']).max())
        per_vector = np.minimum(np.abs(decoded - arrays['U']).max(axis=-1),
                                np.abs(decoded + arrays['U']).max(axis=-1))  # a vector's sign is a gauge
        out['words_source']['max_abs_U_difference_up_to_sign'] = float(per_vector.max())
    out['heuristic'] = {k: int(v) for k, v in heuristic.items()}
    out['angle_model'] = 'ordinary-QROM upper bound (factor_support.prediction), no ANF/banked claim'
    out['by_J'] = rows
    out['best'] = best
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--competition', type=Path, required=True)
    parser.add_argument('--bits', type=int, default=11, help='word width when a file has no brot key')
    parser.add_argument('files', nargs='+', help='factor .npz, or factor.npz:words.npz')
    args = parser.parse_args()
    sys.path[:0] = [str(args.competition/'kickmix'), str(args.competition/'verifiers')]
    from dfthcsos.verify import evaluate_words, heuristic_costs, load_inputs, passes_accuracy
    results = [measure(p, args.bits, evaluate_words, heuristic_costs, load_inputs, passes_accuracy)
               for p in args.files]
    sys.stdout.write(json_text(dict(verifier=str(args.competition/'verifiers/dfthcsos/verify.py'),
                                    verifier_sha256=sha256(args.competition/'verifiers/dfthcsos/verify.py'),
                                    costs_prepare_sha256=sha256(args.competition/'verifiers/dfthcsos/scoreinfra/costs_prepare.py'),
                                    results=results)))


if __name__ == '__main__':
    main()
