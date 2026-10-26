# SPDX-License-Identifier: Apache-2.0
# Port of SomeJoint v7; see PROVENANCE.md and SOURCE_MAP.json.
# Praxen: package imports; production functions only; no notebook runtime.
"T5 adjunct: checked26-AND cubes in whole self-shear interpolation.\n\nThis is a structural arithmetic specialization, but its measured task-level\nopportunity is only about0.5%; it is not claimed as an independent Tier1 win.\nThe old R24 planner/evaluation algebra remains credited in upstream/NOTICE.\nNew field tensor is the field agent's checked GF4-Hermitian construction."
from __future__ import annotations

from . import gold_cube
from .inplace_poly import linear_form
from ..jfraction import jfraction_decoder as jf
from ..jfraction.poly_arithmetic import GF, add_scaled, interpolation_columns
from ..jfraction.model_fast_extraction import shear_cost
ORIGINAL_SHEAR = jf.shear


def cube_vector(b,source,targets,coefficients):
    live=[(w,c) for w,c in zip(targets,coefficients) if w is not None and c]
    if not live:return 0
    pivot,scale=live[0]
    others=[(w,GF.div(c,scale)) for w,c in live[1:]]
    for w,c in others:add_scaled(b,pivot,w,c)
    if scale!=1:b.gf2_idiv(scale,target=pivot,field=GF)
    gold_cube.xor_cube(b.native,source,pivot)
    if scale!=1:b.gf2_imul(scale,target=pivot,field=GF)
    for w,c in reversed(others):add_scaled(b,pivot,w,c)
    return 1


def shear(b,source,target,d,cut,*,constant_zero=False):
    n=len(target)
    evaluations=3*(cut-2)+1 if n>3 else 0
    eligible=(constant_zero and d==2 and n>3 and
              26*evaluations<42*shear_cost(n,d,True,cut))
    if not eligible:
        return ORIGINAL_SHEAR(b,source,target,d,cut,constant_zero=constant_zero)
    assert all(source[i] is target[i] for i in range(cut))
    # A=1+xG: the nonlinear self increment is x^3 G^3. The remaining
    # x^(2i)*a_i^2 terms are GF2-linear and emitted separately below.
    operands=list(source[1:cut])
    outputs=[target[k+3] if cut<=k+3<n else None for k in range(evaluations)]
    for point,column in enumerate(interpolation_columns(evaluations)):
        if not any(w is not None and c for w,c in zip(outputs,column)):continue
        with linear_form(b,operands,[GF.pow(point,i) for i in range(len(operands))]) as value:
            assert not isinstance(value,int)
            cube_vector(b,value,outputs,column)
    for i in range(1,(n-1)//2+1):
        if cut<=2*i<n:add_scaled(b,source[i],target[2*i],frobenius=2)
