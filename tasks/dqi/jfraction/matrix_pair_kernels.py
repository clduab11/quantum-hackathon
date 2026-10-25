# SPDX-License-Identifier: Apache-2.0
# Modified by Praxen: package imports; notebook paths and standalone CLI removed.
"""Direct matrix pair: one reciprocal, only two long gap rotations.

Exact output equivalence to two original steps on every field input.
Idea of paired extraction: Phuc Thai EXP-119a. Matrix derivation/source:
ViberTeam task E; the inherited SomeJoint decoder remains attributed.
"""
from contextlib import contextmanager
from .paired_kernels import short,single_step,scale_unit_active,square
BORROW_ZERO_META=True  # Praxen: fixed paired-v6 schedule; no runtime variant selection.


def zero_flags(b,h,s,t):
    z1,z2=b.alloc_qubits(2)
    b.cswap(s,h[0],h[1]);b.flip_if_equal(h[0],0,target=z1);b.cswap(s,h[0],h[1])
    b.cswap(t,h[2],h[3]);b.flip_if_equal(h[2],0,target=z2);b.cswap(t,h[2],h[3])
    return z1,z2

def clear_zero_flags(b,h,s,t,z1,z2):
    b.cswap(t,h[2],h[3]);b.flip_if_equal(h[2],0,target=z2);b.cswap(t,h[2],h[3])
    b.cswap(s,h[0],h[1]);b.flip_if_equal(h[0],0,target=z1);b.cswap(s,h[0],h[1])
    b.free(z1);b.free(z2)

def first_unit_product(b,h,s,z1,source,target,*,phase=None):
    from .jfraction_decoder import GF
    b.cswap(s,h[0],h[1]);b.cx(z1,h[0][0])
    if phase is None:b.ixor_gf2_mul(h[0],source,target=target,field=GF)
    else:b.gf2_phase_by_product(h[0],source,mask=phase,field=GF)
    b.cx(z1,h[0][0]);b.cswap(s,h[0],h[1])

def make_factor(b,h,t,z2,target):
    b.x(t);b.init_and(t,h[2],target);b.x(t);b.cx(t,target[0])
    flag=b.alloc_qubits(1)[0];b.x(t);b.init_and(t,z2,flag);b.x(t)
    b.cx(flag,target[0]);b.x(t);b.del_and(t,z2,flag);b.x(t);b.free(flag)

def clear_factor(b,h,t,z2,target):
    flag=b.alloc_qubits(1)[0];b.x(t);b.init_and(t,z2,flag);b.x(t)
    b.cx(flag,target[0]);b.x(t);b.del_and(t,z2,flag);b.x(t);b.free(flag)
    b.cx(t,target[0]);b.x(t);b.del_and(t,h[2],target);b.x(t)

def make_B(b,h,s,t,z2,out,work,index):
    from .jfraction_decoder import GF
    from .quadratic_cube import xor_cube,phase_cube
    if index==2:
        b.cx(h[2],out);b.x(s);b.init_and(s,h[1],work);b.x(s)
        square(b,work);b.cx(work,out);square(b,work,reverse=True)
        b.x(s);b.del_and(s,h[1],work);b.x(s)
        return
    make_factor(b,h,t,z2,work)
    b.ixor_gf2_mul(work,h[3],target=out,field=GF)
    clear_factor(b,h,t,z2,work)
    b.init_and(s,h[2],work);square(b,work);b.cx(work,out);square(b,work,reverse=True)
    b.del_and(s,h[2],work)
    xor_cube(b,h[1],work);b.x(s);b.gf2_iadd(work,target=out,field=GF,control=s);b.x(s)
    measured=b.alloc_bits(12);b.hmr(work,measured);phase_cube(b,h[1],measured);b.free(measured)

