"""Count Toffoli-like builder calls that take a classical bit operand, by caller site."""
import sys,os,runpy,json,collections,tempfile,subprocess
if len(sys.argv)>1 and sys.argv[1]=='--inner':
    build=sys.argv[2];out=sys.argv[3]
    sys.path.insert(0,os.path.dirname(build))
    import kickmix as km
    counts=collections.Counter();Base=km.CircuitBuilder
    def wrap(name):
        orig=getattr(Base,name)
        def f(self,*a,**k):
            if any(isinstance(x,km.b) for x in a):
                fr=sys._getframe(1);counts[(name,fr.f_code.co_filename.split('source/')[-1],fr.f_code.co_name,fr.f_lineno)]+=1
            return orig(self,*a,**k)
        return f
    class CB(Base):
        pass
    for n in ('ccz','ccx','cswap'):setattr(CB,n,wrap(n))
    km.CircuitBuilder=CB
    sys.argv=[build,out]
    try:runpy.run_path(build,run_name='__main__')
    finally:
        json.dump([[*k,v] for k,v in counts.most_common()],open(out+'.bitctl.json','w'),indent=1)
else:
    sys.path.insert(0,'.')
    from pathlib import Path
    from tasks.dqi.generate_fused import stage_source
    scratch=Path(tempfile.mkdtemp(prefix='bitctl-'))
    stage_source(scratch,apply_hengck23=True)
    env=dict(os.environ,PYTHONPATH='/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation/kickmix')
    subprocess.run([sys.executable,'-B',os.path.abspath(__file__),'--inner',str(scratch/'source/exp/decoder/build.py'),str(scratch/'dqi.kmb')],cwd=scratch,env=env,check=True)
    print(scratch)
