# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Exact paired extraction. Idea: Phuc Thai EXP-119a (Apache-2.0).

Independent ViberTeam implementation, including exact zero->1 pivot
extensions. Outputs equal two frozen upstream 3+1 steps on every input.
The inherited two-pointer history policy is a separate approximation.
"""
from contextlib import contextmanager
from functools import cache


@contextmanager
def short(b,bank,j):
    cached=getattr(bank,'_paired_modes',None)
    if cached is not None and j in (cached[0],cached[0]+1):
        yield cached[1][j-cached[0]]
        return
    bit=bank.read(j)
    if j:bank.xor_read(j-1,bit)
    try:yield bit
    finally:
        if j:bank.xor_read(j-1,bit)
        bank.unread(j,bit)


@contextmanager
def modes(b,bank,j):
    cached=getattr(bank,'_paired_modes',None)
    if cached is not None and cached[0]==j:
        yield cached[1]
        return
    with short(b,bank,j) as s,short(b,bank,j+1) as t:
        u,v=b.alloc_qubits(2)
        b.x(t);b.init_and(s,t,u);b.x(t)
        b.x(s);b.init_and(s,t,v);b.x(s)
        try:yield s,t,u,v
        finally:
            b.x(s);b.del_and(s,t,v);b.x(s)
            b.x(t);b.del_and(s,t,u);b.x(t)
            b.free(u);b.free(v)


@contextmanager
def unit_pivot(b,c):
    """c is replaced by c or 1 only inside this exact reversible context."""
    if getattr(b,'_paired_unit',None) is c:
        yield c
        return
    zero=b.alloc_qubits(1)[0]
    b.flip_if_equal(c,0,target=zero);b.cx(zero,c[0])
    try:yield c
    finally:
        b.cx(zero,c[0]);b.flip_if_equal(c,0,target=zero);b.free(zero)


def hold_unit(b,c):
    zero=b.alloc_qubits(1)[0];b.flip_if_equal(c,0,target=zero);b.cx(zero,c[0])
    b._paired_unit=c
    return zero


def drop_unit(b,c,zero):
    del b._paired_unit
    b.cx(zero,c[0]);b.flip_if_equal(c,0,target=zero);b.free(zero)


def scale_unit_active(b,pivot,words,shortened,*,divide):
    """The exact active scaler with a proven nonzero pivot, no repeated test."""
    from .jfraction_decoder import GF
    from .merge_kernels import scale_builder
    inverse,scaffold=scale_builder(b,'small').init_gf2_inverse_with_scaffold(pivot,field=GF)
    temporary=b.alloc_qubits(12)
    factor,undo=(inverse,pivot) if divide else (pivot,inverse)
    plain=words if shortened is False else words[:-1]
    for word in plain:
        b.ixor_gf2_mul(word,factor,target=temporary,field=GF)
        b.swap(word,temporary);b.del_gf2_mul(word,undo,target=temporary,field=GF)
    if shortened is not False:
        word=words[-1];b.ixor_gf2_mul(word,factor,target=temporary,field=GF)
        b.x(shortened);b.cswap(shortened,word,temporary)
        mask=b.alloc_bits(12);b.hmr(temporary,mask)
        b.gf2_phase_by_product(word,factor,mask=mask,field=GF)
        b.init_and(shortened,word,temporary);b.cx(undo,factor)
        b.gf2_phase_by_product(temporary,factor,mask=mask,field=GF)
        b.cx(undo,factor);b.del_and(shortened,word,temporary)
        b.free(mask);b.x(shortened)
    b.free(temporary)
    scale_builder(b,'small').del_gf2_inverse_with_scaffold(pivot,target=inverse,scaffold=scaffold,field=GF)
    b.free(inverse+scaffold)


@cache
def square_gates():
    from .jfraction_decoder import GF
    from .tower import elimination_gates
    return tuple(elimination_gates([GF.pow(1<<i,2) for i in range(12)]))


def square(b,a,*,reverse=False):
    gates=square_gates() if reverse else reversed(square_gates())
    for kind,i,k in gates:getattr(b,kind)(a[i],a[k])


def c_a_square(b,c,a,target,*,control=True):
    from .jfraction_decoder import GF
    with unit_pivot(b,c):
        square(b,a)
        b.ixor_gf2_mul(c,a,target=target,field=GF,control=control)
        square(b,a,reverse=True)


def header_probe(b,w,bank,j,*,reverse=False):
    from .jfraction_decoder import GF
    def high():
        if len(w)>4:b.ixor_gf2_mul(w[1],w[2],target=w[3],field=GF)
        else:
            with short(b,bank,j) as s:
                b.x(s);b.ixor_gf2_mul(w[1],w[2],target=w[3],field=GF,control=s);b.x(s)
    if reverse:c_a_square(b,w[0],w[1],w[2]);high()
    else:high();c_a_square(b,w[0],w[1],w[2])


def toggle_second_gap(b,w,bank,j,target):
    from .jfraction_gap_decoder import rotate,toggle_gap
    with short(b,bank,j) as s:
        rotate(b,w[1:4],s,left=False)
        g=bank.read(j)
        toggle_gap(b,w[2:4],g,target)
        bank.unread(j,g)
        rotate(b,w[1:4],s,left=True)


def toggle_second_zero(b,w,bank,j,z):
    with modes(b,bank,j) as (s,t,u,v):
        b.cswap(u,w[1],w[2]);b.cswap(v,w[2],w[3])
        b.flip_if_equal(w[2],0,target=z)
        b.cswap(v,w[2],w[3]);b.cswap(u,w[1],w[2])


def detect_second(b,w,bank,j,z,*,reverse=False):
    header_probe(b,w,bank,j)
    if reverse:
        toggle_second_zero(b,w,bank,j,z)
        flag=bank.pop(j+1)
        toggle_second_gap(b,w,bank,j,flag)
        b.free(flag)
    else:
        flag=b.alloc_qubits(1)[0]
        toggle_second_gap(b,w,bank,j,flag)
        bank.push(j+1,flag)
        toggle_second_zero(b,w,bank,j,z)
    header_probe(b,w,bank,j,reverse=True)


def pre_extra(b,w,bank,j,z):
    """Coefficient three's z*c*a term; a is stored normalized by c."""
    from .jfraction_decoder import GF
    with modes(b,bank,j) as (s,t,u,v):
        zw=b.alloc_qubits(1)[0]
        b.x(u);b.init_and(z,u,zw);b.x(u)
        ctrl=zw
        if len(w)==4:
            ctrl=b.alloc_qubits(1)[0]
            b.x(s);b.init_and(zw,s,ctrl);b.x(s)
        with unit_pivot(b,w[0]):
            b.ixor_gf2_mul(w[0],w[1],target=w[3],field=GF,control=ctrl)
        if len(w)==4:
            b.x(s);b.del_and(zw,s,ctrl);b.x(s);b.free(ctrl)
        b.x(u);b.del_and(z,u,zw);b.x(u);b.free(zw)