def phase_B(b,h,s,t,z2,mask,index,work):
    from .jfraction_decoder import GF
    from .quadratic_cube import phase_cube
    if index==2:
        for i in range(12):b.cz(mask[i],h[2][i])
        square(b,h[1]);b.x(s)
        for i in range(12):b.ccz(mask[i],s,h[1][i])
        b.x(s);square(b,h[1],reverse=True)
        return
    make_factor(b,h,t,z2,work)
    b.gf2_phase_by_product(work,h[3],mask=mask,field=GF)
    clear_factor(b,h,t,z2,work)
    square(b,h[2])
    for i in range(12):b.ccz(mask[i],s,h[2][i])
    square(b,h[2],reverse=True)
    b.x(s);phase_cube(b,h[1],mask,control=s);b.x(s)

def erase_B(b,h,s,t,z2,word,index):
    mask=b.alloc_bits(12);b.hmr(word,mask)
    phase_B(b,h,s,t,z2,mask,index,word);b.free(mask)

@contextmanager
def raw_moment(b,h,s,t,z1,z2,index):
    """Recover one original prefix coefficient in two field words, MBU erase."""
    lhs,result=b.alloc_qubits(12),b.alloc_qubits(12)
    make_B(b,h,s,t,z2,lhs,result,index)
    first_unit_product(b,h,s,z1,lhs,result)
    erase_B(b,h,s,t,z2,lhs,index);b.free(lhs)
    try:yield result
    finally:
        mask=b.alloc_bits(12);b.hmr(result,mask)
        lhs=b.alloc_qubits(12)
        make_B(b,h,s,t,z2,lhs,result,index)
        first_unit_product(b,h,s,z1,lhs,None,phase=mask)
        erase_B(b,h,s,t,z2,lhs,index)
        b.free(mask+lhs+result)

@contextmanager
def coefficients(b,h,s,t,z2):
    """Cbar=1+A*x+B*x^2. A uses one field word, B one bit."""
    A=b.alloc_qubits(12)
    b.x(s);b.init_and(s,h[1],A);b.x(s)
    flag=b.alloc_qubits(1)[0];b.init_and(s,t,flag)
    b.ccx(flag,h[2],A);b.del_and(s,t,flag)
    b.x(t);b.init_and(s,t,flag);b.x(t)
    b.ccx(flag,z2,A[0])
    b.x(t);b.del_and(s,t,flag);b.x(t);b.free(flag)
    B=b.alloc_qubits(1)[0];b.cx(t,s);b.x(s);b.init_and(s,z2,B);b.x(s);b.cx(t,s)
    try:yield A,B
    finally:
        b.cx(t,s);b.x(s);b.del_and(s,z2,B);b.x(s);b.cx(t,s);b.free(B)
        mask=b.alloc_bits(12);b.hmr(A,mask);b.free(A)
        b.x(s)
        for i in range(12):b.ccz(mask[i],s,h[1][i])
        b.x(s)
        flag=b.alloc_qubits(1)[0];b.init_and(s,t,flag)
        for i in range(12):b.ccz(mask[i],flag,h[2][i])
        b.del_and(s,t,flag)
        b.x(t);b.init_and(s,t,flag);b.x(t)
        b.ccz(mask[0],flag,z2)
        b.x(t);b.del_and(s,t,flag);b.x(t);b.free(flag);b.free(mask)

def pre_body(b,h,s,t,z1,z2,*,reverse=False):
    from .jfraction_decoder import GF
    def bulk():
        with coefficients(b,h,s,t,z2) as (A,B):
            for i in range(6,len(h)) if reverse else reversed(range(6,len(h))):
                b.ixor_gf2_mul(A,h[i-1],target=h[i],field=GF)
                b.gf2_iadd(h[i-2],target=h[i],field=GF,control=B)
    def fifth():
        if len(h)>5:
            with coefficients(b,h,s,t,z2) as (A,B):b.ixor_gf2_mul(A,h[4],target=h[5],field=GF)
    def third_source():
        with raw_moment(b,h,s,t,z1,z2,3) as raw:
            with coefficients(b,h,s,t,z2) as (A,B):
                if len(h)>5:b.gf2_iadd(raw,target=h[5],field=GF,control=B)
                b.ixor_gf2_mul(A,raw,target=h[4],field=GF)
    def second_source():
        with raw_moment(b,h,s,t,z1,z2,2) as raw:
            with coefficients(b,h,s,t,z2) as (A,B):b.gf2_iadd(raw,target=h[4],field=GF,control=B)
    if reverse:second_source();third_source();fifth();bulk()
    else:bulk();fifth();third_source();second_source()

