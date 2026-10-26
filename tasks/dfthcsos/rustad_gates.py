"""PRA-280 compiler smoke and measured chemistry floor; no gate waivers."""
import numpy as np
from tasks.dfthcsos.paired_qrom import build_qrom


def g1_smoke(submission_dir):
    from dfthcsos.scoreinfra.circuits import recover_words_from_circuits
    words = np.arange(64 * 3, dtype=np.int64).reshape(64, 3) % 128
    words |= (words & 64) << 1
    circuit, report = build_qrom(words, 8)
    actual, _, _ = recover_words_from_circuits([circuit], num_vectors=64, num_angles=3, seed=280)
    if not np.array_equal(actual, words):
        return {'status': 'FAIL: paired lookup changed words'}
    return {'status': 'PASS', **report}


def g4_floor(ctx):
    from ledger.gates.checks import g4_strict_improvement
    result = g4_strict_improvement(ctx)
    if result['status'] != 'PASS':
        return result
    ratio = ctx.manifest.tasks['dfthcsos'].ratio
    if ratio is None or not ratio >= 7.679:
        return {**result, 'status': f'FAIL: chemistry ratio {ratio} is below 7.679'}
    return {**result, 'chemistry_ratio': ratio, 'chemistry_floor': 7.679}
