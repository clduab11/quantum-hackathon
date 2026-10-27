"""Read-only qubit floor of the port's main coefficient lookup (PRA-285).

Run with ``uv run --group gpu python -m tasks.invsqrt.public_port.lookup_bound``
(refits on CUDA), or pass ``--fit FILE`` with a saved ``fit_tables()`` JSON.
The main lookup writes every output at once while the 22 input wires stay live.
An output that is constant, or an XOR of address bits and other outputs, can be
written later with Clifford gates only. Every other output must be live at the
lookup, so ``22 + independent outputs`` bounds the peak of any storage-only
schedule that keeps this single lookup, before flags or ladder wires.
"""
import argparse
import json
from pathlib import Path

from tasks.invsqrt import signed_digit as H
from . import arithmetic as O
from .model import Config


def lookup_outputs(fitted):
    """The output names and the 256 packed rows written by schedule.build's main lookup."""
    c = Config()
    tabs = {(e, a): fitted['rows'][128*e+a] for e in range(2) for a in range(128)}
    lay = H.layout(c, tabs, LB=c.fy - 7, S=c.fy - 8)
    sp = O.prepare(c, tabs)
    lb, rw, whi = lay['LB'], sp['rw'], lay['whi']
    names = ([f'low{i}' for i in range(lb - 1)] + [f'res{i}' for i in range(rw)]
             + [f'high{i}' for i in range(whi)] + [f'coarse{i}' for i in range(sp['cw'])])
    rows = []
    for e in range(2):
        for a in range(128):
            k = (e, a)
            rows.append(lay['lo'][k] >> 1 | sp['residual'][k] << lb - 1 | lay['hi'][k] << lb - 1 + rw
                        | sp['coarse'][k] << lb - 1 + rw + whi)
    return names, rows


def bound(fitted):
    names, rows = lookup_outputs(fitted)
    n = len(rows)
    basis = {}

    def insert(v):
        while v:
            p = v.bit_length() - 1
            if p not in basis:
                basis[p] = v
                return True
            v ^= basis[p]
        return False

    # Row index 128*e + a is the address: bits 0..6 are x[14:21], bit 7 is f[0].
    for b in range(8):
        insert(sum((i >> b & 1) << i for i in range(n)))
    insert((1 << n) - 1)
    dependent = [name for j, name in enumerate(names)
                 if not insert(sum((r >> j & 1) << i for i, r in enumerate(rows)))]
    independent = len(names) - len(dependent)
    return dict(outputs=len(names), affine_dependent=dependent, independent=independent,
                input_wires=22, floor_without_flags_or_ladder=22 + independent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit', type=Path, help='saved fit_tables() JSON; default refits on CUDA')
    args = parser.parse_args()
    if args.fit is None:
        from .fit import fit_tables
        fitted = fit_tables()
    else:
        fitted = json.loads(args.fit.read_text())
    print(json.dumps(bound(fitted)))


if __name__ == '__main__':
    main()