def header_H1(b,h,s,t):
    from .jfraction_decoder import GF
    flag=b.alloc_qubits(1)[0]
    b.x(s);b.x(t);b.init_and(s,t,flag);b.x(t);b.x(s)
    b.gf2_iadd(h[1],target=h[3],field=GF,control=flag)
    b.x(s);b.x(t);b.del_and(s,t,flag);b.x(t);b.x(s)
    b.x(t);b.init_and(s,t,flag);b.x(t)
    b.gf2_iadd(h[2],target=h[3],field=GF,control=flag)
    b.x(t);b.del_and(s,t,flag);b.x(t);b.free(flag)

def reciprocal_body(b,h,s,t,z1,z2,*,reverse=False):
    from .jfraction_gap_decoder import rotate
    from .merge_kernels import reciprocal_early
    b.cswap(s,h[0],h[1]);b.cx(z1,h[0][0])
    header_H1(b,h,s,t)
    b.cswap(t,h[2],h[3]);b.cx(z2,h[2][0])
    scale_unit_active(b,h[0],[h[2]],False,divide=False)
    if not reverse:scale_unit_active(b,h[2],h[4:],False,divide=True)
    rotate(b,h[3:],t,left=True)
    reciprocal_early(b,[1]+h[3:],t,reverse=reverse)
    rotate(b,h[3:],t,left=False)
    if reverse:scale_unit_active(b,h[2],h[4:],False,divide=False)
    scale_unit_active(b,h[0],[h[2]],False,divide=True)
    b.cx(z2,h[2][0]);b.cswap(t,h[2],h[3])
    header_H1(b,h,s,t)
    b.cx(z1,h[0][0]);b.cswap(s,h[0],h[1])

def body_correction(b,h,s,t):
    from .jfraction_decoder import GF
    # s=t=0: add a1*a2+c2 to the constant body coefficient.
    flag=b.alloc_qubits(1)[0];b.x(s);b.x(t);b.init_and(s,t,flag);b.x(t);b.x(s)
    b.ixor_gf2_mul(h[1],h[3],target=h[4],field=GF,control=flag)
    b.gf2_iadd(h[2],target=h[4],field=GF,control=flag)
    b.x(s);b.x(t);b.del_and(s,t,flag);b.x(t);b.x(s)
    # s=0,t=1: add a1 to body[0] and c2 to body[2].
    b.x(s);b.init_and(s,t,flag);b.x(s)
    b.gf2_iadd(h[1],target=h[4],field=GF,control=flag)
    if len(h)>6:b.gf2_iadd(h[3],target=h[6],field=GF,control=flag)
    b.x(s);b.del_and(s,t,flag);b.x(s)
    # s=t=1: add kept first coefficient and second pivot.
    b.init_and(s,t,flag)
    b.gf2_iadd(h[2],target=h[4],field=GF,control=flag)
    if len(h)>5:b.gf2_iadd(h[3],target=h[5],field=GF,control=flag)
    b.del_and(s,t,flag);b.free(flag)

def post_body(b,h,s,t,z2,*,reverse=False):
    from .jfraction_decoder import GF
    if not reverse:body_correction(b,h,s,t)
    with coefficients(b,h,s,t,z2) as (A,B):
        for i in reversed(range(5,len(h))) if reverse else range(5,len(h)):
            b.ixor_gf2_mul(A,h[i-1],target=h[i],field=GF)
            if i>=6:b.gf2_iadd(h[i-2],target=h[i],field=GF,control=B)
    if reverse:body_correction(b,h,s,t)

def matrix_pair_step(b,h,bank,j,*,reverse=False):
    assert len(h)>=6
    if not reverse:
        single_step(b,h[:4],bank,j)
        single_step(b,h[2:4],bank,j+1)
    with short(b,bank,j) as s,short(b,bank,j+1) as t:
        z1,z2=zero_flags(b,h,s,t)
        if reverse:
            post_body(b,h,s,t,z2,reverse=True)
            reciprocal_body(b,h,s,t,z1,z2,reverse=True)
            pre_body(b,h,s,t,z1,z2,reverse=True)
        else:
            pre_body(b,h,s,t,z1,z2)
            reciprocal_body(b,h,s,t,z1,z2)
            post_body(b,h,s,t,z2)
        clear_zero_flags(b,h,s,t,z1,z2)
    if reverse:
        single_step(b,h[2:4],bank,j+1,reverse=True)
        single_step(b,h[:4],bank,j,reverse=True)

