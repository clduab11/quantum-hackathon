# SPDX-License-Identifier: Apache-2.0
"""Export every rounded free-angle row without one-body re-encoding."""
import numpy as np
from .angles import quantize, decode


def arrays(params, edges, bits, template):
    rounded = quantize(params['angles'],bits)
    words = np.asarray(rounded*(1 << (bits-1))).astype(np.int64)
    w, offsets = np.asarray(params['w']),np.asarray(params['offsets'])
    n = words.shape[1]+1
    if words.shape[0] != n+w.shape[0]*w.shape[1]:
        raise ValueError('angle rows must include N one-body and R*B two-body rows')
    return dict(U=np.asarray(decode(rounded,edges))[n:].reshape(*w.shape[:2],n),
                W=w,H2_I=offsets+w.sum(axis=1),H1_I=np.asarray(template['H1_I']),
                Hsym_lower=np.asarray(template['Hsym_lower']),angle_words=words,
                tree_edges=np.asarray(edges),brot=np.asarray(bits))
