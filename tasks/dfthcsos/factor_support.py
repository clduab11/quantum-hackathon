# SPDX-License-Identifier: Apache-2.0
"""Pinned inputs, conservative ordinary-QROM cost model and deterministic output."""
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np

PIN_FILE = Path(__file__).resolve().parents[2] / 'ledger/manifests/inputs/pra198-google-v4.json'
BASELINE = 'starter_kit/starter/task1_factorization/FeMoco76_65_60_60.npz'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def json_text(value):
    """Strict JSON: undefined physical metrics become null, never NaN tokens."""
    def clean(item):
        if isinstance(item, dict):
            return {k:clean(v) for k,v in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(v) for v in item]
        if isinstance(item, float) and not math.isfinite(item):
            return None
        return item
    return json.dumps(clean(value), indent=2, allow_nan=False)+'\n'


def checked_inputs(root):
    """Refuse missing/modified v4 files before importing their Python source."""
    pins = json.loads(PIN_FILE.read_text())
    for item in pins['files']:
        path = Path(root) / item['path']
        if sha256(path) != item['sha256']:
            raise ValueError(f'input SHA-256 mismatch: {path}; restore pinned starter-kit v4')
    return pins


def prediction(n, r, b, brot, heuristic):
    """Ordinary QROM upper bound, J chosen to fit 128 qubits; no banked claim."""
    addresses = n + r*b
    selection = (addresses-1).bit_length()
    temporary = selection - 1
    batch = min(8, (128-selection-temporary)//brot)
    if batch < 1:
        raise ValueError('ANGLE register exceeds 128 qubits')
    families = (n-2+batch)//batch
    angle_t = 2 * (addresses-2) * families
    words = batch*brot
    return dict(T=int(heuristic['toffoli']+angle_t),
                Q=int(heuristic['persistent_qubits']+words+
                      max(heuristic['temporary_qubits'], temporary)),
                angle_qubits=selection+temporary+words, angle_toffoli=angle_t,
                batch=batch, families=families, model='ordinary-QROM-upper-bound')


def write_npz(path, arrays):
    """Exclusive, sorted ZIP with fixed metadata; rejects nonfinite and oversize arrays."""
    if sum(np.asarray(a).nbytes for a in arrays.values()) > 64*1024*1024:
        raise ValueError('decoded arrays exceed 64 MiB')
    if not all(np.isfinite(a).all() for a in arrays.values()):
        raise ValueError('nonfinite output; no archive written')
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, array in sorted(arrays.items()):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.asarray(array), allow_pickle=False)
            info = zipfile.ZipInfo(name+'.npy', (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            archive.writestr(info, buffer.getvalue())


def markdown(rows):
    lines = ['| R,B,C | bits | error1 Ha | error2 Ha | Lambda | E_gap | lambda_eff | T | Q | ratio | seconds | gate |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        values = [','.join(map(str, r['shape'])), r['brot']]
        values += [f"{r[k]:.6g}" for k in ('error_1','error_2','Lambda','E_gap','lambda_eff','T','Q','ratio','seconds')]
        values += ['PASS' if not r['problems'] else '; '.join(r['problems'])]
        lines.append('| '+' | '.join(map(str, values))+' |')
    return '\n'.join(lines)+'\n'