def extract_matrix_paired(b,words,bank,*,reverse=False,min_pair_length=22):
    stages=[];j=0
    while j<bank.count:
        paired=len(words)-2*j>=min_pair_length
        stages.append((j,paired));j+=2 if paired else 1
    for j,paired in reversed(stages) if reverse else stages:
        if paired:matrix_pair_step(b,words[2*j:],bank,j,reverse=reverse)
        else:single_step(b,words[2*j:],bank,j,reverse=reverse)

def extract_hybrid(b,words,bank,*,reverse=False,matrix_threshold=18,fused=False):
    from .paired_kernels import pair_step
    stages=[];j=0
    while j<bank.count:
        n=len(words)-2*j
        kind='matrix' if n>=matrix_threshold else 'pair' if n>=14 else 'single'
        stages.append((j,kind));j+=1 if kind=='single' else 2
    for j,kind in reversed(stages) if reverse else stages:
        fn=(fused_matrix_pair_step if fused else fast_matrix_pair_step) if kind=='matrix' else pair_step if kind=='pair' else single_step
        fn(b,words[2*j:],bank,j,reverse=reverse)


def held_scale(b,pivot,inverse,words,shortened,*,divide):
    """Use a retained scalar reciprocal; caller owns its exact MBU deletion."""
    from .jfraction_decoder import GF
    temporary=b.alloc_qubits(12);factor,undo=(inverse,pivot) if divide else (pivot,inverse)
    for word in words if shortened is False else words[:-1]:
        b.ixor_gf2_mul(word,factor,target=temporary,field=GF)
        b.swap(word,temporary);b.del_gf2_mul(word,undo,target=temporary,field=GF)
    if shortened is not False:
        word=words[-1];b.ixor_gf2_mul(word,factor,target=temporary,field=GF)
        b.x(shortened);b.cswap(shortened,word,temporary)
        mask=b.alloc_bits(12);b.hmr(temporary,mask)
        b.gf2_phase_by_product(word,factor,mask=mask,field=GF)
        b.init_and(shortened,word,temporary);b.cx(undo,factor)
        b.gf2_phase_by_product(temporary,factor,mask=mask,field=GF)
        b.cx(undo,factor);b.del_and(shortened,word,temporary);b.x(shortened);b.free(mask)
    b.free(temporary)


def pre_partial(b,h,s,t,z2,*,reverse=False):
    """Raw tail still survives: only three boundary word corrections."""
    from .jfraction_decoder import GF
    b.cswap(s,h[2],h[3]) # Original f3 now sits in h3 on both charts.
    u=b.alloc_qubits(1)[0];b.x(t);b.init_and(s,t,u);b.x(t)
    A=b.alloc_qubits(12);b.x(u);b.init_and(u,h[1],A);b.x(u);b.ccx(u,z2,A[0])
    b.x(t);b.del_and(s,t,u);b.x(t);b.free(u)
    B=b.alloc_qubits(1)[0];b.cx(t,s);b.x(s);b.init_and(s,z2,B);b.x(s);b.cx(t,s)
    def boundary():
        flag=b.alloc_qubits(1)[0];b.init_and(s,B,flag)
        b.gf2_iadd(h[0],target=h[3],field=GF,control=flag)
        b.ixor_gf2_mul(A,h[3],target=h[4],field=GF)
        b.gf2_iadd(h[0],target=h[3],field=GF,control=flag)
        b.del_and(s,B,flag)
        b.x(s);b.init_and(s,B,flag);b.x(s)
        b.gf2_iadd(h[2],target=h[4],field=GF,control=flag)
        b.x(s);b.del_and(s,B,flag);b.x(s);b.free(flag)
    if reverse:boundary()
    for i in range(5,len(h)) if reverse else reversed(range(5,len(h))):
        b.ixor_gf2_mul(A,h[i-1],target=h[i],field=GF)
        b.gf2_iadd(h[i-2],target=h[i],field=GF,control=B)
    if not reverse:boundary()
    b.cx(t,s);b.x(s);b.del_and(s,z2,B);b.x(s);b.cx(t,s);b.free(B)
    u=b.alloc_qubits(1)[0];b.x(t);b.init_and(s,t,u);b.x(t)
    b.ccx(u,z2,A[0]);b.x(u);b.del_and(u,h[1],A);b.x(u);b.free(A)
    b.x(t);b.del_and(s,t,u);b.x(t);b.free(u)
    b.cswap(s,h[2],h[3])