def pre_sweep(b,w,bank,j,z,*,reverse=False):
    from .jfraction_decoder import GF
    with modes(b,bank,j) as (s,t,u,v):
        zu,zw=b.alloc_qubits(2)
        b.init_and(z,u,zu);b.x(u);b.init_and(z,u,zw);b.x(u)
        def inject():
            with unit_pivot(b,w[0]):b.gf2_iadd(w[0],target=w[2],field=GF,control=zw)
        def high():
            b.x(s);b.ixor_gf2_mul(w[1],w[-2],target=w[-1],field=GF,control=s);b.x(s)
            if len(w)>4:
                active=b.alloc_qubits(1)[0]
                b.x(s);b.init_and(zw,s,active);b.x(s)
                b.gf2_iadd(w[-3],target=w[-1],field=GF,control=active)
                b.x(s);b.del_and(zw,s,active);b.x(s);b.free(active)
        if not reverse:
            if len(w)==4:inject()
            high()
        A=b.alloc_qubits(12)
        b.x(u);b.init_and(u,w[1],A);b.x(u)
        b.cx(zu,A[0]) # Share the already-paid product with the z*u shift.
        def low():
            b.cx(zu,A[0])
            c_a_square(b,w[0],A,w[2])
            b.cx(zu,A[0])
        if reverse:low()
        indices=range(3,len(w)-1) if reverse else reversed(range(3,len(w)-1))
        for k in indices:
            last=k==len(w)-1
            if k==3 and not reverse:inject()
            ctrl=True
            if last:
                b.x(s);ctrl=s
            b.ixor_gf2_mul(A,w[k-1],target=w[k],field=GF,control=ctrl)
            if last:b.x(s)
            # The omitted highest coefficient must survive both additions.
            for flag,source in ((zw,w[k-2]),):
                if k==3:continue # already folded into A*(f2+z*c)
                if last:
                    active=b.alloc_qubits(1)[0]
                    b.x(s);b.init_and(flag,s,active);b.x(s)
                    b.gf2_iadd(source,target=w[k],field=GF,control=active)
                    b.x(s);b.del_and(flag,s,active);b.x(s);b.free(active)
                else:b.gf2_iadd(source,target=w[k],field=GF,control=flag)
            if k==3 and reverse:inject()
        if not reverse:low()
        b.cx(zu,A[0])
        b.x(u);b.del_and(u,w[1],A);b.x(u);b.free(A)
        if reverse:
            high()
            if len(w)==4:inject()
        b.x(u);b.del_and(z,u,zw);b.x(u);b.del_and(z,u,zu)
        b.free(zu);b.free(zw)


