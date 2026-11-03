# SPDX-License-Identifier: Apache-2.0
"""Bounded own-fit precision screens for PRA-286; never emits a circuit.

Each result includes a freshly recomputed full-domain integer certificate.
The register budget describes the ordinary virtual-low schedule, not a lower
bound on all possible encodings. Failed numerics are kept as negative evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from .fit import fit_tables
from .model import Config


def register_budget(cfg, tables):
    from tasks.invsqrt.signed_digit import layout
    from .arithmetic import prepare

    place = layout(cfg, tables, LB=cfg.fy-7, S=cfg.fy-8)
    split = prepare(cfg, tables)
    low = place['LB']-1
    persistent = 22 + 4 + low + split['rw'] + split['cw']
    return dict(input=22, flags=4, low=low, high=place['whi'],
                residual=split['rw'], coarse=split['cw'], curvature=cfg.w2,
                outer_carries=low-2, virtual_carry=1,
                ordinary_outer_peak=persistent + 1 + low-2,
                full_lookup_outputs=low + place['whi'] + split['rw'] + split['cw'])


def run(out, linear_bits=(16, 17, 18)):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for f1 in linear_bits:
        if f1 not in (16, 17, 18):
            raise ValueError('This bounded study supports linear bits 16, 17 or 18')
        cfg = Config(f1=f1, fyr=f1+8, gy=1)
        started = time.monotonic()
        fitted = fit_tables(cfg=cfg)
        data = (json.dumps(fitted, indent=2)+'\n').encode()
        path = out/f'fit-f1-{f1}.json'
        path.write_bytes(data)
        tables = {(e, a): fitted['rows'][128*e+a] for e in range(2) for a in range(128)}
        try:
            budget = register_budget(cfg, tables)
        except AssertionError as error:
            budget = {'layout_error': str(error)}
        report = dict(params=fitted['params'], fit_sha256=hashlib.sha256(data).hexdigest(),
                      normalized_worst=fitted['normalized_worst'],
                      integer_certificate=fitted['certificate'], registers=budget,
                      seconds=time.monotonic()-started, circuit_built=False)
        reports.append(report)
        (out/'precision-report.json').write_text(json.dumps(reports, indent=2)+'\n')
        print('PRECISION_RESULT '+json.dumps(report), flush=True)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--linear-bits', type=int, choices=(16, 17, 18), nargs='+', default=[16, 17, 18])
    args = parser.parse_args()
    run(args.out, args.linear_bits)


if __name__ == '__main__':
    main()
