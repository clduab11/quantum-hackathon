# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Tower inversion with early intermediate erasure and delayed phase repair.

Y=Norm(x)^-1 also equals Norm(x^-1), so its cleanup can use the output instead
of retaining the norm chain. On final erasure measure the inverse output first,
reuse its clean wires for the norm chain, then repay its measurement phase.
The term formulas and arithmetic counts match the attributed upstream helper.
"""
from contextlib import contextmanager


def norm_rt(m,source,target):
    rt=[];m.bil_terms(rt,m.KT6,m.spec_rows(m.A0ROWS,source),m.spec_rows(m.A1ROWS,source),target)
    m.lin_rows_terms(rt,m.LNROWS,source,target);return rt


def inverse_output_rt(m,source,y,out):
    rt=[];m.kt6_terms_poly(rt,m.spec_rows(m.A01ROWS,source),m.spec_plain(y),out,0)
    m.kt6_terms_poly(rt,m.spec_rows(m.A1ROWS,source),m.spec_plain(y),out,6);return rt


def repay(E,rt,outcomes):
    for term in rt:
        if term[0]=='L':
            for target in term[-1]:
                measurement=outcomes[target]
                for w in term[1]:E.b.z(w,cond=measurement)
                if term[2]:E.b.neg(cond=measurement)
        else:
            _,wa,ca,wb,cb,targets=term
            for target in targets:
                E.pivot_pair(wa,ca,wb,cb,lambda a,b,t=target:E.b.cz(a,b,cond=outcomes[t]))


def bind(m):
    @contextmanager
    def inv_word(E,src):
        assert not E.J.recording,'This standalone research helper does not journal allocator reuse.'
        names=[('low_inv_N',6),('low_inv_M',3),('low_inv_S',3),('low_inv_Y',6)]
        wins=[E.A.open(name,n) for name,n in names]
        n,mm,s,y=wins
        rN,rM,rS=m.norm_chain_terms(src,m.spec_rows(m.A0ROWS,src),m.spec_rows(m.A1ROWS,src),n,mm,s)
        rY=m.chain_rts(src,wins,src)[-2]
        E.macs([rN,rM,rS,rY]);E.frees([rN,rM,rS])
        for (name,_),word in reversed(list(zip(names[:3],wins[:3]))):E.A.close(name,word)
        out=E.A.open('low_inv_out',12);E.mac(inverse_output_rt(m,src,y,out))
        E.free(norm_rt(m,out,y));E.A.close(names[3][0],y)
        yield out
        outcomes={q:E.b.hmr(q) for q in out};E.A.close('low_inv_out',out)
        wins=[E.A.open(name,n) for name,n in names]
        rts=m.chain_rts(src,wins,out);E.macs(rts[:-1]);repay(E,rts[-1],outcomes);E.frees(rts[:-1])
        for (name,_),word in reversed(list(zip(names,wins))):E.A.close(name,word)
    return inv_word
