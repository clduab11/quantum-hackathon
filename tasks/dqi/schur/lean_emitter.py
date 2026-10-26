# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Build two independent affine parities inside their operand registers.

Only the product fanout needs a clean emitter qubit. Every parity basis
change is undone after the controlled operation, including overlapping sets.
"""
from .extension_inverse import setup


class LeanEm(setup()[0].Em):
 def pivot_pair(self,wa,ca,wb,cb,mid):
  wa=set(wa);wb=set(wb);assert wa and wb and wa!=wb,(wa,wb)
  p=min(wa);first=sorted(wa-{p})
  for q in first:self.b.cx(q,p)
  if p in wb:wb.symmetric_difference_update(wa-{p})
  choices=wb-{p};assert choices,(wa,wb)
  q=min(choices);second=sorted(wb-{q})
  for r in second:self.b.cx(r,q)
  if ca:self.b.x(p)
  if cb:self.b.x(q)
  mid(p,q)
  if cb:self.b.x(q)
  if ca:self.b.x(p)
  for r in reversed(second):self.b.cx(r,q)
  for r in reversed(first):self.b.cx(r,p)


def create(m,ab):
 sc=ab.qubits(1);return sc,LeanEm(ab,sc[0],sc[0],sc[0],m.Alloc(ab))
