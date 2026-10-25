# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""No-held-scratch GF8 controlled inverse, exact classical-mask phase deletion.

3 controlled ANDs + a 3-Toffoli in-place inversion. The HMR quadratic phase
on three input bits has rank2, so each nonzero three-bit mask needs one CCZ
after a linear change. Mean deletion cost7/8T, no quantum scratch.
"""


def inplace_inverse(b,word):
    b.ccx(word[0],word[2],word[1])
    b.cx(word[2],word[0])
    b.cx(word[1],word[2])
    b.ccx(word[1],word[2],word[0])
    b.ccx(word[0],word[2],word[1])


def quadratic_phase(b,control,word,measured):
    for code in range(1,8):
        for i in range(3):
            if not(code>>i&1):b.x(measured[i])
        for i in range(3):b.push_condition(measured[i])
        if code==1:b.ccz(control,word[1],word[2])
        elif code==2:b.ccz(control,word[0],word[1])
        elif code==4:b.ccz(control,word[0],word[2])
        elif code==3:
            b.cx(word[2],word[0]);b.ccz(control,word[0],word[1]);b.cx(word[2],word[0])
        elif code==5:
            b.cx(word[1],word[0]);b.ccz(control,word[0],word[2]);b.cx(word[1],word[0])
        elif code==6:
            b.cx(word[2],word[1]);b.ccz(control,word[0],word[1]);b.cx(word[2],word[1])
        else:
            b.cx(word[0],word[1]);b.cx(word[0],word[2])
            b.ccz(control,word[1],word[2])
            b.cx(word[0],word[2]);b.cx(word[0],word[1])
            b.cz(control,word[0])
        for i in range(3):b.pop_condition()
        for i in range(3):
            if not(code>>i&1):b.x(measured[i])


def builder_class():
    from .common import km
    from .static_divisions import StaticArithmeticBuilder
    class ZeroMaskInverseBuilder(StaticArithmeticBuilder):
        def init_controlled_inverse(self,input,control,*,target='alloc'):
            if len(input)!=3:return super().init_controlled_inverse(input,control,target=target)
            b=self.native
            out=b.alloc_qubits(3) if isinstance(target,str) and target=='alloc' else target
            b.reset(out)
            b.init_and(control,input,out)
            inplace_inverse(b,out)
            return out,km.array([])

        def del_controlled_inverse(self,input,control,*,target,scaffold):
            if len(input)!=3:return super().del_controlled_inverse(input,control,target=target,scaffold=scaffold)
            assert not len(scaffold)
            b=self.native;measured=b.alloc_bits(3)
            b.hmr(target,measured)
            for m,i in ((0,0),(0,1),(2,1),(0,2),(1,2),(2,2)):
                b.ccz(measured[m],control,input[i])
            quadratic_phase(b,control,input,measured)
            b.free(measured)
    return ZeroMaskInverseBuilder
