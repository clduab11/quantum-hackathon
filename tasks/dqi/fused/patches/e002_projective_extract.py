# SPDX-License-Identifier: Apache-2.0
"""Edit 002: projective left-looking extract for targets in groups >= 5.

hengck23 iter 004 (discussion 753607): ΔT −15,259, ΔQ +12 (889→901),
jets 289→16, 0 failures.

Classical oracle: ledger/evidence/pra322-hengck23/projective_classical.py.

Kickmix free recycles qubits without clearing them — never free a non-|0>
register (inv(N) clear fails at N=0). Keep Di live for reverse instead.

Projective D starts at 1 and is only replaced by nonzero N, so D≠0 is an
invariant. After ``if N≠0: swap(N,D)``, the swap flag equals (N≠0) again and
must be uncomputed from post-swap N — never HMR/reset (those give ~50% phase).

Q-cut note (PRA-322): HMR / XOR-clear of N·Di after to_affine (and HMR-park of
W) reproducibly yields 100% value_errors under kickmix verify. Live N+Di through
synthesis is value+phase correct at Q 1513; reclaiming the 13×48 qubits needs a
non-HMR uncompute (e.g. clear via u·D_token) — still open.
"""
from __future__ import annotations

from pathlib import Path

RELPATH = Path('exp/confluent_extract/kernel.py')
MARKER = 'def translate(b,words,head,target,c):'
REPLACEMENT = '''def translate(b,words,head,target,c):
    a,z=words[2*head:2*head+2]
    b.cx(a,words[target]);cx(b,z,words[target],c);b.cx(z,words[target+1]);b.cx(z,words[target+2])

def _ehead_xor(b,a,z,c,target24):
    b.cx(a,target24[:12]);cx(b,z,target24[:12],c);b.cx(z,target24[12:])

def _cswap24(b,ctrl,x,y):
    for i in range(24):b.cswap(ctrl,x[i],y[i])

def _square24_ext_inplace(b,x,undo=False):
    from exp.arithmetic.field import extension_columns, square_columns, linear_inplace, inverse_columns
    cols,frm,_=extension_columns(K)
    sq=square_columns(24)
    linear_inplace(b,x,cols)
    linear_inplace(b,x,inverse_columns(sq)if undo else sq)
    linear_inplace(b,x,frm)

def _mul_low12_into24(b,x24,z12,out24):
    from exp.noscratch.kernels import mul_xor_noscratch
    mul_xor_noscratch(b,x24[:12],z12,out24[:12])
    mul_xor_noscratch(b,x24[12:],z12,out24[12:])

def _nz_swap24(b,u,d):
    """If u≠0 swap u↔d. Coherent: uncompute flag from post-swap u (D≠0 invariant)."""
    from exp.decoder.common import zero_hold,zero_free
    tmp=b.alloc_qubits(24)
    b.cx(u,tmp)
    lad=zero_hold(b,tmp)
    flag=b.alloc_qubits(1)
    b.x(lad[-1]);b.cx(lad[-1],flag[0]);b.x(lad[-1])
    zero_free(b,tmp,lad)
    _cswap24(b,flag[0],u,d)
    for i in range(24):b.ccx(flag[0],d[i],tmp[i])
    b.cx(u,tmp)
    lad=zero_hold(b,tmp)
    b.x(lad[-1]);b.cx(lad[-1],flag[0]);b.x(lad[-1])
    zero_free(b,tmp,lad)
    b.free(flag)
    b.cx(u,tmp)
    b.free(tmp)

def extract(b,words,jet_forward,jet_reverse,reverse=False,transcript=None,
            inverse_forward=inverse24_forward190,inverse_reverse=inverse24_reverse209,
            projective_thresh=5):
    """Projective left-looking extract (PRA-322 / hengck23 e002)."""
    from exp.decoder.common import inv
    from exp.noscratch.kernels import mul24_xor_noscratch
    h=len(words)//2;groups=constants(h)[4]
    word_to_gi={g['word']:i for i,g in enumerate(groups)}
    head_to_gi={}
    for i,g in enumerate(groups):
        head_to_gi[g['head']]=i
        if g['double']:head_to_gi[g['head']+1]=i
    history=[]if not reverse else list(transcript)
    w_live={}

    def park_W(j,W):
        w_live[j]=W

    def take_W(j,v_slots):
        if j in w_live:return w_live.pop(j)
        W=b.alloc_qubits(24);b.cx(v_slots,W);b.cx(W,v_slots);b.x(v_slots[0]);return W

    def materialize_fwd(j):
        if j not in w_live:return
        u=combine(words[j:j+2]);v=combine(words[j+2:j+4])
        W=take_W(j,v)
        # Keep N on W and Di on out for reverse (inv(N) clear fails at N=0).
        b.swap(u,v);b.swap(v,W)
        tok=jet_forward(b,u,v,K)
        out=b.alloc_qubits(24);mul24_xor_noscratch(b,W,u,out,K)
        b.swap(u,out)
        history.append(('mat',j,tok,W,out))

    def materialize_rev(j,tok,N,Di):
        u=combine(words[j:j+2]);v=combine(words[j+2:j+4])
        b.swap(u,Di)
        mul24_xor_noscratch(b,u,N,Di,K);b.free(Di)
        jet_reverse(b,u,v,tok,K)
        b.swap(v,N);b.swap(u,v);park_W(j,N)

    def proj_fwd(j,head,c,q):
        u=combine(words[j:j+2]);d=combine(words[j+2:j+4])
        a,z=words[2*head:2*head+2]
        W=take_W(j,d)
        eh=b.alloc_qubits(24);_ehead_xor(b,a,z,c,eh)
        mul24_xor_noscratch(b,eh,d,u,K);_ehead_xor(b,a,z,c,eh);b.free(eh)
        _square24_ext_inplace(b,d)
        _mul_low12_into24(b,d,z,W)
        _square24_ext_inplace(b,d,undo=True)
        _nz_swap24(b,u,d)
        scalepair(b,W,q)
        mul24_xor_noscratch(b,u,d,W,K)
        scalepair(b,u,q)
        park_W(j,W);history.append(('proj',head,c,q,j))

    def proj_rev(j,head,c,q):
        u=combine(words[j:j+2]);d=combine(words[j+2:j+4])
        a,z=words[2*head:2*head+2]
        W=take_W(j,d)
        scalepair(b,u,inv(q))
        mul24_xor_noscratch(b,u,d,W,K)
        scalepair(b,W,inv(q))
        _nz_swap24(b,u,d)
        _square24_ext_inplace(b,d)
        _mul_low12_into24(b,d,z,W)
        _square24_ext_inplace(b,d,undo=True)
        eh=b.alloc_qubits(24);_ehead_xor(b,a,z,c,eh)
        mul24_xor_noscratch(b,eh,d,u,K);_ehead_xor(b,a,z,c,eh);b.free(eh)
        park_W(j,W)

    if not reverse:
        for op in plan(h):
            if op['kind']=='coordinates':
                g=groups[head_to_gi[op['head']]]
                if g['word'] in w_live:materialize_fwd(g['word'])
                cx(b,words[2*op['head']+1],words[2*op['head']],op['c']);continue
            if op['kind']=='local':
                i=2*op['head'];j=i+2;x=combine(words[j:j+2])
                b.cx(words[i+1],words[j]);history.append(('local',inverse_forward(b,x,K)))
                cx(b,words[j+1],words[j],op['c']);continue
            j=op['target'];u=combine(words[j:j+2]);d=combine(words[j+2:j+4]);q=op['q']
            if word_to_gi[j]<projective_thresh:
                translate(b,words,op['head'],j,op['c']);history.append(('jet',jet_forward(b,u,d,K)))
                scalepair(b,d,q);b.cx(u,d);scalepair(b,u,q)
            else:
                proj_fwd(j,op['head'],op['c'],q)
        for j in list(w_live):materialize_fwd(j)
        return history

    while history and history[-1][0]=='mat':
        kind,j,tok,N,Di=history.pop();assert kind=='mat'
        materialize_rev(j,tok,N,Di)
    for op in reversed(plan(h)):
        if op['kind']=='coordinates':
            cx(b,words[2*op['head']+1],words[2*op['head']],op['c'])
            g=groups[head_to_gi[op['head']]]
            if history and history[-1][0]=='mat' and history[-1][1]==g['word']:
                kind,jw,tok,N,Di=history.pop();assert kind=='mat' and jw==g['word']
                materialize_rev(jw,tok,N,Di)
            continue
        if op['kind']=='local':
            i=2*op['head'];j=i+2;x=combine(words[j:j+2])
            cx(b,words[j+1],words[j],op['c']);kind,t=history.pop();assert kind=='local'
            inverse_reverse(b,x,t,K);b.cx(words[i+1],words[j]);continue
        j=op['target'];u=combine(words[j:j+2]);d=combine(words[j+2:j+4]);q=op['q']
        if word_to_gi[j]<projective_thresh:
            scalepair(b,u,inv(q));b.cx(u,d);scalepair(b,d,inv(q))
            kind,t=history.pop();assert kind=='jet';jet_reverse(b,u,d,t,K)
            translate(b,words,op['head'],j,op['c'])
        else:
            kind,head,c,q2,j2=history.pop();assert kind=='proj' and j2==j and q2==q
            proj_rev(j,head,c,q)
    assert not history
    for j in list(w_live):
        W=w_live.pop(j)
        v=combine(words[j+2:j+4]);b.x(v[0]);b.cx(W,v);b.cx(v,W);b.free(W)
    return history
'''


def apply(tree: Path) -> dict:
    path = tree / RELPATH
    text = path.read_text()
    if MARKER not in text:
        raise SystemExit(f'e002: marker not found in {path}')
    start = text.index(MARKER)
    path.write_text(text[:start] + REPLACEMENT)
    return {
        'edit': 'e002',
        'file': str(RELPATH),
        'hengck_iter': '004',
        'expected_dT': -15259,
        'expected_dQ': 12,
        'status': 'applied',
    }
