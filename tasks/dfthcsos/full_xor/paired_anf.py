# SPDX-License-Identifier: Apache-2.0
"""Exact split-ANF XOR lookups.

Every claimed compiler equality is over GF(2), on all addresses 0<=a<A.
The construction never reads or modifies the target while forming a control,
so it implements XOR on every initial target state.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import kickmix as km

# Verifier package (installed beside Kickmix), not tasks.dfthcsos.
from dfthcsos.scoreinfra.circuits import recover_words_from_circuits, circuit_costs


def bits(n: int) -> Iterable[int]:
    while n:
        t = n & -n
        yield t.bit_length() - 1
        n ^= t


def anf(words: np.ndarray, brot: int) -> list[int]:
    """One packed output coefficient per monomial, masks <A.

    [0,A) is downward closed in bit-subset order, so in-place Moebius
    inversion needs no arbitrary unused-address padding.
    """
    words = np.asarray(words, dtype=np.int64)
    a, j = words.shape
    out = [sum(int(words[i, w]) << (w * brot) for w in range(j)) for i in range(a)]
    for b in range((a - 1).bit_length()):
        for mask in range(a):
            if mask & (1 << b):
                out[mask] ^= out[mask ^ (1 << b)]
    return out


def coefficient_polys(coeffs: list[int], output_bits: int) -> list[int]:
    return [sum(1 << mask for mask, c in enumerate(coeffs) if (c >> out) & 1)
            for out in range(output_bits)]


def output_basis(polys: list[int]) -> tuple[list[int], list[int]]:
    """Independent output polynomials and masks describing their fanout."""
    pivots: dict[int, tuple[int, int]] = {}
    basis: list[int] = []
    coords: list[int] = []
    for poly in polys:
        x, coord = poly, 0
        while x:
            p = x.bit_length() - 1
            if p not in pivots:
                k = len(basis)
                basis.append(x)
                pivots[p] = x, 1 << k
                coord ^= 1 << k
                break
            row, rowcoord = pivots[p]
            x ^= row
            coord ^= rowcoord
        coords.append(coord)
    fanouts = [sum(1 << j for j, c in enumerate(coords) if (c >> i) & 1)
               for i in range(len(basis))]
    for p, c in zip(polys, coords):
        z = 0
        for i in bits(c):
            z ^= basis[i]
        assert z == p
    return basis, fanouts


def matrix(poly: int, low_bits: int, addresses: int) -> tuple[list[int], int, int]:
    """Bilinear matrix columns (nonconstant high monomials), pure halves."""
    stride = 1 << low_bits
    high_max = (addresses - 1) >> low_bits
    columns = [0] * high_max
    pure_lo, pure_hi = 0, 0
    for m in bits(poly):
        l, h = m & (stride - 1), m >> low_bits
        if h == 0:
            pure_lo ^= 1 << l
        elif l == 0:
            pure_hi ^= 1 << h
        else:
            columns[h - 1] ^= 1 << l
    return columns, pure_lo, pure_hi


def rank_decomposition(columns: list[int]) -> list[tuple[int, int]]:
    """Exact A=Σ l_i r_i^T, l_i and r_i packed by monomial masks."""
    pivots: dict[int, tuple[int, int]] = {}
    lefts: list[int] = []
    rights: list[int] = []
    for col_index, original in enumerate(columns, 1):
        x, coord = original, 0
        while x:
            p = x.bit_length() - 1
            if p not in pivots:
                k = len(lefts)
                lefts.append(x)
                rights.append(0)
                pivots[p] = x, 1 << k
                coord ^= 1 << k
                break
            row, rowcoord = pivots[p]
            x ^= row
            coord ^= rowcoord
        for k in bits(coord):
            rights[k] ^= 1 << col_index
    for j, col in enumerate(columns, 1):
        rebuilt = 0
        for l, r in zip(lefts, rights):
            if (r >> j) & 1:
                rebuilt ^= l
        assert rebuilt == col
    return list(zip(lefts, rights))


def poly_product(a: int, b: int, max_mask: int) -> int:
    """Boolean polynomial product: x_S*x_T=x_(S union T)."""
    out = 0
    for i in bits(a):
        for j in bits(b):
            if (i | j) <= max_mask:
                out ^= 1 << (i | j)
    return out


def parity_value(poly: int, address: int) -> int:
    return sum(1 for m in bits(poly) if address & m == m) & 1


@dataclass
class Product:
    left1: int
    right1: int
    left2: int
    right2: int
    fanout: int


@dataclass
class Plan:
    addresses: int
    batch: int
    brot: int
    low_bits: int
    products: list[Product]
    pure: dict[int, int]
    ranks: list[int]
    cache_masks: list[int]
    blocks: list['Plan'] | None = None
    parity_scratch: int = 2

    @property
    def toffoli(self) -> int:
        if self.blocks is not None:
            return sum(p.toffoli for p in self.blocks)
        return len(self.cache_masks) + len(self.products)

    @property
    def qubits(self) -> int:
        base = (self.addresses-1).bit_length() + self.batch*self.brot
        if self.blocks is not None:
            return max(p.qubits for p in self.blocks)
        return base + len(self.cache_masks) + (self.parity_scratch if self.products else 0)

    def evaluate(self, address: int) -> int:
        if self.blocks is not None:
            result = 0
            for p in self.blocks:
                result ^= p.evaluate(address)
            return result
        lo, hi = address & ((1 << self.low_bits)-1), address >> self.low_bits
        result = 0
        for p in self.products:
            if ((parity_value(p.left1, lo) ^ parity_value(p.right2, hi)) &
                (parity_value(p.left2, lo) ^ parity_value(p.right1, hi))):
                result ^= p.fanout
        for mask, fanout in self.pure.items():
            if mask & address == mask:
                result ^= fanout
        return result


def make_plan(delta: np.ndarray, brot: int, low_bits: int, *, mixing_steps: int = 0,
              share_odd: bool = False,
              in_place_parity: bool = False,
              seed: int = 0, poly_override: list[int] | None = None) -> Plan:
    delta = np.asarray(delta, dtype=np.int64)
    a, j = delta.shape
    polys = coefficient_polys(anf(delta, brot), j*brot) if poly_override is None else poly_override
    funcs, fanouts = output_basis(polys)
    if mixing_steps:
        funcs, fanouts = mix_output_basis(funcs, fanouts, low_bits, a, mixing_steps, seed)
    products: list[Product] = []
    if share_odd:
        # For two full row-rank odd matrices, cancel distinct low rows with
        # a shared rank-two bilinear update. Both row ranks fall by >=1.
        # Its product-of-affine-forms pure-half terms are also added to the
        # residual polynomials, so all identities remain exact.
        low_rank = (1 << low_bits)-1
        high_rank = (a-1)>>low_bits
        full_rank = min(low_rank,high_rank)
        eligible = [i for i,p in enumerate(funcs)
                    if len(rank_decomposition(matrix(p,low_bits,a)[0])) == full_rank]
        if full_rank >= 3 and full_rank & 1:
            for i,jj in zip(eligible[::2],eligible[1::2]):
                ca=matrix(funcs[i],low_bits,a)[0]
                cb=matrix(funcs[jj],low_bits,a)[0]
                if low_rank <= high_rank:
                    left1,left2=1<<1,1<<2
                    right1=sum(1 << (h+1) for h,col in enumerate(ca) if (col >> 1)&1)
                    right2=sum(1 << (h+1) for h,col in enumerate(cb) if (col >> 2)&1)
                else:
                    # Same operation on the transpose when the high domain
                    # is the smaller, full-rank side (e.g. A1108 split6/5).
                    left1,left2=ca[0],cb[1]
                    right1,right2=1<<1,1<<2
                product=Product(left1,right1,left2,right2,fanouts[i]^fanouts[jj])
                products.append(product)
                full_poly=0
                for l in bits(left1):
                    for h in bits(right1):full_poly ^= 1 << (l | (h << low_bits))
                for l in bits(left2):
                    for h in bits(right2):full_poly ^= 1 << (l | (h << low_bits))
                full_poly ^= poly_product(left1,left2,(1<<low_bits)-1)
                for h in bits(poly_product(right1,right2,(a-1)>>low_bits)):
                    full_poly ^= 1 << (h << low_bits)
                funcs[i] ^= full_poly
                funcs[jj] ^= full_poly
    pure: dict[int, int] = {}
    ranks: list[int] = []
    lowmax, highmax = (1 << low_bits)-1, (a-1) >> low_bits
    def add_pure(p: int, fanout: int, shift: int) -> None:
        for m in bits(p):
            full = m << shift
            if full < a:
                pure[full] = pure.get(full, 0) ^ fanout
    for poly, fanout in zip(funcs, fanouts):
        columns, lo, hi = matrix(poly, low_bits, a)
        factors = rank_decomposition(columns)
        ranks.append(len(factors))
        for t in range(0, len(factors), 2):
            l1, r1 = factors[t]
            l2, r2 = factors[t+1] if t+1 < len(factors) else (0, 0)
            products.append(Product(l1,r1,l2,r2,fanout))
            lo ^= poly_product(l1,l2,lowmax)
            hi ^= poly_product(r1,r2,highmax)
        add_pure(lo,fanout,0)
        add_pure(hi,fanout,low_bits)
    pure = {m:c for m,c in pure.items() if c}
    used = set(pure)
    for p in products:
        used.update(bits(p.left1 | p.left2))
        used.update(m << low_bits for m in bits(p.right1 | p.right2))
    # Downward spanning-tree closure makes every needed monomial in one AND.
    for m in list(used):
        while m and m.bit_count() >= 2:
            used.add(m)
            m ^= 1 << (m.bit_length()-1)
    cache_masks = sorted(m for m in used if m.bit_count() >= 2)
    return Plan(a,j,brot,low_bits,products,pure,ranks,cache_masks,
                parity_scratch=0 if in_place_parity else 2)


def mix_output_basis(funcs: list[int], fanouts: list[int], low_bits: int,
                     addresses: int, steps: int, seed: int) -> tuple[list[int],list[int]]:
    """Monotone elementary GL(m,2) search, exact and reversible."""
    funcs, fanouts = funcs[:], fanouts[:]
    cost_cache: dict[int,int] = {}
    def cost(poly: int) -> int:
        if poly not in cost_cache:
            cost_cache[poly] = (len(rank_decomposition(matrix(poly,low_bits,addresses)[0]))+1)//2
        return cost_cache[poly]
    rng = np.random.default_rng(seed)
    for _ in range(steps):
        i,j = map(int,rng.choice(len(funcs),2,replace=False))
        new = funcs[i] ^ funcs[j]
        if cost(new) < cost(funcs[i]):
            funcs[i] = new
            fanouts[j] ^= fanouts[i]
    return funcs,fanouts


def build_circuit(plan: Plan) -> km.Circuit:
    b = km.CircuitBuilder()
    selection = b.create_quantum_register((plan.addresses-1).bit_length(), 'selection')
    words = [b.create_quantum_register(plan.brot, f'word_{j}') for j in range(plan.batch)]
    targets = [q for word in words for q in word]

    def compile_one(p: Plan) -> None:
        cache: dict[int,object] = {0:True, **{1<<i:q for i,q in enumerate(selection)}}
        allocated = b.alloc_qubits(len(p.cache_masks))
        for mask,q in zip(p.cache_masks,allocated):
            top = 1 << (mask.bit_length()-1)
            b.init_and(cache[mask ^ top], cache[top], q)
            cache[mask] = q
        parity = b.alloc_qubits(p.parity_scratch if p.products else 0)
        def xorpoly(poly: int, shift: int, target: object) -> None:
            for mask in bits(poly):
                b.cx(cache[mask << shift],target)
        for prod in p.products:
            inverse_ops=[]
            if p.parity_scratch:
                control1,control2=parity[0],parity[1]
                xorpoly(prod.left1,0,control1); xorpoly(prod.right2,p.low_bits,control1)
                xorpoly(prod.left2,0,control2); xorpoly(prod.right1,p.low_bits,control2)
            else:
                # Two independent linear forms can be materialized by an
                # invertible CNOT map on existing cache/address wires.
                # No clean parity ancilla is needed. Restore every wire
                # immediately after the arbitrary-target CCX fanout.
                aa={cache[m].id for m in bits(prod.left1)}
                aa.update(cache[m << p.low_bits].id for m in bits(prod.right2))
                bb={cache[m].id for m in bits(prod.left2)}
                bb.update(cache[m << p.low_bits].id for m in bits(prod.right1))
                pp=min(aa)
                use_a=pp in bb
                bprime=bb^aa if use_a else bb
                assert bprime, 'dependent product controls should have been simplified'
                qq=min(bprime)
                inverse_ops=[(km.q(t),km.q(pp)) for t in sorted(aa-{pp})]
                inverse_ops += [(km.q(t),km.q(qq)) for t in sorted(bprime-{qq})]
                if use_a:inverse_ops.append((km.q(pp),km.q(qq)))
                for control,target in inverse_ops:b.cx(control,target)
                control1,control2=km.q(pp),km.q(qq)
            out = list(bits(prod.fanout))
            pivot = targets[out[0]]
            # Conjugated fanout implements one arbitrary-target XOR vector
            # using a single CCX, without any clean product target.
            for k in out[1:]: b.cx(pivot,targets[k])
            b.ccx(control1,control2,pivot)
            for k in out[1:]: b.cx(pivot,targets[k])
            if p.parity_scratch:
                xorpoly(prod.left2,0,control2); xorpoly(prod.right1,p.low_bits,control2)
                xorpoly(prod.left1,0,control1); xorpoly(prod.right2,p.low_bits,control1)
            else:
                for control,target in reversed(inverse_ops):b.cx(control,target)
        b.free(parity)
        for mask,fanout in p.pure.items():
            for k in bits(fanout): b.cx(cache[mask],targets[k])
        for mask in reversed(p.cache_masks):
            top = 1 << (mask.bit_length()-1)
            b.del_and(cache[mask ^ top],cache[top],cache[mask])
        b.free(allocated)
    for p in plan.blocks or [plan]: compile_one(p)
    return b.finish_circuit()


def assert_classical(plan: Plan, delta: np.ndarray) -> None:
    for a,row in enumerate(delta):
        expected = sum(int(x) << (j*plan.brot) for j,x in enumerate(row))
        actual = plan.evaluate(a)
        assert actual == expected, (a,expected,actual)


def batch_deltas(words: np.ndarray, batch: int) -> list[np.ndarray]:
    a,n=words.shape
    padded=np.zeros((a,math.ceil(n/batch)*batch),dtype=np.int64)
    padded[:,:n]=words
    tables=padded.reshape(a,-1,batch).transpose(1,0,2).copy()
    tables[1:] ^= tables[:-1].copy()
    return list(tables)


def signed_gauge(words: np.ndarray, tree_edges: np.ndarray, brot: int) -> np.ndarray:
    """Exact projector-preserving signed-angle gauge, all arithmetic integral.

    Traverse backwards, propagating endpoint diagonal signs towards the
    initially-zero vertices. The only surviving initial sign is a global
    sign on the root. Independent per-angle folding is NOT sufficient.
    """
    out=np.asarray(words,dtype=np.int64).copy()
    edges=np.asarray(tree_edges,dtype=np.int64)
    assert len(edges)==out.shape[1]
    signs=np.zeros((out.shape[0],out.shape[1]+1),dtype=bool)
    period,half,quarter=1<<brot,1<<(brot-1),1<<(brot-2)
    for k in reversed(range(len(edges))):
        p,q=map(int,edges[k])
        effective=np.where(signs[:,p]^signs[:,q],-out[:,k],out[:,k])%period
        folded=(effective+quarter)%half-quarter
        toggle=(((effective-folded)//half)&1).astype(bool)
        signs[:,p]^=toggle;signs[:,q]^=toggle
        out[:,k]=folded%period
    return out


def sample_proxy(addresses: int=1366, columns: int=75, *,
                 preserve_projectors: bool=True) -> np.ndarray:
    archive=np.load(Path(__file__).resolve().parents[4]/'sample_submission/dfthcsos/submission.npz')
    source=archive['angle_words']
    # Quantize 12-bit words to eight bits, then fold to [-pi/2,pi/2).
    # This is a structure proxy, NOT a claimed accurate factorization.
    source=source[:addresses,:]
    q=np.rint(source/16).astype(np.int64)
    if preserve_projectors:
        q=signed_gauge(q%256,archive['tree_edges'],8)
    else:
        q=(((q+64)%128)-64)%256
    return q[:,:columns]


def run_smoke() -> None:
    rng=np.random.default_rng(104729)
    for a,j,br,nangle,lo in [(19,2,4,5,3),(37,3,8,7,3),(130,3,8,8,4)]:
        words=rng.integers(0,1<<br,(a,nangle),dtype=np.int64)
        plans=[make_plan(d,br,lo) for d in batch_deltas(words,j)]
        for p,d in zip(plans,batch_deltas(words,j)): assert_classical(p,d)
        circuits=[build_circuit(p) for p in plans]
        recovered,layout,toffoli=recover_words_from_circuits(circuits,num_vectors=a,num_angles=nangle,seed=104729)
        assert np.array_equal(recovered,words)
        assert toffoli == 2*sum(p.toffoli for p in plans)
        assert [p.qubits for p in plans] == [int(c.num_qubits) for c in circuits]
        print(dict(test='smoke',A=a,J=j,brot=br,angles=nangle,plans=[dict(T=p.toffoli,Q=p.qubits,ranks=p.ranks) for p in plans],recover_T=toffoli),flush=True)


if __name__ == '__main__':
    run_smoke()