def u_scale(b,w,bank,j,*,divide=False):
    from .compact_lifetime_kernels import scale_active_reused_mask
    from .merge_kernels import scale_builder
    cached=getattr(bank,'_paired_modes',None)
    if cached is not None and cached[0]==j:
        u=cached[1][2];b.x(u)
        scale_unit_active(b,w[0],[w[1]],u,divide=divide)
        b.x(u)
        return
    # Keep only u across this inverse/scaling, rather than all pair modes.
    u=b.alloc_qubits(1)[0]
    with short(b,bank,j) as s,short(b,bank,j+1) as t:
        b.x(t);b.ccx(s,t,u);b.x(t)
    b.x(u)
    scale_active_reused_mask(scale_builder(b,'small'),w[0],[w[1]],u,divide=divide)
    b.x(u)
    with short(b,bank,j) as s,short(b,bank,j+1) as t:
        b.x(t);b.ccx(s,t,u);b.x(t)
    b.free(u)


def pre_rotate(b,w,bank,j,z,*,reverse=False):
    from .jfraction_gap_decoder import rotate
    def injection():
        with modes(b,bank,j) as (s,t,u,v):
            zu=b.alloc_qubits(1)[0];b.init_and(z,u,zu)
            with unit_pivot(b,w[0]):b.gf2_iadd(w[0],target=w[1],control=zu)
            b.del_and(z,u,zu);b.free(zu)
    if not reverse:u_scale(b,w,bank,j);injection()
    with modes(b,bank,j) as (s,t,u,v):
        if reverse:
            rotate(b,w[2:],v,left=False);rotate(b,w[1:],u,left=True)
        else:
            rotate(b,w[1:],u,left=False);rotate(b,w[2:],v,left=True)
    if reverse:injection();u_scale(b,w,bank,j,divide=True)


