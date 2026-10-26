# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
import kickmix as km

def isomorphism(pub):
    native=km.GF2Field(12)
    def peval(x):
        v=0
        for i in reversed(range(13)):v=native.mul(v,x)^((pub.POLY>>i)&1)
        return v
    logs={native.pow(2,k):k for k in range(4095)}
    beta=next(x for x in range(2,4096) if peval(x)==0)
    k=logs[beta];r=pow(k,-1,4095)
    forward=[pub.gpow(pub.EXP[r],i) for i in range(12)]
    back=[native.pow(beta,i) for i in range(12)]
    def transform(v,cols):
        z=0
        for i in range(12):
            if v>>i&1:z^=cols[i]
        return z
    for a in range(4096):assert transform(transform(a,forward),back)==a
    return forward,back,transform

