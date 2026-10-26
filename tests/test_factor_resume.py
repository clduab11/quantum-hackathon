"""A completed continuous stage can resume; altered or partial evidence cannot."""
import json
from pathlib import Path
import numpy as np
import pytest
from tasks.dfthcsos.factor_support import sha256, write_npz
from tasks.dfthcsos.gpu_fit.geometry import columns, physical_error
from tasks.dfthcsos.factor_resume import load_continuous, ORIGINAL_DRIVER_SHA


def fixture(tmp_path):
    rng=np.random.default_rng(5);u=rng.normal(size=(1,3,4));u/=np.linalg.norm(u,axis=-1,keepdims=True)
    w=rng.normal(size=(1,3,2))*.1;x=columns(u,w);target=x@x.T+np.eye(10)*.006
    error=physical_error(u,w,target)
    factor=tmp_path/'factor.npz';write_npz(factor,{'U':u,'W':w})
    report={'input_sha256':'input-pin','source_hashes':{'factor_fit_v4.py':ORIGINAL_DRIVER_SHA,'gpu_fit/math.py':'math-pin'},
        'optimizer_seed':95101,'stages':[{'stage':'structural','limit_steps':8000,'limit_seconds':700,'elapsed':701,'stop':'source_time_limit','best_error':error},
        {'stage':'gauss-newton','limit_iterations':300,'limit_cg':100,'limit_seconds':450,'elapsed':451,'stop':'source_time_limit','best_error':error}],
        'rows':[{'label':'continuous-best','shape':[1,3,2],'seconds':1155,'detail':{'continuous_error':error}}]}
    rp=tmp_path/'progress.json';rp.write_text(json.dumps(report))
    manifest=tmp_path/'resume.json';manifest.write_text(json.dumps({'progress':{'path':str(rp),'sha256':sha256(rp)},'factor':{'path':str(factor),'sha256':sha256(factor)}}))
    return manifest,target,report


def load(path,target):
    return load_continuous(path,sha256(path),'input-pin',{'gpu_fit/math.py':'math-pin'},target)


def test_resumes_exact_continuous_arrays_and_preserves_completed_stage_records(tmp_path):
    path,target,report=fixture(tmp_path);p,proof=load(path,target)
    assert physical_error(p['U'],p['W'],target)==pytest.approx(report['stages'][-1]['best_error'])
    assert proof['stages']==report['stages'] and proof['prior_seconds']==1155
    assert proof['checkpoint_sha256']==sha256(tmp_path/'factor.npz')


@pytest.mark.parametrize('damage', ['manifest','report','factor','input','source','partial'])
def test_rejects_tampered_or_partial_resume(tmp_path,damage):
    path,target,report=fixture(tmp_path)
    if damage=='manifest':
        with pytest.raises(ValueError,match='hash'):load_continuous(path,'wrong','input-pin',{'gpu_fit/math.py':'math-pin'},target)
        return
    if damage=='report':(tmp_path/'progress.json').write_text('{}')
    if damage=='factor':(tmp_path/'factor.npz').write_bytes(b'altered')
    if damage in ('input','source','partial'):
        if damage=='input':report['input_sha256']='other'
        if damage=='source':report['source_hashes']['gpu_fit/math.py']='other'
        if damage=='partial':report['rows']=[]
        rp=tmp_path/'progress.json';rp.write_text(json.dumps(report));m=json.loads(path.read_text());m['progress']['sha256']=sha256(rp);path.write_text(json.dumps(m))
    with pytest.raises(ValueError):load(path,target)
