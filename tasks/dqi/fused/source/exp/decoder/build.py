"""Build the integrated decoder with isolated degree-two-gap lookahead."""
import argparse,json,time,hashlib,gc
from common import *
from exp.confluent_extract.kernel import initial,extract as extract_jets
from exp.confluent_extract.model import constants as confluent_constants
from exp.jet24.kernel import jet_forward,jet_reverse

def extract(b,words,reverse=False,transcript=None):
    return extract_jets(b,words,jet_forward,jet_reverse,reverse,transcript)
from exp.fold_cached_norm.kernel import synthesize,unsynthesize
from exp.mask_projection.kernel import project,restore,SELECTED
sys.path.insert(0,str(ROOT/'exp/convert'))
from convert import convert
from exp.convert_short_hankel.phase34 import convert_safe as convert_historyfree
sys.path.insert(0,str(ROOT/'exp/scan'))
from scan import scan

def build(path):
    start=time.time();b=km.CircuitBuilder();S=[b.alloc_qubits(12) for i in range(70)]
    E=[b.alloc_bits(12) for j in range(4095)]
    stages=[];oldT=0
    def snapshot(name):
        nonlocal oldT
        c=b.finish_circuit();T=c.operation_statistics().num_toffoli_like
        r=dict(name=name,T=T-oldT,cumulative_T=T,Q=c.num_qubits,num_ops=len(c),seconds=time.time()-start)
        stages.append(r);oldT=T;print(json.dumps(r),flush=True);del c;gc.collect()
    with b.mark('mask_projection'):mask_token=project(b,S,E)
    snapshot('mask_projection')
    with b.mark('initial'):initial(b,S)
    snapshot('initial')
    with b.mark('extract'):xh=extract(b,S)
    snapshot('extract')
    with b.mark('synthesis'):A,B,yh=synthesize(b,S)
    snapshot('synthesis')
    history_word=b.alloc_qubits(12)
    with b.mark('convert_lookahead'):phase_token=convert_historyfree(b,A,B,history_scratch12=history_word,monic_root=True)
    snapshot('convert_lookahead')
    with b.mark('scan'):scan(b,A,B,E,skip_points=SELECTED,node_polynomial=confluent_constants()[2])
    snapshot('scan')
    with b.mark('unconvert_lookahead'):convert_historyfree(b,A,B,True,history_scratch12=history_word,phase_token=phase_token)
    b.free(history_word)
    snapshot('unconvert_lookahead')
    with b.mark('unsynthesis'):unsynthesize(b,yh)
    snapshot('unsynthesis')
    with b.mark('unextract'):extract(b,S,True,xh)
    snapshot('unextract')
    with b.mark('uninitial'):initial(b,S,True)
    snapshot('uninitial')
    with b.mark('restore_masks'):restore(b,E,mask_token)
    snapshot('restore_masks')
    # Named builder registers cannot be temporarily freed. Attach the exact
    # contract metadata after construction, retaining the original wire IDs.
    metadata=[]
    for i in range(70):
        metadata.append(f'REGISTER r{i} "S{i}"')
        metadata.extend(f'APPEND_TO_REGISTER q{12*i+k} r{i}' for k in range(12))
    for j in range(4095):
        metadata.append(f'REGISTER r{70+j} "E{j}"')
        metadata.extend(f'APPEND_TO_REGISTER b{12*j+k} r{70+j}' for k in range(12))
    c=km.Circuit('\n'.join(metadata))+b.finish_circuit();c.to_file(str(path),format='kmb')
    digest=hashlib.file_digest(open(path,'rb'),'sha256').hexdigest()
    result=dict(path=str(path),sha256=digest,T_static=c.operation_statistics().num_toffoli_like,Q=c.num_qubits,num_ops=len(c),num_bits=c.num_bits,stages=stages,seconds=time.time()-start,scope='STATIC compiled counts include mutually exclusive classical branches; confluent Hermite extraction, zero-power retained-norm synthesis, short-Hankel monic-root guarded h2 conversion, classical mask projection; no verifier cost claimed')
    path.with_suffix('.build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();build(args.output)
