# SPDX-License-Identifier: Apache-2.0
"""Edit 011: clear converter zero flags by measurement, not by a second zero test.

hengck23 iter 011 (discussion 753607): ΔT −456 mean-executed.
``clear_flag(b,a,F)`` recomputed ``zero(a)`` into ``F`` (11 AND gates) and freed
it. Where F equals ``zero(a)`` at that point, measure F in the X basis (HMR) and
pay the phase ``(−1)^{m·zero(a)}`` with the edit-001 conditioned ladder, which is
skipped on shots where ``m=0``. ``clear_flag_m`` is that measured clear; each call
site is switched over separately so a site where the flag is not exactly
``zero(a)`` can stay on the recompute.
"""
from __future__ import annotations

import os
from pathlib import Path

CONVERTER = Path('exp/safe_scalar/converter.py')
SHORT = Path('exp/convert_short_hankel/kernel.py')
DEF_MARKER = 'def clear_flag(b,a,F):zero_toggle(b,a,F);b.free(F)'
DEF_NEW = DEF_MARKER + '''

def clear_flag_m(b,a,F):
    from exp.arithmetic.division import phase_zero
    m=b.alloc_bits(1);b.hmr(F,m[0]);b.free(F);phase_zero(b,a,m[0]);b.free(m)'''

# site name -> (file, old text, new text); every old text must occur exactly once.
SITES = {
    'q_post': (CONVERTER, 'b.cswap(F,q,p);clear_flag(b,q,F)', 'b.cswap(F,q,p);clear_flag_m(b,q,F)'),
    'look_a': (CONVERTER, 'canonical_permute(b,f,g,F);clear_flag(b,g[-1],F)',
               'canonical_permute(b,f,g,F);clear_flag_m(b,g[-1],F)'),
    'look_b': (CONVERTER, 'rotate(b,g,F,True);clear_flag(b,g[-1],F)',
               'rotate(b,g,F,True);clear_flag_m(b,g[-1],F)'),
    'root_a': (SHORT, 'old.canonical_permute(b,f,g,F);old.clear_flag(b,g[-1],F)',
               'old.canonical_permute(b,f,g,F);old.clear_flag_m(b,g[-1],F)'),
    'root_b': (SHORT, 'old.rotate(b,g,F,True);old.clear_flag(b,g[-1],F)',
               'old.rotate(b,g,F,True);old.clear_flag_m(b,g[-1],F)'),
}
DEFAULT_SITES = tuple(SITES)


def apply(tree: Path, sites=None) -> dict:
    if sites is None:
        env = os.environ.get('PRA322_E011_SITES')
        sites = env.split(',') if env else DEFAULT_SITES
    path = tree / CONVERTER
    text = path.read_text()
    if text.count(DEF_MARKER) != 1:
        raise SystemExit(f'e011: marker not found exactly once in {path}')
    path.write_text(text.replace(DEF_MARKER, DEF_NEW))
    for name in sites:
        rel, old, new = SITES[name]
        path = tree / rel
        text = path.read_text()
        if text.count(old) != 1:
            raise SystemExit(f'e011: site {name} not found exactly once in {path}')
        path.write_text(text.replace(old, new))
    return {'edit': 'e011', 'file': str(CONVERTER), 'hengck_iter': '011', 'expected_dT': -456,
            'sites': list(sites)}