def fast_matrix_pair_step(b,h,bank,j,*,reverse=False):
    """Retain one reciprocal while raw boundary moments are still available."""
    from .jfraction_decoder import GF
    from .jfraction_gap_decoder import rotate
    from .merge_kernels import reciprocal_early,scale_builder
    from .compact_lifetime_kernels import scale_active_reused_mask
    from .paired_kernels import first_flag
    assert len(h)>=6
    scaler=scale_builder(b,'small')
    if not reverse:
        first_flag(b,h[:4],bank,j)
        with short(b,bank,j) as s:rotate(b,h[:4],s,left=True)
        z1=b.alloc_qubits(1)[0];b.flip_if_equal(h[0],0,target=z1);b.cx(z1,h[0][0]);b._paired_unit=h[0]
        inverse,scaffold=scaler.init_gf2_inverse_with_scaffold(h[0],field=GF)
        held_scale(b,h[0],inverse,[h[1]],False,divide=True)
        z2=b.alloc_qubits(1)[0];detect_second_lowspace(b,h[:4],bank,j,z2)
        with short(b,bank,j) as s,short(b,bank,j+1) as t:
            pre_partial(b,h,s,t,z2)
            held_scale(b,h[0],inverse,h[2:4],s,divide=True)
            scaler.del_gf2_inverse_with_scaffold(h[0],target=inverse,scaffold=scaffold,field=GF);b.free(inverse+scaffold)
            reciprocal_early(b,[1]+h[1:4],s)
            b.cx(z1,h[0][0]);del b._paired_unit
            rotate(b,h[:4],s,left=False)
            scale_active_reused_mask(scaler,h[2],[h[3]],t,divide=True)
            reciprocal_body(b,h,s,t,z1,z2)
            post_body(b,h,s,t,z2)
            clear_zero_flags(b,h,s,t,z1,z2)
    else:
        with short(b,bank,j) as s,short(b,bank,j+1) as t:
            z1,z2=zero_flags(b,h,s,t)
            post_body(b,h,s,t,z2,reverse=True)
            reciprocal_body(b,h,s,t,z1,z2,reverse=True)
            scale_active_reused_mask(scaler,h[2],[h[3]],t,divide=False)
            rotate(b,h[:4],s,left=True)
            b.cx(z1,h[0][0]);b._paired_unit=h[0]
            reciprocal_early(b,[1]+h[1:4],s,reverse=True)
            inverse,scaffold=scaler.init_gf2_inverse_with_scaffold(h[0],field=GF)
            held_scale(b,h[0],inverse,h[2:4],s,divide=False)
            pre_partial(b,h,s,t,z2,reverse=True)
        detect_second_lowspace(b,h[:4],bank,j,z2,reverse=True);b.free(z2)
        held_scale(b,h[0],inverse,[h[1]],False,divide=False)
        scaler.del_gf2_inverse_with_scaffold(h[0],target=inverse,scaffold=scaffold,field=GF);b.free(inverse+scaffold)
        b.cx(z1,h[0][0]);del b._paired_unit
        b.flip_if_equal(h[0],0,target=z1);b.free(z1)
        with short(b,bank,j) as s:rotate(b,h[:4],s,left=False)
        first_flag(b,h[:4],bank,j,reverse=True)


