# SPDX-License-Identifier: Apache-2.0
"""Exact GF(2) lookup factorization, ported from mrmeows v6 rank_parity.py.

Source URL, hashes and attribution: notices/35-chem-catchup.txt.
Only deterministic matrix factorization is used; no kernel/seed search.
"""
import numpy as np

def set_bits(value):
    while value:
        bit = (value & -value).bit_length()-1
        yield bit
        value &= value-1


def mobius_axis(values, axis):
    out = np.swapaxes(values.copy(),axis,0)
    ids = np.arange(len(out))
    for bit in range((len(out)-1).bit_length()):
        rows = ids[(ids & (1 << bit)) != 0]
        out[rows] ^= out[rows ^ (1 << bit)]
    return np.swapaxes(out,0,axis)




class BinaryBasis:
    def __init__(self):
        self.pivots = {}
        self.vectors = []

    def add(self,value):
        original = value
        coordinates = 1 << len(self.vectors)
        while value:
            p = value.bit_length()-1
            if p not in self.pivots:
                self.pivots[p] = (value,coordinates)
                self.vectors.append(original)
                return True
            v,c = self.pivots[p]
            value ^= v
            coordinates ^= c
        return False

    def solve(self,value):
        coordinates = 0
        while value:
            p = value.bit_length()-1
            if p not in self.pivots:
                return None
            v,c = self.pivots[p]
            value ^= v
            coordinates ^= c
        return coordinates




def nullspace(rows, width):
    """Basis of the GF(2) vectors of ``width`` bits orthogonal to every packed row."""
    pivots = {}
    for value in rows:
        value = int(value)
        while value:
            p = value.bit_length()-1
            if p not in pivots:
                pivots[p] = value
                if len(pivots) == width:
                    return []
                break
            value ^= pivots[p]
    result = []
    for j in range(width):
        if j not in pivots:
            value = 1 << j
            for p,row in sorted(pivots.items()):
                if (row & value).bit_count() & 1:
                    value ^= 1 << p
            result.append(value)
    return result


def factor_matrix(columns):
    basis = BinaryBasis()
    for col in columns:
        basis.add(col)
    lows = [0]*len(basis.vectors)
    for k,col in enumerate(columns):
        coordinates = basis.solve(col)
        assert coordinates is not None
        for bit in set_bits(coordinates):
            lows[bit] ^= 1 << k
    return list(zip(basis.vectors,lows))


def require_redundant_sign_bit(delta,brot):
    """Reject raw tables that cannot be represented by b-1 Boolean functions.

    Every physical word bit remains an arbitrary target. This precondition is
    about the requested XOR values, not an assumption about target contents.
    The caller must explicitly apply a legal projective gauge beforehand.
    """
    if not isinstance(brot,(int,np.integer)) or not 2 <= brot <= 62:
        raise ValueError('brot must be an integer between 2 and 62')
    table = np.asarray(delta)
    if (table.ndim != 2 or min(table.shape,default=0) < 1 or
            not np.issubdtype(table.dtype,np.integer)):
        raise ValueError('delta must be a nonempty two-dimensional integer table')
    if np.any(table < 0) or np.any(table >= (1 << brot)):
        raise ValueError('delta word outside the selected precision')
    table = table.astype(np.int64,copy=False)
    if np.any(((table >> (brot-1)) ^ (table >> (brot-2))) & 1):
        raise ValueError('redundant sign-bit precondition failed: the two highest '
                         'bits of every requested XOR word must be equal')
    return table


def coefficients(delta,brot,lowbits):
    delta = require_redundant_sign_bit(delta,brot)
    count,J = delta.shape
    low = 1 << lowbits
    high = (count+low-1)//low
    padded = np.zeros((low*high,J),dtype=np.int64)
    padded[:count] = delta
    require_redundant_sign_bit(padded,brot)
    bits = np.stack([(padded[:,j] >> bit)&1 for j in range(J)
                     for bit in range(brot-1)],axis=1).astype(np.uint8)
    truth = bits.reshape(high,low,-1)
    result = mobius_axis(mobius_axis(truth,0),1)
    assert np.array_equal(mobius_axis(mobius_axis(result,1),0),truth)
    return result
