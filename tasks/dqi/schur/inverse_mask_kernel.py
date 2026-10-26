# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Root-gated parity of a field inverse against a runtime classical mask.

A candidate primitive for a Wronskian-based DQI scan. This does not by itself
replace the decoder: the reversible in-place Wronskian transform is unfinished.
"""
import json
import kickmix as km
from .tower_inverse import tower,apply_map,product,linear_xor
from .recursive_forney import inverse_dot_data,trans_ops
from .transposed_forney import multiplication_terms
from .crt_multiplier import indices


def classical_transpose(b,x,u,target):
    flag=b.alloc_bits(1)[0]
    for lm,rm,om in multiplication_terms(len(x)):
        xx=list(indices(lm));lead=x[xx[0]];other=km.array([x[j] for j in xx[1:]])
        cm=km.array([u[j] for j in indices(om)]);dst=km.array([target[j] for j in indices(rm)])
        b.cx(other,lead);b.cx(cm,flag);b.push_condition(flag);b.cx(lead,dst);b.pop_condition();b.cx(cm,flag);b.cx(other,lead)
    b.free(km.array([flag]))


def phase_inverse(b,source,mask):
    """Ungated mask dot inverse(source), preserving source and classical mask."""
    info=tower(12);apply_map(b,source,info['ops'],True);apply_map(b,mask,trans_ops(12))
    a,c=source[:6],source[6:];norm=b.alloc_qubits(6);v=b.alloc_qubits(6)
    product(b,a,c,norm);linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    def vmap():
        b.cx(c,a);classical_transpose(b,a,mask[:6],v);b.cx(c,a)
        classical_transpose(b,c,mask[6:],v)
    vmap();leaf,iv,cleanup=inverse_dot_data(b,norm,v);b.cz(leaf,iv);cleanup()
    vmap();b.free(v)
    linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    b.del_gf2_mul(a,c,target=norm,field=km.GF2Field(6));b.free(norm)
    apply_map(b,mask,trans_ops(12),True);apply_map(b,source,info['ops'])


def apply(b,root,source,mask):
    info=tower(12);apply_map(b,source,info['ops'],True);apply_map(b,mask,trans_ops(12))
    a,c=source[:6],source[6:];norm=b.alloc_qubits(6);v=b.alloc_qubits(6)
    product(b,a,c,norm);linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    def vmap():
        b.cx(c,a);classical_transpose(b,a,mask[:6],v);b.cx(c,a)
        classical_transpose(b,c,mask[6:],v)
    vmap();leaf,inv,cleanup=inverse_dot_data(b,norm,v)
    parity=b.alloc_qubits(1)[0];ladder=b.alloc_qubits(10);meas=b.alloc_bits(1)[0]
    for j in range(3):b.ccx(leaf[j],inv[j],parity)
    b.x(root);b.init_and(root[0],root[1],ladder[0])
    for j in range(1,10):b.init_and(ladder[j-1],root[j+1],ladder[j])
    b.ccz(ladder[-1],root[-1],parity)
    for j in reversed(range(1,10)):b.del_and(ladder[j-1],root[j+1],ladder[j])
    b.del_and(root[0],root[1],ladder[0]);b.x(root)
    b.hmr(parity,meas);b.push_condition(meas);b.cz(leaf,inv);b.pop_condition();cleanup()
    vmap();b.free(v)
    linear_xor(b,a,norm,info['square']);linear_xor(b,c,norm,info['musquare'])
    b.del_gf2_mul(a,c,target=norm,field=km.GF2Field(6));b.free(norm)
    apply_map(b,mask,trans_ops(12),True);apply_map(b,source,info['ops'])
    b.bit_store(meas,False);b.free(km.array([meas]));b.free(km.array([parity]));b.free(ladder)