def lowspace_toggle_second_gap(b,h,bank,j,target):
    from .jfraction_gap_decoder import rotate
    with short(b,bank,j) as s:
        rotate(b,h[1:4],s,left=False)
        previous=bank.read(j)
        z0,z1=b.alloc_qubits(2)
        xor_zero12(b,h[2],z0);xor_zero12(b,h[3],z1)
        enabled=b.alloc_qubits(1)[0];b.x(previous);b.init_and(previous,z0,enabled);b.x(previous)
        b.x(z1);b.ccx(enabled,z1,target);b.x(z1)
        b.x(previous);b.del_and(previous,z0,enabled);b.x(previous);b.free(enabled)
        xor_zero12(b,h[3],z1);xor_zero12(b,h[2],z0);b.free(z0);b.free(z1)
        bank.unread(j,previous)
        rotate(b,h[1:4],s,left=True)


def detect_second_lowspace(b,h,bank,j,z,*,reverse=False):
    from .paired_kernels import header_probe
    header_probe(b,h,bank,j)
    if reverse:
        second_zero_lean(b,h,bank,j,z)
        flag=bank.pop(j+1);lowspace_toggle_second_gap(b,h,bank,j,flag);b.free(flag)
    else:
        flag=b.alloc_qubits(1)[0];lowspace_toggle_second_gap(b,h,bank,j,flag);bank.push(j+1,flag)
        second_zero_lean(b,h,bank,j,z)
    header_probe(b,h,bank,j,reverse=True)


def xor_zero12(b,word,target):
    """12-input zero conjunction with ten disposable AND intermediates."""
    b.x(word);chain=b.alloc_qubits(10)
    b.init_and(word[0],word[1],chain[0])
    for i in range(1,10):b.init_and(chain[i-1],word[i+1],chain[i])
    b.ccx(chain[9],word[11],target)
    for i in reversed(range(1,10)):b.del_and(chain[i-1],word[i+1],chain[i])
    b.del_and(word[0],word[1],chain[0]);b.free(chain);b.x(word)


def second_zero_lean(b,h,bank,j,z):
    from .paired_kernels import modes
    with modes(b,bank,j) as (s,t,u,v):
        b.cswap(u,h[1],h[2]);b.cswap(v,h[2],h[3])
        xor_zero12(b,h[2],z)
        b.cswap(v,h[2],h[3]);b.cswap(u,h[1],h[2])


def reciprocal_four(b,h,s):
    """[1,a,b,c]^-1=[1,a,b+a^2,c+a^3], only one field temporary."""
    from .jfraction_decoder import GF,add_scaled
    from .quadratic_cube import xor_cube,phase_cube
    temporary=b.alloc_qubits(12);xor_cube(b,h[1],temporary)
    b.x(s);b.gf2_iadd(temporary,target=h[3],field=GF,control=s);b.x(s)
    mask=b.alloc_bits(12);b.hmr(temporary,mask);phase_cube(b,h[1],mask);b.free(mask+temporary)
    add_scaled(b,h[1],h[2],frobenius=2)


def mix_H1_numerator(b,h,s,t,z2):
    """h3 += (c2 or 1)*R, R=a1 or c2, on the full second slot."""
    from .jfraction_decoder import GF
    flag=b.alloc_qubits(1)[0]
    b.x(s);b.x(t);b.init_and(s,t,flag);b.x(t);b.x(s)
    b.ixor_gf2_mul(h[1],h[2],target=h[3],field=GF,control=flag)
    b.x(s);b.x(t);b.del_and(s,t,flag);b.x(t);b.x(s)
    b.x(t);b.init_and(s,t,flag);b.x(t)
    square(b,h[2]);b.gf2_iadd(h[2],target=h[3],field=GF,control=flag);square(b,h[2],reverse=True)
    zero=b.alloc_qubits(1)[0];b.init_and(flag,z2,zero)
    b.gf2_iadd(h[2],target=h[3],field=GF,control=zero)
    b.del_and(flag,z2,zero);b.free(zero)
    b.x(t);b.del_and(s,t,flag);b.x(t);b.free(flag)


def clear_held(b,source,inverse,scaffold):
    from .jfraction_decoder import GF
    from .merge_kernels import scale_builder
    scale_builder(b,'small').del_gf2_inverse_with_scaffold(source,target=inverse,scaffold=scaffold,field=GF)
    b.free(inverse+scaffold)


