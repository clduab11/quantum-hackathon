# SPDX-License-Identifier: Apache-2.0
"""Regenerate the public-source invsqrt experiment; the fallback is unchanged.

Usage: uv run --group gpu python -m tasks.invsqrt.public_port.generate --out DIR
No cached table, circuit, angle file, or rewrite file is an input.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

from .model import Config, certificate


def resources(circuit):
    stats = circuit.operation_statistics()
    depth = 0
    discount = 0.
    for line in str(circuit).splitlines():
        opcode = line.split(' ', 1)[0]
        if opcode == 'PUSH_CONDITION':
            depth += 1
        elif opcode == 'POP_CONDITION':
            depth -= 1
        elif opcode in ('CCX', 'CSWAP') and depth:
            discount += 1 - 2**-depth
    return dict(qubits=int(circuit.num_qubits), static_toffoli=int(stats.num_toffoli_like),
                expected_toffoli=int(stats.num_toffoli_like)-discount,
                t_like=int(stats.num_t_like), rotations=int(stats.num_z_pow(min_clifford_hierarchy_level=4)))


def build_from_fit(fitted):
    cfg = Config()
    tables = {(e,a): fitted['rows'][128*e+a] for e in range(2) for a in range(128)}
    # Recompute instead of trusting a passed flag supplied by a caller.
    proof = certificate(cfg, tables)
    if not proof['passed']:
        raise ValueError(f'G2 integer mirror failed before circuit construction: {proof}')
    print(json.dumps(dict(stage='integer_mirror', **proof)), flush=True)

    import kickmix as km
    from tasks.invsqrt import affine, calibrate
    from . import schedule, calibration

    raw, split = schedule.build(cfg, tables, group_bits=None, interpolation=fitted['interpolation'],
                                main_lookup='anf', affine=True, joint_norm=False)
    print(json.dumps(dict(stage='raw', **resources(raw))), flush=True)
    compiled = affine.compile_circuit(raw)
    phase = calibrate.assert_phase_matches(compiled, cfg, tables)
    before = resources(km.Circuit(compiled.text))
    print(json.dumps(dict(stage='compiled', phase=phase, **before)), flush=True)
    calibrated = calibration.calibrate(compiled, before)
    circuit = km.Circuit(calibrated['text'])
    final = resources(circuit)
    estimate = calibrate._estimate(final['qubits'], final['expected_toffoli'], final['t_like'],
                                   final['rotations'], calibrated['margin_units'])
    buffer = io.BytesIO()
    circuit.to_file(buffer, format='kmb')
    data = buffer.getvalue()
    report = dict(integer_mirror=proof, phase=phase, split=split, raw=resources(raw),
                  compiled=before, rewrites=dict(compiled.rewrites), final=final, estimate=estimate,
                  calibration={k:v for k,v in calibrated.items() if k != 'text'},
                  sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                  parent_version=361726742, tables=fitted, full_verification_required=True)
    return data, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    from .fit import fit_tables
    fitted = fit_tables()
    data, report = build_from_fit(fitted)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/'invsqrt.kmb').write_bytes(data)
    (args.out/'build-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('tables','calibration')}), flush=True)


if __name__ == '__main__':
    main()
