# SPDX-License-Identifier: Apache-2.0
"""Candidate-specific checks for the accepted 63-qubit circuit."""
from dataclasses import replace
from pathlib import Path

from ledger.gates.checks import g4_strict_improvement
from ledger.run_manifest import read_manifest
from .generate import SHA256, checked_bytes

SALT = 'PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'


def g1_smoke(submission_dir):
    import kickmix as km
    path = Path(submission_dir) / 'invsqrt.kmb'
    try:
        checked_bytes(path)
    except (OSError, ValueError) as exc:
        return {'status': f'FAIL: {exc}'}
    circuit = km.Circuit.from_file(str(path))
    registers = circuit.register_data
    if list(registers) != ['x'] or len(list(registers['x'])) != 22:
        return {'status': 'FAIL: expected the single 22-qubit x register'}
    if circuit.num_qubits > 63:
        return {'status': 'FAIL: qubit count exceeds 63'}
    return {'status': 'PASS', 'sha256': SHA256, 'num_qubits': circuit.num_qubits,
            'static_toffoli': int(circuit.operation_statistics().num_toffoli_like)}


def g2_proxy(submission_dir):
    import kickmix as km
    from invsqrt.verify_submission_invsqrt import ProblemSpecInvSqrt, verify
    smoke = g1_smoke(submission_dir)
    if smoke['status'] != 'PASS':
        return smoke
    circuit = km.Circuit.from_file(str(Path(submission_dir) / 'invsqrt.kmb'))
    spec = replace(ProblemSpecInvSqrt.for_n_p(10), max_x=1536, shots_per_x=1)
    result = verify(circuit, spec, salt=SALT, max_workers=1)
    return {**result, 'parity': False, 'scope': 'x=1..1536, one shot per input'}


def g4_floor(ctx):
    result = g4_strict_improvement(ctx)
    if result['status'] != 'PASS':
        return result
    manifest = ctx.manifest
    if manifest.parent_candidate_id != 'pra309-chem-8-143-60':
        return {'status': 'FAIL: parent is not the submission-011 bundle'}
    parent = read_manifest(ctx.manifests_root / 'candidates' /
                           f'{manifest.parent_candidate_id}.json')
    for task in ('dqi', 'dfthcsos'):
        if manifest.tasks[task].files != parent.tasks[task].files:
            return {'status': f'FAIL: {task} changed from submission-011'}
    invsqrt = manifest.tasks['invsqrt']
    if invsqrt.files != {'invsqrt.kmb': SHA256}:
        return {'status': 'FAIL: invsqrt is not the accepted source'}
    for task, floor in (('invsqrt', 20.0), ('dqi', 54.7), ('dfthcsos', 9.7)):
        ratio = manifest.tasks[task].ratio
        if ratio is None or not ratio >= floor:
            return {'status': f'FAIL: {task} ratio {ratio} below {floor}'}
    return {**result, 'invsqrt_floor': 20.0, 'unchanged_tasks': ['dqi', 'dfthcsos']}
