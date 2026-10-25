# SPDX-License-Identifier: Apache-2.0
"""Reproduce PRA-232's fixed structural ablation; no salt or seed selection."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tasks.dfthcsos.circuit import generate
from tasks.dfthcsos.gates import g2_proxy

SALT = 'PRA171_LOCAL_PUBLIC_FIXED_SALT_0001'
BASELINE_COST = 3355599588.3155365
# name, brot, J, low bank bits, traversal wires, pebbling prefix degree
POINTS = (
    ('direct12-j9', 12, 9, 0, 8, 4),
    ('direct12-six', 12, 9, 0, 6, 5),
    ('bank2-12-j4', 12, 4, 1, 6, 5),
    ('bank2-12-j5', 12, 5, 1, 6, 5),
    ('bank4-12-five', 12, 2, 2, 5, 4),
    ('bank4-12-six', 12, 2, 2, 6, 4),
    ('bank4-12-j3', 12, 3, 2, 6, 4),
    ('direct11-j9', 11, 9, 0, 8, 4),
    ('bank2-11-j5', 11, 5, 1, 6, 5),
    ('direct10-j10', 10, 10, 0, 8, 4),
    ('bank2-10-j5', 10, 5, 1, 6, 5),
)


def run(out: Path):
    from dfthcsos.verify import (load_inputs, load_tree_edges, evaluate_circuits,
                                rejection_reason, verify)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, brot, batch, bank, scratch, degree in POINTS:
        row = dict(name=name, parameters=dict(brot=brot, batch_size=batch,
                   bank_bits=bank, scratch=scratch, pebble_degree=degree))
        start = time.monotonic()
        try:
            row['build'] = generate(out / name, **row['parameters'])
        except ValueError as exc:
            row['build_failure'] = str(exc)
        else:
            row['g2'] = g2_proxy(out / name)
            row['predicted_ratio'] = BASELINE_COST / row['g2']['estimated_cost']
            # Full official verifier, same salt and all 64 shots per address.
            # For rejected precision points retain the underlying full metrics too.
            chemistry = out / name / 'dfthcsos'
            verify_start = time.monotonic()
            try:
                row['verifier'] = verify(chemistry, salt=SALT)
            except AssertionError as exc:
                result = evaluate_circuits(load_inputs(chemistry / 'submission.npz'), chemistry,
                    load_tree_edges(None, chemistry), salt=SALT)
                result.pop('angle_words')
                result['score'] = None  # Infinite rejection score, JSON has no infinity.
                row['verifier'] = dict(status='FAIL', error=str(exc), **result)
            row['verify_seconds'] = time.monotonic() - verify_start
            v = row['verifier']
            row['measured_ratio'] = BASELINE_COST / v['score'] if v['status'] == 'PASS' else None
        row['seconds'] = time.monotonic() - start
        rows.append(row)
        (out / (name + '.json')).write_text(json.dumps(row, indent=2) + '\n')
        print(json.dumps({k:row[k] for k in ['name', 'build_failure', 'predicted_ratio', 'measured_ratio', 'seconds'] if k in row}), flush=True)
    passing = [r for r in rows if r.get('g2', {}).get('status') == 'PASS']
    selected = min(passing, key=lambda r: r['g2']['estimated_cost']) if passing else None
    result = dict(salt=SALT, shots_per_address=64, baseline_cost=BASELINE_COST,
                  selected=selected['name'] if selected else None, rows=rows)
    (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True, help='Fresh experiment directory')
    a = p.parse_args()
    if a.out.exists() and any(a.out.iterdir()):
        p.error('--out must be empty; previous evidence is never overwritten')
    run(a.out)


if __name__ == '__main__':
    main()
