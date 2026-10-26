import subprocess,json,datetime
from pathlib import Path
argv=['/home/cld-main/work/.paperclip-worktrees/quantum-hackathon/PRA-246-factor-fit-v4/.venv/bin/python', '-m', 'tasks.dfthcsos.factor_fit_v4', '--starter', '/home/cld-main/work/vqcc-data/starter-kit', '--competition', '/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation', '--factor', '/home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz', '--sha256', '809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5', '--out', '/home/cld-main/work/vqcc-data/pra246-declared-v4-04', '--resume-continuous', '/home/cld-main/work/.paperclip-worktrees/quantum-hackathon/PRA-246-factor-fit-v4/ledger/evidence/pra246/continuous-resume-run03.json', '--resume-sha256', '362d82da2f1f03fdcf1968378ae0699574dc653bfe8f35bfdcc15f4f7063d440']
print(json.dumps({"argv":argv}),flush=True)
result=subprocess.run(argv)
Path('/home/cld-main/work/vqcc-data/pra246-declared-v4-04.exit.json').write_text(json.dumps({"returncode":result.returncode,"finished_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()})+"\n")
raise SystemExit(result.returncode)
