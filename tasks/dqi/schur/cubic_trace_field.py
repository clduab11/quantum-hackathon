# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""GF(4096)/GF(16) Kummer coordinates and small exact Boolean components.

The five-product inversion core is the inner Boyar-Peralta AES inversion
construction; free input/output maps are independently found and exhaustively
checked here. Background: NIST circuit-complexity project and Boyar, Find,
Peralta, Small Low-Depth Circuits for Cryptographic Applications (2018).
"""
from functools import lru_cache
import itertools
import kickmix as km
from .boolean_lookup import Network,Signal
from .tower_inverse import map_ops


def linear(cols,x):
 out=0
 for j,c in enumerate(cols):
  if x>>j&1:out^=c
 return out


def inverse_columns(cols):
 ops=map_ops(cols);out=[]
 for j in range(len(cols)):
  v=1<<j
  for op,a,b in reversed(ops):
   if op=='cx':v^=((v>>a)&1)<<b
   elif ((v>>a)^(v>>b))&1:v^=(1<<a)|(1<<b)
  out.append(v)
 return tuple(out)


def trace(f,x):
 out=0
 for _ in range(f.degree):out^=x;x=f.mul(x,x)
 assert out in [0,1]
 return out


def inverse_network():
 net=Network(4);x=[Signal(frozenset([j])) for j in range(4)]
 def transform(cols,words):return [sum_signal([v for j,v in enumerate(words) if cols[j]>>i&1]) for i in range(len(words))]
 t21,t22,t23,t24=transform((1,8,11,15),x)
 t25=t21^t22;t26=net.mul(t21,t23);t27=t24^t26;t28=net.mul(t25,t27);t29=t28^t22;t30=t23^t24;t31=t22^t26;t32=net.mul(t31,t30);t33=t32^t24;t34=t23^t33;t35=t27^t33;t36=net.mul(t24,t35);t37=t36^t34;t38=t27^t36;t39=net.mul(t29,t38);t40=t25^t39
 net.outputs=transform(inverse_columns((8,10,3,14)),[t29,t33,t37,t40]);assert len(net.nodes)==5
 return net


def sum_signal(words):
 out=Signal(frozenset())
 for w in words:out=out^w
 return out


def rank(rows):
 basis={}
 for v in rows:
  while v:
   j=v.bit_length()-1
   if j in basis:v^=basis[j]
   else:basis[j]=v;break
 return len(basis)


@lru_cache(None)
def cube_terms():
 f=km.GF2Field(4);values=[f.pow(x,3) for x in range(16)];anf=values.copy()
 for j in range(4):
  for x in range(16):
   if x>>j&1:anf[x]^=anf[x^(1<<j)]
 pairs=[m for m in range(16) if m.bit_count()==2];rows=[sum(((anf[m]>>j)&1)<<i for i,m in enumerate(pairs)) for j in range(4)];span={0}
 for row in rows:span|={v^row for v in list(span)}
 selected=[]
 for a in range(1,16):
  for b in range(1,a):
   q=0
   for i,mask in enumerate(pairs):
    u,v=[j for j in range(4) if mask>>j&1];q|=((((a>>u)&1)&((b>>v)&1))^(((a>>v)&1)&((b>>u)&1)))<<i
   if q in span and rank([p[2] for p in selected]+[q])>len(selected):selected.append((a,b,q))
   if len(selected)==4:break
  if len(selected)==4:break
 terms=[];linearcols=[anf[1<<i] for i in range(4)]
 for j,(a,b,q) in enumerate(selected):
  out=0
  for bit,row in enumerate(rows):
   coeff=next(c for c in range(16) if xor_values(selected[i][2] for i in range(4) if c>>i&1)==row)
   out|=((coeff>>j)&1)<<bit
  terms.append((a,b,out))
  for bit in range(4):
   if (a&b)>>bit&1:linearcols[bit]^=out
 assert all(linear(linearcols,x)^xor_values(o for a,b,o in terms if (a&x).bit_count()%2 and (b&x).bit_count()%2)==values[x] for x in range(16))
 return tuple(terms),tuple(linearcols),tuple(anf)


def xor_values(values):
 out=0
 for v in values:out^=v
 return out


@lru_cache(None)
def data():
 f=km.GF2Field(12);g=km.GF2Field(4)
 def eval_poly(p,x):
  out=0
  for j in reversed(range(p.bit_length())):out=f.mul(out,x)^((p>>j)&1)
  return out
 root=next(x for x in range(2,4096) if eval_poly(g.modulus,x)==0);emb=[f.pow(root,i) for i in range(4)];kappa=next(x for x in range(2,16) if g.pow(x,5)!=1);ek=linear(emb,kappa);t=next(x for x in range(4096) if f.pow(x,3)==ek);cols=tuple(f.mul(f.pow(t,i),c) for i in range(3) for c in emb);back=inverse_columns(cols)
 tr12=tuple(sum(trace(f,f.mul(1<<i,1<<j))<<j for j in range(12)) for i in range(12));tr4=tuple(sum(trace(g,g.mul(1<<i,1<<j))<<j for j in range(4)) for i in range(4))
 net=inverse_network();assert net.values()==[g.pow(x,14) for x in range(16)]
 return dict(kappa=kappa,columns=cols,inverse_columns=back,dual_columns=inverse_columns(tr12),trace4_columns=tr4)


