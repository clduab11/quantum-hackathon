# SPDX-License-Identifier: Apache-2.0
"""Measure v3 checkpoints through the unmodified, hash-checked evaluator."""
from dataclasses import replace
import numpy as np
from tasks.dfthcsos.checks import acceptance_problems
from tasks.dfthcsos.factor_support import prediction, sha256, write_npz


def floor_problems(metrics, ratio):
    problems = acceptance_problems(metrics)
    for name in ('error_1', 'error_2'):
        if not 0 <= metrics[name] <= .0195:
            problems.append(f'{name} misses 19.5 mHa margin')
    if not np.isfinite(metrics['lambda_eff']) or metrics['lambda_eff'] <= 0:
        problems.append('lambda_eff is nonpositive or nonfinite')
    if not np.isfinite(ratio) or ratio < 3.:
        problems.append('modelled ratio below 3.0x or nonfinite')
    return problems


def measure(params, inputs, bits, out, label):
    # Imported only after the driver verifies both package manifests.
    from dfthcsos.verify import native_inputs, evaluate_words, heuristic_costs
    from verifier.score import SubmissionInputs
    from starter.task2_angles.encode import encode_inputs
    from starter.task2_angles.trees import log_depth_tree_edges
    w, offsets, shift, beta = native_inputs(params)
    point = replace(inputs, params=params, w=w, W=offsets, S=shift, beta_1=beta)
    encoder = SubmissionInputs('FeMoCo76o113e', None, params, inputs.ref, w,
                               offsets, shift, beta, inputs.energy_upper)
    edges = log_depth_tree_edges(params['U'].shape[-1])
    words = encode_inputs(encoder, edges, bits)
    metrics = evaluate_words(point, words, edges, bits)
    shape = params['W'].shape
    resources = prediction(76, *shape[:2], bits, heuristic_costs(76, *shape, bits))
    cost = metrics['lambda_eff']*resources['T']*resources['Q']
    ratio = 3355599588.3/cost if cost > 0 else 0.
    file = out/f'{label}-b{bits}.npz'
    write_npz(file, {**params, 'angle_words':words, 'tree_edges':edges,
                     'brot':np.array(bits, dtype=np.int64)})
    return dict(label=label, shape=shape, brot=bits, **metrics, **resources,
                cost=cost, ratio=ratio, file=file.name, sha256=sha256(file),
                problems=floor_problems(metrics, ratio), full_circuit_verified=False)
