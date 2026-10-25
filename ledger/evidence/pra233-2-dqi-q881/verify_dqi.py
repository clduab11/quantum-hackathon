import json,time
import kickmix as km
from dqi.verify_submission_dqi import verify,ProblemSpecDQI
start=time.monotonic()
c=km.Circuit.from_file('/tmp/pra236-build/dqi.kmb',format='kmb')
r=verify(c,ProblemSpecDQI.benchmark_instance(),salt='PRA171_LOCAL_PUBLIC_FIXED_SALT_0001',seed=None,max_workers=1)
r['wall_seconds']=time.monotonic()-start
print(json.dumps(r,indent=2))
