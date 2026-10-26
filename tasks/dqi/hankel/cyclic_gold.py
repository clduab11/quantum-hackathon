# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
'Cyclic middle-cube interpolation for the T5 Frobenius self-shear.\n\nGeneral cyclic-convolution principle is classical (see the literature\nreview); unused low/high output coefficients permit fewer Gold evaluations.\nAn optional single highest-cube correction removes the only overlapping\nwraparound coefficient. No approximation or randomized choices are used.'
from __future__ import annotations

from contextlib import contextmanager
from functools import cache
from . import gold_extraction as gold
from .inplace_poly import linear_form
from ..jfraction import jfraction_decoder as jf, quadratic_cube, matrix_pair_kernels
from ..jfraction.poly_arithmetic import GF, add_scaled
from ..jfraction.model_fast_extraction import shear_cost
DIVISORS = tuple(n for n in range(1, 4096) if 4095 % n == 0)


@cache
def plan(n,cut):
    old=42*shear_cost(n,2,True,cut)
    best=(old,'original',0,False)
    if n<=3:return best
    whole=26*(3*(cut-2)+1)
    if whole<best[0]:best=(whole,'whole',0,False)
    count=next(q for q in DIVISORS if q>=max(1,n-3,2*cut-3))
    correction=3*(cut-2)>=count and count==2*cut-3
    cost=26*(count+int(correction))
    if cost<best[0]:best=(cost,'cyclic',count,correction)
    return best


def shear(b,source,target,d,cut,*,constant_zero=False):
    n=len(target)
    if not constant_zero or d!=2:
        return gold.ORIGINAL_SHEAR(b,source,target,d,cut,constant_zero=constant_zero)
    cost,method,count,correction=plan(n,cut)
    if method=='original':
        return gold.ORIGINAL_SHEAR(b,source,target,d,cut,constant_zero=True)
    if method=='whole':
        return gold.shear(b,source,target,d,cut,constant_zero=True)
    assert all(source[i] is target[i] for i in range(cut))
    operands=list(source[1:cut])
    indices=list(range(max(cut,3),n))
    outputs=[target[k] for k in indices]
    omega=GF.pow(GF.primitive_element,4095//count)
    for j in range(count):
        point=GF.pow(omega,j)
        weights=[GF.pow(omega,(-j*(k-3))%count) for k in indices]
        with linear_form(b,operands,[GF.pow(point,i) for i in range(len(operands))]) as value:
            assert not isinstance(value,int)
            gold.cube_vector(b,value,outputs,weights)
    if correction:
        assert 3*(cut-2)-count==cut-3
        gold.gold_cube.xor_cube(b.native,source[cut-1],target[cut])
    for i in range(1,(n-1)//2+1):
        if cut<=2*i<n:add_scaled(b,source[i],target[2*i],frobenius=2)


@contextmanager
def installed():
    previous_shear,previous_cube=jf.shear,quadratic_cube.xor_cube
    jf.shear=shear
    quadratic_cube.xor_cube=lambda b,s,t:gold.gold_cube.xor_cube(b.native,s,t)
    try:yield
    finally:jf.shear,quadratic_cube.xor_cube=previous_shear,previous_cube


def extract(b,words,bank,*,reverse=False):
    with installed():
        matrix_pair_kernels.extract_hybrid(b,words,bank,reverse=reverse,
                                          fused=True,matrix_threshold=14)
