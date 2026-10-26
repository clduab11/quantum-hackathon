import subprocess,json,datetime
from pathlib import Path
argv=['/home/cld-main/work/.paperclip-worktrees/quantum-hackathon/PRA-246-factor-fit-v4/.venv/bin/python', '-m', 'tasks.dfthcsos.factor_fit_v4', '--starter', '/home/cld-main/work/vqcc-data/starter-kit', '--competition', '/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation', '--factor', '/home/cld-main/work/vqcc-data/starter-kit/starter_kit/starter/task1_factorization/FeMoco76_65_60_60.npz', '--sha256', 'b13120cb62bf4cfcf41a3dc0c78cd6e58e17dacc7d0691834cee2cc6e4bc642b', '--out', '/home/cld-main/work/vqcc-data/pra246-google-v4-01']
print(json.dumps({"argv":argv}),flush=True)
result=subprocess.run(argv)
Path('/home/cld-main/work/vqcc-data/pra246-google-v4-01.exit.json').write_text(json.dumps({"returncode":result.returncode,"finished_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()})+"\n")
raise SystemExit(result.returncode)
