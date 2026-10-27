# SPDX-License-Identifier: Apache-2.0
"""PRA-294 J=4 compiler smoke and the 8.0x chemistry floor on the PRA-293 bundle; no gate waivers."""
from pathlib import Path

import numpy as np

CHEMISTRY_FLOOR = 8.0


def g1_smoke(submission_dir):
    """Recompile batch 0 from the shipped factor; it must equal the shipped bytes and load the words."""
    import kickmix as km
    from dfthcsos.scoreinfra.circuits import recover_words_from_circuits
    from tasks.dfthcsos.c59 import FIRST_STAGE_SEEDS, INPUT_SHA256, compile_batch
    from tasks.dfthcsos.generate import batch_deltas, sha256_file
    folder = Path(submission_dir) / 'dfthcsos'
    if sha256_file(folder / 'submission.npz') != INPUT_SHA256:
        return {'status': 'FAIL: shipped factor is not the pinned C59 input'}
    with np.load(folder / 'submission.npz', allow_pickle=False) as archive:
        words = archive['angle_words']
    delta = batch_deltas(words, 4)[0]
    circuit, report = compile_batch(delta, FIRST_STAGE_SEEDS[0])
    shipped = km.Circuit.from_file(folder / 'angle_k_0.kmb', format='kmb')
    if str(shipped) != str(circuit):
        return {'status': 'FAIL: recompiled angle_k_0 differs from the shipped circuit'}
    actual, _, _ = recover_words_from_circuits([circuit], num_vectors=len(delta), num_angles=4, seed=294)
    if not np.array_equal(actual, delta):
        return {'status': 'FAIL: streamed lookup changed words'}
    if report['num_qubits'] > 128:
        return {'status': f"FAIL: angle_k_0 uses {report['num_qubits']} qubits"}
    return {'status': 'PASS', **report}


def g4_floor(ctx):
    """PRA-293's G4 (strict improvement, dqi and invsqrt pins), then chemistry >= 8.0x."""
    from tasks.dqi.fused.gates import g4_floor_on_port
    result = g4_floor_on_port(ctx)
    if result['status'] != 'PASS':
        return result
    ratio = ctx.manifest.tasks['dfthcsos'].ratio
    if ratio is None or not ratio >= CHEMISTRY_FLOOR:
        return {**result, 'status': f'FAIL: chemistry ratio {ratio} is below {CHEMISTRY_FLOOR}'}
    return {**result, 'chemistry_ratio': ratio, 'chemistry_floor': CHEMISTRY_FLOOR}
