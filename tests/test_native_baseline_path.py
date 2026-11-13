"""Store native full-shot calibration outside the repository without bypassing it."""
from pathlib import Path

from harness import score_local


def test_explicit_baseline_path_is_used_by_g3(tmp_path, monkeypatch):
    selected = tmp_path / 'evidence' / 'reference-baseline.jsonl'
    monkeypatch.setenv('VQCC_BASELINE', str(selected))
    monkeypatch.setattr(score_local, 'parse_submission', lambda _: {})
    seen = []

    def refuse_baseline(path):
        seen.append(path)
        raise ValueError('calibration must still be complete')

    monkeypatch.setattr(score_local, 'load_baseline', refuse_baseline)
    result = score_local.score_submission(tmp_path, salt_label=score_local.LOCAL_SALT)
    assert seen == [selected]
    assert result['status'] == 'FAIL: calibration must still be complete'


def test_baseline_default_is_unchanged_when_override_absent(monkeypatch):
    monkeypatch.delenv('VQCC_BASELINE', raising=False)
    assert score_local.baseline_path() == score_local.DATA.parent / 'reference-baseline.jsonl'
