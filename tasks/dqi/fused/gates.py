# SPDX-License-Identifier: Apache-2.0
"""G1 for the fused decoder: source pins, then exact complete-domain arithmetic checks."""
import json
from pathlib import Path
import subprocess
import sys

PORT = Path(__file__).resolve().parent


def g1_smoke(submission_dir):
    from ..generate_fused import check_pins
    try:
        pinned = check_pins()
        proc = subprocess.run([sys.executable, '-B', str(PORT / 'smoke.py')], capture_output=True,
                              text=True, timeout=600, check=False)
        if proc.returncode:
            return {'status': f'FAIL: smoke exited {proc.returncode}: {proc.stderr[-800:]}'}
        report = json.loads(proc.stdout.strip().splitlines()[-1])
    except (SystemExit, Exception) as error:
        return {'status': f'FAIL: {type(error).__name__}: {error}'}
    return {**report, 'pinned_files': pinned}


EXPECTED_SHA256 = '7beea291a5de36ef2b4fb50585b2f8d7cce02d3c575b491cf5dcc93e9d9655f6'
DQI_FLOOR = 54.7


def g4_floor(ctx):
    """Strict improvement and the chemistry floor, then the PRA-293 dqi floor."""
    from tasks.dfthcsos.rustad_gates import g4_floor as chemistry_floor
    result = chemistry_floor(ctx)
    if result['status'] != 'PASS':
        return result
    dqi = ctx.manifest.tasks['dqi']
    if dqi.files.get('dqi.kmb') != EXPECTED_SHA256:
        return {**result, 'status': f"FAIL: dqi.kmb {dqi.files.get('dqi.kmb')} is not {EXPECTED_SHA256}"}
    if dqi.ratio is None or not dqi.ratio >= DQI_FLOOR:
        return {**result, 'status': f'FAIL: dqi ratio {dqi.ratio} is below {DQI_FLOOR}'}
    return {**result, 'dqi_ratio': dqi.ratio, 'dqi_floor': DQI_FLOOR}


INVSQRT_FLOOR = 13.2377


def g4_floor_on_port(ctx):
    """g4_floor, then #62's public-port invsqrt bytes at their 13.2377× floor (pra293-fused-invsqrt)."""
    from tasks.invsqrt.public_port.gates import PORT_SHA256
    result = g4_floor(ctx)
    if result['status'] != 'PASS':
        return result
    invsqrt = ctx.manifest.tasks['invsqrt']
    if invsqrt.files.get('invsqrt.kmb') != PORT_SHA256:
        return {**result, 'status': f"FAIL: invsqrt.kmb {invsqrt.files.get('invsqrt.kmb')} is not {PORT_SHA256}"}
    if invsqrt.ratio is None or not invsqrt.ratio >= INVSQRT_FLOOR:
        return {**result, 'status': f'FAIL: invsqrt ratio {invsqrt.ratio} is below {INVSQRT_FLOOR}'}
    return {**result, 'invsqrt_ratio': invsqrt.ratio, 'invsqrt_floor': INVSQRT_FLOOR}
