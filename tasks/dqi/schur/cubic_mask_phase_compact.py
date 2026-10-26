# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Trace-inverse phase with the GF16 inverse outputs fused into CZ gates."""
from contextlib import contextmanager
import inspect
import kickmix as km
from . import cubic_mask_phase_joint as joint
from .cubic_trace_field import inverse_network


@contextmanager
def inverse4(b,source):
 net=inverse_network();A,B=b.alloc_qubits(2);live={}
 def lin(s,target):
  if s.const:b.x(target)
  for j in s.terms:b.cx(source[j] if j<4 else live[j],target)
 for j,(a,c) in enumerate(net.nodes):
  q=b.alloc_qubits(1)[0];lin(a,A);lin(c,B);b.init_and(A,B,q);lin(c,B);lin(a,A);live[4+j]=q
 yield [(s.const,[source[j] if j<4 else live[j] for j in s.terms]) for s in net.outputs]
 for j in reversed(range(len(net.nodes))):
  a,c=net.nodes[j];lin(a,A);lin(c,B);q=live.pop(4+j);b.del_and(A,B,q);lin(c,B);lin(a,A);b.free(km.array([q]))
 b.free(km.array([A,B]))


def phase_pair(b,word,signals):
 for q,(const,terms) in zip(word,signals):
  if const:b.z(q)
  for r in terms:b.cz(q,r)

ns=dict(joint.ns);ns.update(vars(joint));ns.update(inverse4=inverse4,phase_pair=phase_pair)
exec(joint.s.replace(joint.old,joint.new).replace('b.cz(Q,iv)','phase_pair(b,Q,iv)'),ns)
exec(inspect.getsource(joint.phase_inverse),ns);phase_inverse=ns['phase_inverse']
exec(inspect.getsource(joint.native_phase_inverse),ns);native_phase_inverse=ns['native_phase_inverse']
