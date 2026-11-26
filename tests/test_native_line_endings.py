"""Keep historical CRLF evidence byte-identical across native checkouts."""
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CRLF_EVIDENCE = (
    'ledger/manifests/index-legacy.csv',
    'docs/research/dfthcsos-factorization/notes/input_sha256.tsv',
    'docs/research/dfthcsos-factorization/notes/section8_reproduction.json',
)


@pytest.mark.parametrize('relative', CRLF_EVIDENCE)
def test_frozen_crlf_evidence_is_exempt_from_text_conversion(relative):
    result = subprocess.check_output(
        ['git', 'check-attr', '-z', 'text', '--', relative], cwd=ROOT,
    ).decode().split('\0')
    assert result[:3] == [relative, 'text', 'unset']
    canonical = subprocess.check_output(['git', 'show', ':' + relative], cwd=ROOT)
    assert b'\r\n' in canonical
    assert (ROOT / relative).read_bytes() == canonical
