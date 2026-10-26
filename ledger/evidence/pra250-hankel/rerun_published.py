from pathlib import Path
from ledger.gates.runner import load_config,rerun_gate
from ledger.run_manifest import read_manifest
p=Path('ledger/manifests/candidates/pra250-hankel.json');m=read_manifest(p)
r=rerun_gate(m,'G5',Path('/home/cld-main/work/vqcc-data/queue/pra250-hankel.zip'),load_config(Path('configs/gates/pra250-hankel.yaml')),generator_commit='8e53362324fef5816baf58e699fa002a08596d7a',note='D-PRA250-03: repeat G5 against the published, tree-identical generator; original generator identity retained.',manifest_file=p,repo=Path.cwd(),package_root=Path('/home/cld-main/work/vqcc-data'))
print(r.gate,r.status,r.reason)
print('published_commit',r.details.get('rebuild',{}).get('commit'))
print('shipping_problems',m.shipping_problems())
assert r.status=='PASS'
