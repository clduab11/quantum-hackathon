# SPDX-License-Identifier: Apache-2.0
"""Edit 002: projective left-looking extract for targets in groups >= 5.

hengck23 iter 004 (discussion 753607): ΔT −15,259, ΔQ +12 (889→901),
jets 289→16, 0 failures.

Classical oracle: ledger/evidence/pra322-hengck23/projective_classical.py.

Cost model: D² is the GF(2) Frobenius (linear), not a full GF24 mul.
W is HMR-parked around the N≠0 ladder so peak Q stays near baseline+12.
Materialize keeps a classical Di snapshot so reverse skips inverse24.
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

def _load_bits(b,bits,reg):
    for i,bit in enumerate(bits):
        b.push_condition(bit);b.x(reg[i]);b.pop_condition()

def _cswap24(b,ctrl,x,y):
    for i in range(24):b.cswap(ctrl,x[i],y[i])

def _square24_ext_inplace(b,x,undo=False):
    """x := x² (or Frobenius inverse) in a+b*y coordinates; CNOT only."""
    from exp.arithmetic.field import extension_columns, square_columns, linear_inplace, inverse_columns
    cols,frm,_=extension_columns(K)
    sq=square_columns(24)
    linear_inplace(b,x,cols)
    linear_inplace(b,x,inverse_columns(sq)if undo else sq)
    linear_inplace(b,x,frm)

def _mul_low12_into24(b,x24,z12,out24):
    """out ^= (x24)*(z12+0*y) via two GF12 muls (no 24-qubit z pad)."""
    from exp.noscratch.kernels import mul_xor_noscratch
    mul_xor_noscratch(b,x24[:12],z12,out24[:12])
    mul_xor_noscratch(b,x24[12:],z12,out24[12:])

def _emul24_bits_xor(b,xbits,ybits,z24):
    """z ^= emul(x,y) with x,y classical bits; zero ancilla (conditioned X only)."""
    from exp.arithmetic.field import bits
    from exp.decoder.common import emul
    for i in range(24):
        for j in range(24):
            for k in bits(emul(1<<i,1<<j)):
                b.push_condition(xbits[i]);b.push_condition(ybits[j]);b.x(z24[k]);b.pop_condition();b.pop_condition()

def extract(b,words,jet_forward,jet_reverse,reverse=False,transcript=None,
            inverse_forward=inverse24_forward190,inverse_reverse=inverse24_reverse209,
            projective_thresh=5):
    """Projective left-looking extract (PRA-322 / hengck23 e002)."""
    from exp.decoder.common import inv,zero_hold,zero_free
    from exp.noscratch.kernels import mul24_xor_noscratch
    h=len(words)//2;groups=constants(h)[4]
    word_to_gi={g['word']:i for i,g in enumerate(groups)}
    head_to_gi={}
    for i,g in enumerate(groups):
        head_to_gi[g['head']]=i
        if g['double']:head_to_gi[g['head']+1]=i
    history=[]if not reverse else list(transcript)
    w_park={}
    parity=b.alloc_qubits(12)

    def park_W(j,W):
        bits=b.alloc_bits(24);b.hmr(W,bits);b.free(W);w_park[j]=bits

    def take_W(j,v_slots):
        if j in w_park:
            W=b.alloc_qubits(24);_load_bits(b,w_park.pop(j),W);return W
        W=b.alloc_qubits(24);b.cx(v_slots,W);b.cx(W,v_slots);b.x(v_slots[0]);return W

    def materialize_fwd(j):
        if j not in w_park:return
        u=combine(words[j:j+2]);v=combine(words[j+2:j+4])
        W=take_W(j,v)
        Nscratch=b.alloc_qubits(24);b.cx(u,Nscratch)
        Nbits=b.alloc_bits(24);b.hmr(Nscratch,Nbits);b.free(Nscratch)
        b.swap(u,v);b.swap(v,W);b.free(W)
        tok=jet_forward(b,u,v,K)
        # HMR clears its target; copy Di so u stays inv(D) for the N·Di mul
        Ditmp=b.alloc_qubits(24);b.cx(u,Ditmp)
        Dibits=b.alloc_bits(24);b.hmr(Ditmp,Dibits);b.free(Ditmp)
        N=b.alloc_qubits(24);_load_bits(b,Nbits,N)
        out=b.alloc_qubits(24);mul24_xor_noscratch(b,N,u,out,K)
        b.swap(u,out);b.free(out);b.free(N)
        history.append(('mat',j,tok,Nbits,Dibits))

    def materialize_rev(j,tok,Nbits,Dibits):
        u=combine(words[j:j+2]);v=combine(words[j+2:j+4])
        # u = N·Di; clear with classical-bit product (0 ancilla), restore Di
        _emul24_bits_xor(b,Nbits,Dibits,u)
        Di=b.alloc_qubits(24);_load_bits(b,Dibits,Di);b.free(Dibits)
        b.cx(Di,u);b.free(Di)
        jet_reverse(b,u,v,tok,K)
        # u=D, v=W → park W, then u=N, v=D
        W=b.alloc_qubits(24);b.cx(v,W);b.cx(W,v);park_W(j,W)
        b.swap(u,v)
        N=b.alloc_qubits(24);_load_bits(b,Nbits,N);b.free(Nbits)
        b.cx(N,u);b.free(N)

    def proj_fwd(j,head,c,q):
        u=combine(words[j:j+2]);d=combine(words[j+2:j+4])
        a,z=words[2*head:2*head+2]
        eh=b.alloc_qubits(24);_ehead_xor(b,a,z,c,eh)
        mul24_xor_noscratch(b,eh,d,u,K);b.free(eh)
        W=take_W(j,d)
        _square24_ext_inplace(b,d)
        _mul_low12_into24(b,d,z,W)
        _square24_ext_inplace(b,d,undo=True)
        park_W(j,W)
        lad=zero_hold(b,u);b.x(lad[-1]);b.cx(lad[-1],parity[0])
        _cswap24(b,parity[0],u,d)
        b.cx(lad[-1],parity[0]);b.x(lad[-1]);zero_free(b,u,lad)
        W=take_W(j,d)
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
        park_W(j,W)
        lad=zero_hold(b,u);b.x(lad[-1]);b.cx(lad[-1],parity[0])
        _cswap24(b,parity[0],u,d)
        b.cx(lad[-1],parity[0]);b.x(lad[-1]);zero_free(b,u,lad)
        W=take_W(j,d)
        _square24_ext_inplace(b,d)
        _mul_low12_into24(b,d,z,W)
        _square24_ext_inplace(b,d,undo=True)
        park_W(j,W)
        eh=b.alloc_qubits(24);_ehead_xor(b,a,z,c,eh)
        mul24_xor_noscratch(b,eh,d,u,K);b.free(eh)

    if not reverse:
        for op in plan(h):
            if op['kind']=='coordinates':
                g=groups[head_to_gi[op['head']]]
                if g['word'] in w_park:materialize_fwd(g['word'])
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
        for j in list(w_park):materialize_fwd(j)
        b.free(parity);return history

    while history and history[-1][0]=='mat':
        kind,j,tok,Nbits,Dibits=history.pop();assert kind=='mat'
        materialize_rev(j,tok,Nbits,Dibits)
    for op in reversed(plan(h)):
        if op['kind']=='coordinates':
            cx(b,words[2*op['head']+1],words[2*op['head']],op['c'])
            g=groups[head_to_gi[op['head']]]
            if history and history[-1][0]=='mat' and history[-1][1]==g['word']:
                kind,jw,tok,Nbits,Dibits=history.pop();assert kind=='mat' and jw==g['word']
                materialize_rev(jw,tok,Nbits,Dibits)
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
    for j in list(w_park):
        bits=w_park.pop(j);W=b.alloc_qubits(24);_load_bits(b,bits,W);b.free(bits)
        v=combine(words[j+2:j+4]);b.x(v[0]);b.cx(W,v);b.free(W)
    b.free(parity);return history
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