def post_sweep(b,w,bank,j,z,*,reverse=False):
    from .jfraction_decoder import GF
    with modes(b,bank,j) as (s,t,u,v):
        zu,zw=b.alloc_qubits(2)
        b.init_and(z,u,zu);b.x(u);b.init_and(z,u,zw);b.x(u)
        def high():
            if len(w)<6:return
            active=b.alloc_qubits(1)[0]
            b.x(s);b.x(t);b.init_and(s,t,active);b.x(t);b.x(s)
            coefficient=b.alloc_qubits(12)
            b.init_and(active,w[1],coefficient);b.cx(zu,coefficient[0])
            b.ixor_gf2_mul(coefficient,w[-2],target=w[-1],field=GF)
            b.cx(zu,coefficient[0]);b.del_and(active,w[1],coefficient);b.free(coefficient)
            b.x(s);b.x(t);b.del_and(s,t,active);b.x(t);b.x(s)
            if len(w)>=8:
                b.x(t);b.init_and(zw,t,active);b.x(t)
                b.gf2_iadd(w[-3],target=w[-1],field=GF,control=active)
                b.x(t);b.del_and(zw,t,active);b.x(t)
            b.free(active)
        if reverse:high()
        A=b.alloc_qubits(12)
        b.x(u);b.init_and(u,w[1],A);b.x(u);b.cx(zu,A[0])
        def a1():
            if len(w)>4:
                b.cx(A,w[3]);b.gf2_iadd(w[2],target=w[3],field=GF,control=u)
            else:
                b.x(t);b.gf2_iadd(A,target=w[3],field=GF,control=t)
                au=b.alloc_qubits(1)[0];b.init_and(t,u,au)
                b.gf2_iadd(w[2],target=w[3],field=GF,control=au)
                b.del_and(t,u,au);b.free(au);b.x(t)
        def correction():
            if len(w)<6:return
            b.ixor_gf2_mul(A,w[3],target=w[4],field=GF)
            # k=2 iff s=t. The same bit controls the b* correction.
            b.cx(t,s);b.x(s)
            b.gf2_iadd(w[2],target=w[4],field=GF,control=s)
            b.x(s);b.cx(t,s)
            b.cx(zw,w[4][0])
            active=v
            if len(w)==6:
                active=b.alloc_qubits(1)[0]
                b.x(t);b.init_and(v,t,active);b.x(t)
            b.gf2_iadd(w[2],target=w[5],field=GF,control=active)
            if len(w)==6:
                b.x(t);b.del_and(v,t,active);b.x(t);b.free(active)
                active=b.alloc_qubits(1)[0]
                b.x(t);b.init_and(zw,t,active);b.x(t)
            else:active=zw
            b.gf2_iadd(w[3],target=w[5],field=GF,control=active)
            if len(w)==6:
                b.x(t);b.del_and(zw,t,active);b.x(t);b.free(active)
        if not reverse:a1();correction()
        indices=reversed(range(5,len(w)-1)) if reverse else range(5,len(w)-1)
        for k in indices:
            last=k==len(w)-1
            if last:b.x(t)
            b.ixor_gf2_mul(A,w[k-1],target=w[k],field=GF,control=t if last else True)
            if last:b.x(t)
            if k>=6:
                active=zw
                if last:
                    active=b.alloc_qubits(1)[0]
                    b.x(t);b.init_and(zw,t,active);b.x(t)
                b.gf2_iadd(w[k-2],target=w[k],field=GF,control=active)
                if last:
                    b.x(t);b.del_and(zw,t,active);b.x(t);b.free(active)
        if reverse:correction();a1()
        b.cx(zu,A[0]);b.x(u);b.del_and(u,w[1],A);b.x(u);b.free(A)
        if not reverse:high()
        b.x(u);b.del_and(z,u,zw);b.x(u);b.del_and(z,u,zu)
        b.free(zu);b.free(zw)


def final_rotate(b,w,bank,j,*,reverse=False):
    from .jfraction_gap_decoder import rotate
    with modes(b,bank,j) as (s,t,u,v):
        b.cx(u,s) # s becomes s&t
        if reverse:
            b.cswap(u,w[0],w[1]);rotate(b,w,s,left=True);rotate(b,w[2:],v,left=True)
        else:
            rotate(b,w[2:],v,left=False);rotate(b,w,s,left=False);b.cswap(u,w[0],w[1])
        b.cx(u,s)


def first_flag(b,w,bank,j,*,reverse=False):
    from .jfraction_gap_decoder import toggle_gap
    flag=bank.pop(j) if reverse else b.alloc_qubits(1)[0]
    prev=bank.read(j-1) if j else False
    toggle_gap(b,w,prev,flag)
    if j:bank.unread(j-1,prev)
    if reverse:b.free(flag)
    else:bank.push(j,flag)


