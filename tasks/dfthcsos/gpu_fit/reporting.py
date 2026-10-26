# SPDX-License-Identifier: Apache-2.0
"""Exclusive factor snapshots and unchanged-verifier measurements for GPU fits."""
import time
from datetime import datetime, timezone
import numpy as np
import torch
from tasks.dfthcsos.checks import acceptance_problems
from tasks.dfthcsos.factor_progress import checkpoint_callback
from tasks.dfthcsos.factor_support import json_text, sha256, write_npz
from . import native


def predict(shape, bits):
    from dfthcsos.verify import heuristic_costs
    r, b, c = shape
    heuristic = heuristic_costs(76, r, b, c, bits)
    addresses = 76 + r*b
    select = (addresses-1).bit_length()
    temp = select-1
    layouts = []
    for batch in range(1, (128-select-temp)//bits+1):
        angle = 2*(addresses-2)*((75+batch-1)//batch)
        t = int(heuristic['toffoli']+angle)
        q = int(heuristic['persistent_qubits']+batch*bits+max(temp, heuristic['temporary_qubits']))
        layouts.append(dict(J=batch, T=t, Q=q, angle_qubits=select+temp+batch*bits))
    if not layouts:
        raise ValueError('no ordinary ANGLE layout fits 128 qubits')
    return {**min(layouts, key=lambda x: x['T']*x['Q']),
            'model': 'ordinary-QROM upper bound; not circuit verification'}


class Reporter:
    def __init__(self, out, context, header):
        self.out, self.context = out, context
        self.started = time.monotonic()
        self.report = {**header, 'rows': [], 'stages': [], 'complete': False}
        self.save()

    def save(self):
        tmp = self.out/'progress.tmp'
        tmp.write_text(json_text(self.report))
        tmp.replace(self.out/'progress.json')

    def point(self, label, data, bits, detail=None):
        from .words import restore_factor
        metrics = native.evaluate_words(self.context, data, bits)
        resources = predict(data['W'].shape, bits)
        cost = metrics['lambda_eff']*resources['T']*resources['Q']
        index = len(self.report['rows'])
        path = self.out/f'{index:04d}-{label}-b{bits}.npz'
        write_npz(path, {**data, 'brot': np.array(bits, dtype=np.int64)})
        problems = acceptance_problems(metrics)
        row = dict(label=label, shape=list(data['W'].shape), bits=bits, **metrics, **resources,
            predicted_ratio=3355599588.3/cost if np.isfinite(cost) and cost > 0 else None,
            seconds=time.monotonic()-self.started, gpu_peak_bytes=torch.cuda.max_memory_allocated(),
            measured_utc=datetime.now(timezone.utc).isoformat(), file=path.name, sha256=sha256(path),
            problems=problems, margin_19_5_mha=metrics['error_1']<=.0195 and metrics['error_2']<=.0195,
            detail=detail or {}, full_circuit_verified=False)
        self.report['rows'].append(row)
        self.save()
        print(json_text(row), flush=True)
        # An accepted factor is reloaded and measured independently before handoff.
        if bits == 8 and not problems:
            with np.load(path, allow_pickle=False) as z:
                loaded = {k: z[k] for k in z.files}
            checked = native.evaluate_words(self.context, restore_factor(loaded, bits), bits)
            if acceptance_problems(checked):
                raise ValueError('serialized 8-bit factor failed independent reload')
            ready = self.out/'passing-8bit.json'
            if not ready.exists():
                with ready.open('x') as f:
                    f.write(json_text({**row, 'reload_metrics': checked}))
        return row

    def continuous_callback(self, stage, params, bits=11):
        from .postprocess import prepare
        raw_save = checkpoint_callback(self.out, stage, 1)
        def checkpoint(u, w, details):
            p = {**{k:v for k,v in params.items() if k not in ('angle_words','brot')}, 'U': u, 'W': w}
            raw_save(p)
            self.point(f'stage-{stage}', prepare(self.context, p, bits), bits, details)
        return checkpoint
