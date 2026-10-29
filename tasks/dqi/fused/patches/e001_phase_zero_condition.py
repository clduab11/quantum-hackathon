# SPDX-License-Identifier: Apache-2.0
"""Edit 001: condition phase_zero's 22-Toffoli ladder on the classical mask bit.

hengck23 iter 001/002 (discussion 753607): ΔT −374 at fixed Q 889.
When ``head`` is None the phase is exactly (−1)^{zero(y) ∧ mask}. Wrapping the
ladder in ``push_condition(mask)`` and paying ``CZ`` instead of ``CCZ(..., mask)``
skips the ladder on mask=0 shots (mean-executed Toffolis).
Calls with a quantum head keep the original unconditional ladder.
"""
from __future__ import annotations

from pathlib import Path

RELPATH = Path('exp/arithmetic/division.py')
MARKER = 'def phase_zero(b,y,mask,head=None,headmask=None):'
REPLACEMENT = '''def phase_zero(b,y,mask,head=None,headmask=None):
    """Apply zero(y)*(mask+dot(head,headmask)); conditioned ladder when head is None.

    PRA-322 / hengck23 edit 001: when there is no head term, run the 22-Toffoli
    zero-test ladder only under push_condition(mask) and apply CZ (mask is the
    classical condition). Headful calls keep the original unconditional path.
    """
    if head is None:
        n=len(y);b.push_condition(mask);b.x(y);ladder=b.alloc_qubits(n-2)
        b.init_and(y[0],y[1],ladder[0])
        for i in range(1,n-2):b.init_and(ladder[i-1],y[i+1],ladder[i])
        b.cz(ladder[-1],y[-1])
        for i in reversed(range(n-2)):
            if i==0:b.del_and(y[0],y[1],ladder[0])
            else:b.del_and(ladder[i-1],y[i+1],ladder[i])
        b.free(ladder);b.x(y);b.pop_condition()
        return
    n=len(y);b.x(y);ladder=b.alloc_qubits(n-2)
    b.init_and(y[0],y[1],ladder[0])
    for i in range(1,n-2):b.init_and(ladder[i-1],y[i+1],ladder[i])
    b.ccz(ladder[-1],y[-1],mask)
    q=b.alloc_qubits(1)[0]
    for xi,mi in zip(head,headmask):b.ccx(mi,xi,q)
    b.ccz(ladder[-1],y[-1],q)
    for xi,mi in reversed(list(zip(head,headmask))):b.ccx(mi,xi,q)
    b.free(q)
    for i in reversed(range(n-2)):
        if i==0:b.del_and(y[0],y[1],ladder[0])
        else:b.del_and(ladder[i-1],y[i+1],ladder[i])
    b.free(ladder);b.x(y)
'''


def apply(tree: Path) -> dict:
    path = tree / RELPATH
    text = path.read_text()
    if MARKER not in text:
        raise SystemExit(f'e001: marker not found in {path}')
    start = text.index(MARKER)
    # Replace through the blank line after the original function body.
    end = text.index('\n\n\n', start)
    new = text[:start] + REPLACEMENT.rstrip() + text[end:]
    path.write_text(new)
    return {'edit': 'e001', 'file': str(RELPATH), 'hengck_iter': '001/002', 'expected_dT': -374}
