# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""DQI memory merge, built on attributed Apache-2.0 SomeJoint sources.

The two-pointer history follows the publicly described Phuc Thai EXP-118c
idea, independently implemented here. It is exact on histories of weight <=2.
The insertion is a permutation; a final HMR discards only its overflow bit.
"""
from contextlib import contextmanager


class PointerBank:
    def __init__(self, builder, count):
        self.b, self.count = builder, count
        self.width = count.bit_length()
        self.pointers = [builder.alloc_qubits(self.width) for _ in range(2)]
        self.overflow_measurements = 0

    def _transposition(self, pointer, code, flag):
        """Swap pointer values 0 <-> code, controlled by flag; fix all others."""
        from .common import km
        pivot = (code & -code).bit_length() - 1
        others = [i for i in range(self.width) if i != pivot]
        targets = [i for i in others if code >> i & 1]
        for i in targets:
            self.b.cx(pointer[pivot], pointer[i])
        self.b.flip_if_equal(km.array([pointer[i] for i in others]), 0,
                             target=pointer[pivot], control=flag)
        for i in reversed(targets):
            self.b.cx(pointer[pivot], pointer[i])

    def push(self, index, flag):
        b, code = self.b, index + 1
        for pointer in self.pointers:
            self._transposition(pointer, code, flag)
            b.flip_if_equal(pointer, code, target=flag)
        # This bit is identically zero on the promised <=2-gap subspace.
        # Overflow is an explicit approximation, never freed dirty.
        measured = b.alloc_bits(1)
        b.hmr(flag, measured[0])
        b.free(measured)
        b.free(flag)
        self.overflow_measurements += 1

    def pop(self, index):
        b, code = self.b, index + 1
        flag = b.alloc_qubits(1)[0]
        for pointer in reversed(self.pointers):
            b.flip_if_equal(pointer, code, target=flag)
            self._transposition(pointer, code, flag)
        return flag

    def read(self, index):
        assert 0 <= index < self.count
        flag = self.b.alloc_qubits(1)[0]
        self.xor_read(index, flag)
        return flag

    def xor_read(self, index, flag):
        for pointer in self.pointers:
            self.b.flip_if_equal(pointer, index + 1, target=flag)

    def unread(self, index, flag):
        for pointer in reversed(self.pointers):
            self.b.flip_if_equal(pointer, index + 1, target=flag)
        self.b.free(flag)

    @contextmanager
    def access(self, indices):
        flags = {i: self.read(i) for i in sorted(set(indices))}
        try:
            yield flags
        finally:
            for i, flag in reversed(list(flags.items())):
                self.unread(i, flag)

    def release_zero(self):
        for pointer in self.pointers:
            self.b.free(pointer)


def extract_pointers(builder, words, bank, *, reverse=False, early_buffer=True, release_inverse=False):
    from .jfraction_gap_decoder import rotate, toggle_gap
    from .compact_lifetime_kernels import scale_active_reused_mask
    scaler = scale_builder(builder, release_inverse)
    slots = len(words) // 2
    assert slots == bank.count
    for j in reversed(range(slots)) if reverse else range(slots):
        active = words[2*j:]
        if not reverse:
            gap = builder.alloc_qubits(1)[0]
            previous = bank.read(j - 1) if j else False
            toggle_gap(builder, active, previous, gap)
            if j:
                bank.unread(j - 1, previous)
            bank.push(j, gap)
        shortened = bank.read(j)
        if j:
            bank.xor_read(j - 1, shortened)
        rotate(builder, active, shortened, left=True)
        if reverse:
            reciprocal_early(builder, [1] + active[1:], shortened,
                             reverse=True, early_buffer=early_buffer)
            scale_active_reused_mask(scaler, active[0], active[1:], shortened, divide=False)
        else:
            scale_active_reused_mask(scaler, active[0], active[1:], shortened, divide=True)
            reciprocal_early(builder, [1] + active[1:], shortened, early_buffer=early_buffer)
        rotate(builder, active, shortened, left=False)
        if j:
            bank.xor_read(j - 1, shortened)
        bank.xor_read(j, shortened)
        builder.free(shortened)
        if reverse:
            gap = bank.pop(j)
            previous = bank.read(j - 1) if j else False
            toggle_gap(builder, active, previous, gap)
            if j:
                bank.unread(j - 1, previous)
            builder.free(gap)


def convert_pointers(builder, words, bank, *, reverse=False, release_inverse=False):
    """Read rotation controls only around rotations, not across field scaling."""
    from .jfraction_decoder import conversion_layout, scale_words
    from .jfraction_gap_decoder import conversion_core, rotate, toggle_header
    scaler = scale_builder(builder, release_inverse)
    p,q,stages=conversion_layout(words)
    stages=[(bank.count-1-i,*stage) for i,stage in enumerate(stages)]
    for j,x,y,old_p,old_q in reversed(stages) if reverse else stages:
        new_p=[x]+old_q[1:]
        rotations=[x,y]+old_q[1:]
        if reverse:
            gap=bank.read(j)
            rotate(builder,new_p,gap,left=True)
            bank.unread(j,gap)
            scale_words(scaler,x,old_q[1:],divide=True)
            pending=bank.read(j-1) if j else False
            toggle_header(builder,y,old_q,pending)
        else:
            pending=bank.read(j-1) if j else False
            if j:builder.cswap(pending,x,y)
            gap=bank.read(j)
            rotate(builder,rotations,gap,left=True)
            bank.unread(j,gap)
        conversion_core(builder,y,old_p,old_q,pending)
        if reverse:
            gap=bank.read(j)
            rotate(builder,rotations,gap,left=False)
            bank.unread(j,gap)
            if j:builder.cswap(pending,x,y)
            if j:bank.unread(j-1,pending)
        else:
            toggle_header(builder,y,old_q,pending)
            if j:bank.unread(j-1,pending)
            scale_words(scaler,x,old_q[1:],divide=False)
            gap=bank.read(j)
            rotate(builder,new_p,gap,left=False)
            bank.unread(j,gap)
    return p,q


class EphemeralInverseBuilder:
    """Release 18 scaffold wires while a scale's inverse is held.

    Recreate its small norm/reciprocal scaffold immediately before MBU
    deletion: +36 Toffolis per scale, no new approximation.
    """
    def __init__(self,builder):self.builder=builder
    def __getattr__(self,name):return getattr(self.builder,name)
    def init_gf2_inverse_with_scaffold(self,source,*,field):
        from .common import km
        from .compact_lifetime_kernels import init_compact_inverse
        return init_compact_inverse(self.builder,source,field=field),km.array([])
    def del_gf2_inverse_with_scaffold(self,source,*,target,scaffold,field):
        from .compact_lifetime_kernels import delete_compact_inverse
        assert len(scaffold)==0
        delete_compact_inverse(self.builder,source,target,field=field)


class RetainedNormInverseBuilder:
    """Retain the six-bit top norm in otherwise unused peak-Q slack.

    Only the GF64 reciprocal and its six-bit scaffold are deleted/recreated.
    This pays 21 rather than 36 extra Toffolis, at the same peak as the
    fully ephemeral inverse when exactly one 12-bit temporary is held.
    """
    def __init__(self,builder):self.builder=builder
    def __getattr__(self,name):return getattr(self.builder,name)
    def init_gf2_inverse_with_scaffold(self,source,*,field):
        b=self.builder
        inverse,scaffold=b.init_gf2_inverse_with_scaffold(source,field=field)
        norm,reciprocal,chain=scaffold[:6],scaffold[6:12],scaffold[12:]
        b.del_gf2_inverse_with_scaffold(norm,target=reciprocal,scaffold=chain,field=b.bases[12].inner)
        b.free(reciprocal+chain)
        return inverse,norm
    def del_gf2_inverse_with_scaffold(self,source,*,target,scaffold,field):
        b=self.builder
        assert len(scaffold)==6
        reciprocal,chain=b.init_gf2_inverse_with_scaffold(scaffold,field=b.bases[12].inner)
        b.del_gf2_inverse_with_scaffold(source,target=target,scaffold=scaffold+reciprocal+chain,field=field)
        b.free(reciprocal+chain)


def scale_builder(builder,mode):
    if mode=='small':
        from .smallspace_inverse import SmallSpaceInverseBuilder
        return SmallSpaceInverseBuilder(builder)
    if mode=='norm':return RetainedNormInverseBuilder(builder)
    return EphemeralInverseBuilder(builder) if mode else builder


def extract_exact_late(builder,words,bank,*,reverse=False,inverse_mode='norm',qubit_cap=None,retire=False):
    """Keep the exact 4->3 history codec closed across every field operation."""
    from .jfraction_gap_decoder import rotate,toggle_gap
    from .compact_lifetime_kernels import scale_active_reused_mask
    for j in reversed(range(bank.count)) if reverse else range(bank.count):
        if not reverse:bank.append(j)
        active=words[2*j:]
        shortened=builder.alloc_qubits(1)[0]
        with bank.access([j-1,j] if j else [j]) as flags:
            prev,gap=flags[j-1] if j else False,flags[j]
            if not reverse and gap is not False:toggle_gap(builder,active,prev,gap)
            builder.cx(gap,shortened)
            if j:builder.cx(prev,shortened)
        if not reverse:bank.compress_completed(j)
        mode=inverse_mode
        if qubit_cap is not None and builder.num_allocated_qubits+43<=qubit_cap:
            mode=False
        scaler=scale_builder(builder,mode)
        rotate(builder,active,shortened,left=True)
        if reverse:
            reciprocal_early(builder,[1]+active[1:],shortened,reverse=True)
            scale_active_reused_mask(scaler,active[0],active[1:],shortened,divide=False)
        else:
            scale_active_reused_mask(scaler,active[0],active[1:],shortened,divide=True)
            reciprocal_early(builder,[1]+active[1:],shortened)
        rotate(builder,active,shortened,left=False)
        with bank.access([j-1,j] if j else [j]) as flags:
            prev,gap=flags[j-1] if j else False,flags[j]
            if j:builder.cx(prev,shortened)
            builder.cx(gap,shortened)
            if reverse and gap is not False:toggle_gap(builder,active,prev,gap)
        builder.free(shortened)
        if reverse and retire and j%4==0:
            block=j//4
            bank._free(bank.blocks.pop(block))
            bank.encoded.discard(block)


def convert_exact_late(builder,words,bank,*,reverse=False,inverse_mode='norm'):
    from .jfraction_decoder import conversion_layout,scale_words
    from .jfraction_gap_decoder import conversion_core,rotate,toggle_header
    scaler=scale_builder(builder,inverse_mode)
    p,q,stages=conversion_layout(words)
    stages=[(bank.count-1-i,*stage) for i,stage in enumerate(stages)]
    for j,x,y,old_p,old_q in reversed(stages) if reverse else stages:
        new_p=[x]+old_q[1:];rotations=[x,y]+old_q[1:]
        if reverse:
            with bank.access([j]) as flags:rotate(builder,new_p,flags[j],left=True)
            scale_words(scaler,x,old_q[1:],divide=True)
        with bank.access([j-1,j] if j else [j]) as flags:
            pending,gap=flags[j-1] if j else False,flags[j]
            if reverse:
                toggle_header(builder,y,old_q,pending)
            else:
                if j:builder.cswap(pending,x,y)
                rotate(builder,rotations,gap,left=True)
            conversion_core(builder,y,old_p,old_q,pending)
            if reverse:
                rotate(builder,rotations,gap,left=False)
                if j:builder.cswap(pending,x,y)
            else:toggle_header(builder,y,old_q,pending)
        if not reverse:
            scale_words(scaler,x,old_q[1:],divide=False)
            with bank.access([j]) as flags:rotate(builder,new_p,flags[j],left=False)
    return p,q


def terminal_zero_bank_class():
    from .compact_gap_variant import GapBank
    class TerminalZeroBank(GapBank):
        """Omit the last gap, which cannot occur on a supported degree<=L chart.

        At the final non-pending slot only one degree remains. A first-order
        gap needs two degrees (four moments); a pending slot already forces
        gap=False. The original higher-order-gap approximation is retained.
        """
        def append(self,index):
            if index==self.count-1:
                assert self.count%4!=0 and index==self.appended
                self.blocks.setdefault(index//4,[]).append(False)
                self.appended+=1
            else:super().append(index)
        def _free(self,bits):
            bits=[bit for bit in bits if bit is not False]
            if bits:super()._free(bits)
    return TerminalZeroBank


def top_power_update_early(builder, words, d, shortened):
    from .jfraction_decoder import GF, add_scaled
    last = len(words) - 1
    terms = [(i, last - d*i) for i in range(1, last//d + 1)]
    if not terms:
        return
    assert all(j > 0 for _, j in terms)
    delta, frobenius = builder.alloc_qubits(12), builder.alloc_qubits(12)
    for i, j in terms:
        add_scaled(builder, words[i], frobenius, frobenius=d)
        builder.ixor_gf2_mul(frobenius, words[j], target=delta, field=GF)
        add_scaled(builder, words[i], frobenius, frobenius=d)
    builder.x(shortened)
    builder.gf2_iadd(delta, target=words[-1], control=shortened, field=GF)
    builder.x(shortened)
    mask = builder.alloc_bits(12)
    builder.hmr(delta, mask)
    builder.free(delta)
    for i, j in terms:
        add_scaled(builder, words[i], frobenius, frobenius=d)
        builder.gf2_phase_by_product(frobenius, words[j], mask=mask, field=GF)
        add_scaled(builder, words[i], frobenius, frobenius=d)
    builder.free(mask + frobenius)


def reciprocal_early(builder, words, shortened, *, reverse=False, early_buffer=True):
    from .jfraction_decoder import power_map
    from .jfraction_gap_decoder import top_power_update
    update = top_power_update_early if early_buffer else top_power_update
    d, exponent, factors = 2, 1, []
    while exponent < len(words) - 1:
        factors.append(d)
        exponent *= 1 + d
        d *= d
    for factor in reversed(factors) if reverse else factors:
        if reverse:
            power_map(builder, words[:-1], factor, reverse=True)
            update(builder, words, factor, shortened)
        else:
            update(builder, words, factor, shortened)
            power_map(builder, words[:-1], factor)


class LeanZeroTest:
    """Unconditional 12-input conjunction: ten intermediates, not eleven."""
    def __init__(self, builder, sigma, enabled=True):
        assert enabled is True
        self.builder, self.sigma = builder, sigma
        self.chain, self.calls = None, 0

    def flip_if_equal(self, lhs, rhs, *, target, control=True):
        assert lhs is self.sigma and rhs == 0 and control is True
        b = self.builder
        self.calls += 1
        b.x(lhs)
        if self.chain is None:
            self.chain = b.alloc_qubits(len(lhs) - 2)
            b.init_and(lhs[0], lhs[1], self.chain[0])
            for i in range(1, len(self.chain)):
                b.init_and(self.chain[i-1], lhs[i+1], self.chain[i])
            b.init_and(self.chain[-1], lhs[-1], target)
        else:
            b.del_and(self.chain[-1], lhs[-1], target)
            for i in reversed(range(1, len(self.chain))):
                b.del_and(self.chain[i-1], lhs[i+1], self.chain[i])
            b.del_and(lhs[0], lhs[1], self.chain[0])
            b.free(self.chain)
            self.chain = None
        b.x(lhs)


def forney_lean(builder, numerator, denominator_tail, outcomes, *, field):
    # Reuse the previously FULL-PASS sigma/inverse lifetime schedule; only
    # specialize its enabled=True zero test. Restore the module after building.
    from . import compact_euclid
    from .compact_lifetime_kernels import forney_reused_sigma
    old = compact_euclid._EnabledZeroTest
    compact_euclid._EnabledZeroTest = LeanZeroTest
    try:
        return forney_reused_sigma(builder, numerator, denominator_tail, outcomes, field=field)
    finally:
        compact_euclid._EnabledZeroTest = old
