# Direct byte comparison

```bash
uv run python - <<'PY'
import json, zipfile
from pathlib import Path
r = json.loads(Path('ledger/evidence/pra275-rollback/member-hashes.json').read_text())
with zipfile.ZipFile(r['source_zip']) as before, zipfile.ZipFile(r['output_zip']) as after:
    assert sorted(before.namelist()) == sorted(after.namelist())
    for name in before.namelist():
        if name != 'dqi.kmb':
            assert before.read(name) == after.read(name), name
            print('BYTE-EQUAL', name)
print('PASS: direct byte comparison of all ten retained members')
PY
```

Exit status: 0

```text
BYTE-EQUAL dfthcsos/angle_k_0.kmb
BYTE-EQUAL dfthcsos/angle_k_1.kmb
BYTE-EQUAL dfthcsos/angle_k_2.kmb
BYTE-EQUAL dfthcsos/angle_k_3.kmb
BYTE-EQUAL dfthcsos/angle_k_4.kmb
BYTE-EQUAL dfthcsos/angle_k_5.kmb
BYTE-EQUAL dfthcsos/angle_k_6.kmb
BYTE-EQUAL dfthcsos/angle_k_7.kmb
BYTE-EQUAL dfthcsos/submission.npz
BYTE-EQUAL invsqrt.kmb
PASS: direct byte comparison of all ten retained members
```
