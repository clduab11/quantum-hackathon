# SPDX-License-Identifier: Apache-2.0
"""G1/G2 hooks for a pinned public invsqrt circuit (46 qubits at most).

``g1_invsqrt``/``g2_invsqrt`` check the syed3000 v12 pin (SOURCE.json); ``g1_mix_invsqrt``/
``g2_mix_invsqrt`` check the three-source mix pin (MIX-20261113.json, D-HERMES-20261113-01).

dqi and dfthcsos reuse the existing hooks unchanged (tasks.dqi.gates, tasks.dfthcsos.gates).
Those two G1 smokes are builder smoke tests that ignore the submission directory, and the G2
proxies read the shipped circuit/factor. Byte identity of every shipped file with its pin is
enforced by G5 (vendored_circuit, byte-identical rebuild), not by those hooks.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from .generate import PIN, load_pin

MIX_PIN_NAME = 'MIX-20261113.json'

SALT = 'PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'
MAX_QUBITS = 46
REGISTER_WIDTH = 22
# Same bounded proxy as tasks.invsqrt.vendored.gates.g2_proxy.
SPEC_N_P = 10
SPEC_MAX_X = 1536
SPEC_SHOTS_PER_X = 1


def mix_pin() -> dict:
    return load_pin(MIX_PIN_NAME)


def _pinned_invsqrt(pin: dict | None = None) -> dict:
    (entry,) = [f for f in (PIN if pin is None else pin)['files'] if f['task'] == 'invsqrt']
    return entry


def _checked_path(submission_dir, pin: dict | None = None) -> tuple[Path | None, str | None, dict]:
    """The shipped invsqrt.kmb if it is the pinned file, streamed so the whole file is never loaded."""
    entry = _pinned_invsqrt(pin)
    path = Path(submission_dir) / entry['output']
    try:
        digest, size = hashlib.sha256(), 0
        with path.open('rb') as stream:
            while chunk := stream.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        return None, f'FAIL: {exc}', entry
    if size != entry['size_bytes'] or digest.hexdigest() != entry['sha256']:
        return None, (f'FAIL: SHA-256 {digest.hexdigest()} ({size} bytes) does not match pinned '
                      f'{entry["sha256"]} ({entry["size_bytes"]} bytes)'), entry
    return path, None, entry


def g1_invsqrt(submission_dir, pin: dict | None = None) -> dict:
    import kickmix as km
    path, problem, entry = _checked_path(submission_dir, pin)
    if problem:
        return {'status': problem}
    circuit = km.Circuit.from_file(str(path))
    registers = circuit.register_data
    if list(registers) != ['x'] or len(list(registers['x'])) != REGISTER_WIDTH:
        return {'status': f'FAIL: expected the single {REGISTER_WIDTH}-qubit x register'}
    if circuit.num_qubits > MAX_QUBITS:
        return {'status': f'FAIL: qubit count {circuit.num_qubits} exceeds {MAX_QUBITS}'}
    return {'status': 'PASS', 'sha256': entry['sha256'], 'num_qubits': circuit.num_qubits,
            'max_qubits': MAX_QUBITS,
            'static_toffoli': int(circuit.operation_statistics().num_toffoli_like)}


def _bounded_spec(spec_cls):
    return replace(spec_cls.for_n_p(SPEC_N_P), max_x=SPEC_MAX_X, shots_per_x=SPEC_SHOTS_PER_X)


def g2_invsqrt(submission_dir, pin: dict | None = None) -> dict:
    smoke = g1_invsqrt(submission_dir, pin)
    if smoke['status'] != 'PASS':
        return smoke
    import kickmix as km
    from invsqrt.verify_submission_invsqrt import ProblemSpecInvSqrt, verify
    circuit = km.Circuit.from_file(str(Path(submission_dir) / _pinned_invsqrt(pin)['output']))
    result = verify(circuit, _bounded_spec(ProblemSpecInvSqrt), salt=SALT, max_workers=1)
    return {**result, 'parity': False, 'scope': f'x=1..{SPEC_MAX_X}, one shot per input'}


def g1_mix_invsqrt(submission_dir) -> dict:
    return g1_invsqrt(submission_dir, mix_pin())


def g2_mix_invsqrt(submission_dir) -> dict:
    return g2_invsqrt(submission_dir, mix_pin())
