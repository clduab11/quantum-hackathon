# Negative controls

These read-only checks must exit 1. They demonstrate the reported config failure and the unmet DQI rollback target before applying the documented command.

## old-config-is-not-dqi-only

```bash
uv run python - <<'PY'
import yaml
from pathlib import Path
current = yaml.safe_load(Path('configs/gates/pra250-hankel.yaml').read_text())
old = yaml.safe_load(Path('configs/gates/pra236-jfraction.yaml').read_text())
assert old['generators']['dfthcsos'] == current['generators']['dfthcsos'], 'old config changes chemistry generator'
assert old['inputs'] == current['inputs'], 'old config changes chemistry input'
PY
```

Exit status: 1 (expected 1).

```text
Traceback (most recent call last):
  File "<string>", line 5, in <module>
    assert old['generators']['dfthcsos'] == current['generators']['dfthcsos'], 'old config changes chemistry generator'
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: old config changes chemistry generator
```

## before-rollback-target

```bash
uv run python - <<'PY'
import hashlib, zipfile
with zipfile.ZipFile('/home/cld-main/work/vqcc-data/queue/pra250-hankel.zip') as z:
    with z.open('dqi.kmb') as s:
        actual = hashlib.file_digest(s, 'sha256').hexdigest()
assert actual == 'dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d', f'rollback target not met: {actual}'
PY
```

Exit status: 1 (expected 1).

```text
Traceback (most recent call last):
  File "<string>", line 5, in <module>
    assert actual == 'dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d', f'rollback target not met: {actual}'
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: rollback target not met: 17df18286ae5713fd08584cb616116f800c2eed92dce1566f78310f187c58c52
```

