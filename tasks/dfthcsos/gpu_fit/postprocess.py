# SPDX-License-Identifier: Apache-2.0
"""Published fixed-grid QR, offsets, column gauge, barrier and word repair stages."""
import numpy as np
from . import native, words
from .fixed import fixed_word_fit, joint_norm
from .gauge import deterministic_column_gauge
from .integer import ExactAnglePolisher
from .one_body import polish as polish_one_body


def prepare(context, params, bits, body_words=None):
    data = {k: np.array(v, copy=True) for k, v in params.items()}
    n = data['U'].shape[-1]
    if body_words is None:
        body_words = native.encode_vectors(data['U'].reshape(-1, n), data['tree_edges'], bits)
    data['angle_words'] = np.concatenate([np.zeros((n, n-1), dtype=np.int64), body_words])
    data['angle_words'], _ = words.canonicalize_words(data['angle_words'], data['tree_edges'], bits)
    data = words.restore_factor(data, bits)
    return native.refresh_one_body(context, data, bits)


def postprocess(context, params, bits, checkpoint, *, physical_iters=350, joint_iters=100):
    data = words.restore_factor(params, bits)
    target = native.packed_target(context, data)
    data['W'], physical = fixed_word_fit(data['U'], data['W'], target, maxiter=physical_iters)
    data = native.refresh_one_body(context, data, bits)
    checkpoint('fixed-qr', data, physical)
    for index in range(2):
        data, offsets = native.optimize_effective_norm(context, data, bits, maxiter=400, gap_margin=.0002)
        checkpoint(f'offset-{index}', data, offsets)
        data, gauge = deterministic_column_gauge(data, plane_sweeps=3)
        data = native.refresh_one_body(context, data, bits)
        checkpoint(f'gauge-{index}', data, gauge)
    if physical['after_E2'] < .019999:
        data, joint = joint_norm(context, data, bits, maxiter=joint_iters, stages=3)
        checkpoint('joint-barrier', data, joint)
    else:
        checkpoint('joint-barrier-skipped', data, {'reason': 'physical_error_above_source_entry_gate'})
    data = native.refresh_one_body(context, data, bits)
    data['angle_words'], _ = words.canonicalize_words(data['angle_words'], data['tree_edges'], bits)
    data = words.restore_factor(data, bits)
    metrics = native.evaluate_words(context, data, bits)
    if metrics['error_1'] > .0195:
        data, repair = polish_one_body(context, data, bits, target=.0195, max_steps=2000, seconds=60)
        checkpoint('one-body-repair', data, repair)
    return data


def repair_two_body(context, params, bits, checkpoint):
    """Full source budgets, CUDA exact-rank-two proposals, fixed-word refits."""
    data = native.copy_data(params)
    h = native.packed_target(context, data)
    for stage in range(2):
        polisher = ExactAnglePolisher(data['angle_words'], data['W'], data['tree_edges'], h,
                                     brot=bits, backend='torch', device='cuda')
        report = polisher.polish(seconds=90, max_steps=256, top_k=128, batch_size=128,
            ranking='gauss_newton', audit_every=32, proposals_per_gradient=16)
        data['angle_words'] = polisher.export_words()
        data = words.restore_factor(data, bits)
        data = native.refresh_one_body(context, data, bits)
        checkpoint(f'integer-{stage}', data, report)
        data['W'], report = fixed_word_fit(data['U'], data['W'], h, maxiter=150)
        data = native.refresh_one_body(context, data, bits)
        checkpoint(f'integer-qr-{stage}', data, report)
        if report['after_E2'] < .0195:
            break
    return data
