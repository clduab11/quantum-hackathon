# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Existing 66-AND inverse creation with 31-AND cubic mask repayment."""
from contextlib import contextmanager
import kickmix as km
from .low_workspace_inverse import norm_rt,inverse_output_rt
from .cubic_mask_phase_compact import native_phase_inverse


def bind(m):
 @contextmanager
 def inv_word(E,src):
  names=[('cubic_low_N',6),('cubic_low_M',3),('cubic_low_S',3),('cubic_low_Y',6)];wins=[E.A.open(name,n) for name,n in names];n,mm,s,y=wins;rN,rM,rS=m.norm_chain_terms(src,m.spec_rows(m.A0ROWS,src),m.spec_rows(m.A1ROWS,src),n,mm,s);rY=m.chain_rts(src,wins,src)[-2];E.macs([rN,rM,rS,rY]);E.frees([rN,rM,rS])
  for (name,_),word in reversed(list(zip(names[:3],wins[:3]))):E.A.close(name,word)
  out=E.A.open('cubic_low_out',12);E.mac(inverse_output_rt(m,src,y,out));E.free(norm_rt(m,out,y));E.A.close(names[3][0],y)
  yield out
  b=E.b.raw;mask=b.alloc_bits(12);b.hmr(km.array([km.q(q) for q in out]),mask);E.A.close('cubic_low_out',out);native_phase_inverse(b,src,mask);b.bit_store(mask,False);b.free(mask)
 return inv_word


