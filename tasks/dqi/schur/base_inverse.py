# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""112-Toffoli in-place GF(4096) inverse, native polynomial coordinates."""
import kickmix as km
from .extension_inverse import Adapter,init_inverse12,setup
from .inverse_mask_kernel import phase_inverse
from .tower_inverse import map_ops,apply_map

def inplace(b,src):
 m,k,fw,bk,tr=setup();ab=Adapter(b);qq=ab.qubits(3);E=m.Em(ab,*qq,m.Alloc(ab));out=ab.qubits(12)
 init_inverse12(m,E,[q.id for q in src],out);oo=km.array([km.q(i) for i in out]);mask=b.alloc_bits(12);b.hmr(src,mask)
 apply_map(b,oo,map_ops(bk));trans=tuple(sum(((fw[i]>>j)&1)<<i for i in range(12)) for j in range(12));ops=map_ops(trans);apply_map(b,mask,ops)
 phase_inverse(b,oo,mask);apply_map(b,mask,ops,True);apply_map(b,oo,map_ops(bk),True)
 for x,y in zip(src,oo):b.swap(x,y)
 ab.release_recycle('base_inverse_output',out);ab.release_recycle('base_inverse_emitter',qq)
 b.bit_store(mask,False);b.free(mask)

def build():
 from .fast_dqi import FastBuilder
 b=FastBuilder(km.CircuitBuilder());src=b.create_quantum_register(12,'x');inplace(b,src)
 c=b.finish_circuit();return km.Circuit(str(c)+'\n'+''.join(f'BIT_STORE0 b{i}\n' for i in range(c.num_bits)))