def fused_middle_forward(b,h,s,t,z1,z2,inverse,scaffold):
    from .jfraction_decoder import GF
    from .jfraction_gap_decoder import rotate
    from .merge_kernels import reciprocal_early,scale_builder
    held_scale(b,h[0],inverse,h[2:4],s,divide=True)
    reciprocal_four(b,h,s)
    b.cx(z1,h[0][0]);rotate(b,h[:4],s,left=False)
    b.cswap(s,h[0],h[1]);b.cx(z1,h[0][0])
    b.cswap(t,h[2],h[3]);b.cx(z2,h[2][0])
    mix_H1_numerator(b,h,s,t,z2)
    held_scale(b,h[0],inverse,[h[3]],t,divide=False)
    held_scale(b,h[0],inverse,[h[2]],False,divide=False)
    clear_held(b,h[0],inverse,scaffold)
    reciprocal,chain=scale_builder(b,'small').init_gf2_inverse_with_scaffold(h[2],field=GF)
    held_scale(b,h[2],reciprocal,[h[3]],t,divide=True)
    held_scale(b,h[2],reciprocal,h[4:],False,divide=True)
    clear_held(b,h[2],reciprocal,chain)
    rotate(b,h[3:],t,left=True);reciprocal_early(b,[1]+h[3:],t);rotate(b,h[3:],t,left=False)
    scale_unit_active(b,h[0],[h[2]],False,divide=True)
    b.cx(z2,h[2][0]);b.cswap(t,h[2],h[3]);header_H1(b,h,s,t)
    b.cx(z1,h[0][0]);b.cswap(s,h[0],h[1]);del b._paired_unit


def fused_middle_reverse(b,h,s,t,z1,z2):
    from .jfraction_decoder import GF
    from .jfraction_gap_decoder import rotate
    from .merge_kernels import reciprocal_early,scale_builder
    b.cswap(s,h[0],h[1]);b.cx(z1,h[0][0]);b._paired_unit=h[0]
    header_H1(b,h,s,t);b.cswap(t,h[2],h[3]);b.cx(z2,h[2][0])
    scale_unit_active(b,h[0],[h[2]],False,divide=False)
    rotate(b,h[3:],t,left=True);reciprocal_early(b,[1]+h[3:],t,reverse=True);rotate(b,h[3:],t,left=False)
    reciprocal,chain=scale_builder(b,'small').init_gf2_inverse_with_scaffold(h[2],field=GF)
    held_scale(b,h[2],reciprocal,h[4:],False,divide=False)
    held_scale(b,h[2],reciprocal,[h[3]],t,divide=False)
    clear_held(b,h[2],reciprocal,chain)
    inverse,scaffold=scale_builder(b,'small').init_gf2_inverse_with_scaffold(h[0],field=GF)
    held_scale(b,h[0],inverse,[h[2]],False,divide=True)
    held_scale(b,h[0],inverse,[h[3]],t,divide=True)
    mix_H1_numerator(b,h,s,t,z2)
    b.cx(z2,h[2][0]);b.cswap(t,h[2],h[3])
    b.cx(z1,h[0][0]);b.cswap(s,h[0],h[1])
    rotate(b,h[:4],s,left=True);b.cx(z1,h[0][0])
    reciprocal_four(b,h,s)
    held_scale(b,h[0],inverse,h[2:4],s,divide=False)
    return inverse,scaffold