def pair_step(b,w,bank,j,*,reverse=False):
    from .jfraction_decoder import scale_words
    from .jfraction_gap_decoder import rotate
    from .compact_lifetime_kernels import scale_active_reused_mask
    from .merge_kernels import reciprocal_early,scale_builder
    scaler=scale_builder(b,'small')
    if not reverse:
        first_flag(b,w,bank,j)
        with short(b,bank,j) as s:rotate(b,w,s,left=True)
        zc=hold_unit(b,w[0])
        scale_unit_active(b,w[0],[w[1]],False,divide=True)
        z=b.alloc_qubits(1)[0]
        detect_second(b,w,bank,j,z)
        with modes(b,bank,j) as state:
            bank._paired_modes=(j,state)
            try:
                pre_sweep(b,w,bank,j,z)
                pre_rotate(b,w,bank,j,z)
                with short(b,bank,j+1) as t:
                    scale_unit_active(b,w[2],w[3:],t,divide=True)
                    reciprocal_early(b,[1]+w[3:],t)
                scale_unit_active(b,w[0],[w[2]],False,divide=True)
                post_sweep(b,w,bank,j,z)
                b.cx(z,w[2][0]);b.flip_if_equal(w[2],0,target=z);b.free(z)
                drop_unit(b,w[0],zc)
                final_rotate(b,w,bank,j)
            finally:del bank._paired_modes
    else:
        with modes(b,bank,j) as state:
            bank._paired_modes=(j,state)
            try:
                final_rotate(b,w,bank,j,reverse=True)
                zc=hold_unit(b,w[0])
                z=b.alloc_qubits(1)[0];b.flip_if_equal(w[2],0,target=z);b.cx(z,w[2][0])
                post_sweep(b,w,bank,j,z,reverse=True)
                scale_unit_active(b,w[0],[w[2]],False,divide=False)
                with short(b,bank,j+1) as t:
                    reciprocal_early(b,[1]+w[3:],t,reverse=True)
                    scale_unit_active(b,w[2],w[3:],t,divide=False)
                pre_rotate(b,w,bank,j,z,reverse=True)
                pre_sweep(b,w,bank,j,z,reverse=True)
            finally:del bank._paired_modes
        detect_second(b,w,bank,j,z,reverse=True);b.free(z)
        scale_unit_active(b,w[0],[w[1]],False,divide=False)
        drop_unit(b,w[0],zc)
        with short(b,bank,j) as s:rotate(b,w,s,left=False)
        first_flag(b,w,bank,j,reverse=True)


def single_step(b,w,bank,j,*,reverse=False):
    from .jfraction_gap_decoder import rotate
    from .compact_lifetime_kernels import scale_active_reused_mask
    from .merge_kernels import scale_builder,reciprocal_early
    if not reverse:first_flag(b,w,bank,j)
    with short(b,bank,j) as s:
        rotate(b,w,s,left=True)
        scaler=scale_builder(b,'small')
        if reverse:
            reciprocal_early(b,[1]+w[1:],s,reverse=True)
            scale_active_reused_mask(scaler,w[0],w[1:],s,divide=False)
        else:
            scale_active_reused_mask(scaler,w[0],w[1:],s,divide=True)
            reciprocal_early(b,[1]+w[1:],s)
        rotate(b,w,s,left=False)
    if reverse:first_flag(b,w,bank,j,reverse=True)


def extract_paired(b,words,bank,*,reverse=False,min_pair_length=14):
    starts=[];j=0
    while j<bank.count:
        paired=len(words)-2*j>=min_pair_length
        starts.append((j,paired));j+=2 if paired else 1
    for j,paired in reversed(starts) if reverse else starts:
        w=words[2*j:]
        if paired:pair_step(b,w,bank,j,reverse=reverse)
        else:single_step(b,w,bank,j,reverse=reverse)
