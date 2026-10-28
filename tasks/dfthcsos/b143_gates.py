# SPDX-License-Identifier: Apache-2.0
"""PRA-321 full-XOR smoke and the 9.7x chemistry floor on the submission-010 bundle; no gate waivers."""
from pathlib import Path

import numpy as np

CHEMISTRY_FLOOR = 9.7


def g1_smoke(submission_dir):
    """Recompile batch 0 from the shipped factor; it must equal the shipped bytes and load the words."""
    import kickmix as km
    from dfthcsos.scoreinfra.circuits import recover_words_from_circuits
    from tasks.dfthcsos.b143 import INPUT_SHA256, batch_deltas, compile_batch, load_plans
    from tasks.dfthcsos.generate import sha256_file
    folder = Path(submission_dir) / 'dfthcsos'
    if sha256_file(folder / 'submission.npz') != INPUT_SHA256:
        return {'status': 'FAIL: shipped factor is not the pinned B143 input'}
    with np.load(folder / 'submission.npz', allow_pickle=False) as archive:
        words = archive['angle_words']
    delta = batch_deltas(words)[:, 0]
    circuit, _, report = compile_batch(delta, load_plans()[0])
    shipped = km.Circuit.from_file(folder / 'angle_k_0.kmb', format='kmb')
    if str(shipped) != str(circuit):
        return {'status': 'FAIL: recompiled angle_k_0 differs from the shipped circuit'}
    actual, _, _ = recover_words_from_circuits([circuit], num_vectors=len(delta), num_angles=5, seed=321)
    if not np.array_equal(actual, delta):
        return {'status': 'FAIL: full-XOR lookup changed words'}
    if report['num_qubits'] > 128:
        return {'status': f"FAIL: angle_k_0 uses {report['num_qubits']} qubits"}
    return {'status': 'PASS', **report}


def g4_floor(ctx):
    """Submission-010's G4 (strict improvement, dqi and invsqrt pins), then chemistry >= 9.7x."""
    from tasks.dfthcsos.c59_gates import g4_floor as c59_floor
    result = c59_floor(ctx)
    if result['status'] != 'PASS':
        return result
    ratio = ctx.manifest.tasks['dfthcsos'].ratio
    if ratio is None or not ratio >= CHEMISTRY_FLOOR:
        return {**result, 'status': f'FAIL: chemistry ratio {ratio} is below {CHEMISTRY_FLOOR}'}
    return {**result, 'chemistry_ratio': ratio, 'chemistry_floor': CHEMISTRY_FLOOR}
