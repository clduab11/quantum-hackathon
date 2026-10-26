# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""In-place quadratic inversion with a held norm measurement.

The two coordinates scale in place. The old norm, rather than the old
24-bit source, carries the sole pending X-measurement phase.
"""
import json
from pathlib import Path
import numpy as np
import kickmix as km
from .fast_dqi import FastBuilder
from .lean_emitter import create as lean_create
from .extension_inverse import Adapter,setup,extension_norm_rt,inverse_output_rt
from .low_workspace_inverse import norm_rt as norm12_rt
from .cubic_mask_phase_compact import phase_inverse
from .tower_inverse import apply_map,map_ops


def init_delayed(m,E,src):
 names=[('ext_inv_N6',6),('ext_inv_M3',3),('ext_inv_S3',3),('ext_inv_Y6',6)];wins=[E.A.open(name,n) for name,n in names];n,mm,s,y=wins
 rN,rM,rS=m.norm_chain_terms(src,m.spec_rows(m.A0ROWS,src),m.spec_rows(m.A1ROWS,src),n,mm,s);rY=m.chain_rts(src,wins,src)[-2];E.macs([rN,rM,rS,rY]);E.frees([rN,rM,rS])
 for (name,_),word in reversed(list(zip(names[:3],wins[:3]))):E.A.close(name,word)
 out=E.A.open('ext_delayed_inverse',12);E.mac(inverse_output_rt(m,src,y,out));E.free(norm12_rt(m,out,y));E.A.close(names[3][0],y);return out


def inverse_mask_native(b,source,mask,fw,bk):
 word=km.array([km.q(q) for q in source]);bops=map_ops(bk);trans=tuple(sum(((fw[i]>>j)&1)<<i for i in range(12)) for j in range(12));mops=map_ops(trans)
 apply_map(b,word,bops);apply_map(b,mask,mops);phase_inverse(b,word,mask);apply_map(b,mask,mops,True);apply_map(b,word,bops,True)


def build(reverse=False):
 m,k,fw,bk,tr=setup();b=FastBuilder(km.CircuitBuilder());x=b.create_quantum_register(24,'x');ghost=b.create_classical_register(24,'ghost');ab=Adapter(b);sc,E=lean_create(m,ab);src=[q.id for q in x]
 nn=E.A.open('extension_norm',12);E.mac(extension_norm_rt(m,src,nn,k));ni=init_delayed(m,E,nn)
 if reverse:
  for q,mask in zip(ni,ghost[:12]):ab.z(q,mask)
  b.bit_store(ghost,False)
 else:b.bit_store(ghost,False)
 b.cx(x[12:],x[:12])
 with m.opened(E,'extension_coordinate_scale',12) as temp:
  for word in [src[:12],src[12:]]:m.mon_slot(E,word,ni,nn,temp)
 if reverse:
  mask=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in nn]),mask);E.A.close('extension_norm',nn);inverse_mask_native(b,ni,mask,fw,bk);b.bit_store(mask,False);b.free(mask)
 else:
  b.hmr(km.array([km.q(q) for q in nn]),ghost[:12]);E.A.close('extension_norm',nn)
 E.free(extension_norm_rt(m,src,ni,k));E.A.close('ext_delayed_inverse',ni);ab.release_recycle('norm_inverse_emitter',sc);c=b.finish_circuit();held={v.id for v in ghost};return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits) if i not in held))


