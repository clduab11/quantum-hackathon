# Port of jday96314/QuantumAI @ 2b9227095bf2c76f9f64a572645d7dce54998298.
# No repository licence; board ruling D-PRA269-01. See PROVENANCE.md.
"""Defer converter companion masks across the phase-only amplitude scan."""
from .derivative_inverse_deferred_compact import build as convert
from .schur_amplitude_scan import write_scan
from .schur_extract import body,mapped,BRE


def write_middle(f,N,M,private,nn,bb,scratch):
 n=N//2;rows=[];held=12*(n-1)
 def emit(c):
  ports={**{f'A{i}':w for i,w in enumerate(nn)},**{f'B{i}':w for i,w in enumerate(bb)}};qm={q.id:v for name,word in ports.items() for q,v in zip(c.register_data[name],word)};missing=[q for q in range(c.num_qubits) if q not in qm];available=[q for q in scratch if q not in qm.values()];assert len(missing)<=len(available);qm.update(dict(zip(missing,available)));f.write(BRE.sub(lambda x:f'b{private+int(x[1])}',mapped(body(c),qm)));rows.append(dict(Q=c.num_qubits,T=c.operation_statistics().num_toffoli_like))
 emit(convert(n));scan=write_scan(f,N,M,private+held, (nn,bb),scratch);emit(convert(n,True));return dict(components=rows,**scan,middle_T=sum(r['T'] for r in rows)+M*scan['kernel_T'])