def fused_matrix_pair_step(b,h,bank,j,*,reverse=False):
    from .jfraction_decoder import GF
    from .jfraction_gap_decoder import rotate
    from .merge_kernels import scale_builder
    from .paired_kernels import first_flag
    assert len(h)>=6;scaler=scale_builder(b,'small')
    if not reverse:
        first_flag(b,h[:4],bank,j)
        with short(b,bank,j) as s:rotate(b,h[:4],s,left=True)
        z1=b.alloc_qubits(1)[0];b.flip_if_equal(h[0],0,target=z1);b.cx(z1,h[0][0]);b._paired_unit=h[0]
        inverse,scaffold=scaler.init_gf2_inverse_with_scaffold(h[0],field=GF)
        held_scale(b,h[0],inverse,[h[1]],False,divide=True)
        z2=b.alloc_qubits(1)[0];detect_second_lowspace(b,h[:4],bank,j,z2)
        with short(b,bank,j) as s,short(b,bank,j+1) as t:
            if BORROW_ZERO_META:pre_partial_borrow(b,h,s,t,z2,z1=z1)
            else:pre_partial(b,h,s,t,z2)
            fused_middle_forward(b,h,s,t,z1,z2,inverse,scaffold)
            post_body(b,h,s,t,z2);clear_zero_flags(b,h,s,t,z1,z2)
    else:
        with short(b,bank,j) as s,short(b,bank,j+1) as t:
            z1,z2=zero_flags(b,h,s,t);post_body(b,h,s,t,z2,reverse=True)
            inverse,scaffold=fused_middle_reverse(b,h,s,t,z1,z2)
            if BORROW_ZERO_META:pre_partial_borrow(b,h,s,t,z2,z1=z1,reverse=True)
            else:pre_partial(b,h,s,t,z2,reverse=True)
        detect_second_lowspace(b,h[:4],bank,j,z2,reverse=True);b.free(z2)
        held_scale(b,h[0],inverse,[h[1]],False,divide=False);clear_held(b,h[0],inverse,scaffold)
        b.cx(z1,h[0][0]);del b._paired_unit;b.flip_if_equal(h[0],0,target=z1);b.free(z1)
        with short(b,bank,j) as s:rotate(b,h[:4],s,left=False)
        first_flag(b,h[:4],bank,j,reverse=True)


def pre_partial_borrow(b,h,s,t,z2,*,z1,reverse=False):
    """Borrow the original pivot-zero bit, with exact dirty-bit corrections."""
    from .jfraction_decoder import GF
    b.cswap(s,h[2],h[3])
    u=b.alloc_qubits(1)[0];b.x(t);b.init_and(s,t,u);b.x(t)
    A=b.alloc_qubits(12);b.x(u);b.init_and(u,h[1],A);b.x(u);b.ccx(u,z2,A[0])
    b.x(t);b.del_and(s,t,u);b.x(t);b.free(u)
    B=b.alloc_qubits(1)[0];b.cx(t,s);b.x(s);b.init_and(s,z2,B);b.x(s);b.cx(t,s)
    def boundary():
        # z1'=z1 XOR s*B. The old z1 contribution is A*z1 because
        # z1=1 implies that the regularized pivot h0 is exactly1.
        b.ccx(s,B,z1)
        b.gf2_iadd(h[0],target=h[3],field=GF,control=z1)
        b.ixor_gf2_mul(A,h[3],target=h[4],field=GF)
        b.gf2_iadd(h[0],target=h[3],field=GF,control=z1)
        b.ccx(s,B,z1)
        b.gf2_iadd(A,target=h[4],field=GF,control=z1)
        # Borrow the same bit for (!s)*B; the two old-bit terms cancel.
        b.x(s);b.ccx(s,B,z1);b.x(s)
        b.gf2_iadd(h[2],target=h[4],field=GF,control=z1)
        b.x(s);b.ccx(s,B,z1);b.x(s)
        b.gf2_iadd(h[2],target=h[4],field=GF,control=z1)
    if reverse:boundary()
    for i in range(5,len(h)) if reverse else reversed(range(5,len(h))):
        b.ixor_gf2_mul(A,h[i-1],target=h[i],field=GF)
        b.gf2_iadd(h[i-2],target=h[i],field=GF,control=B)
    if not reverse:boundary()
    b.cx(t,s);b.x(s);b.del_and(s,z2,B);b.x(s);b.cx(t,s);b.free(B)
    u=b.alloc_qubits(1)[0];b.x(t);b.init_and(s,t,u);b.x(t)
    b.ccx(u,z2,A[0]);b.x(u);b.del_and(u,h[1],A);b.x(u);b.free(A)
    b.x(t);b.del_and(s,t,u);b.x(t);b.free(u)
    b.cswap(s,h[2],h[3])
