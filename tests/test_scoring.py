import json
import math

import pandas as pd
import pytest

from harness import score_local
from harness.runtime import load_metric
from harness.verification import report


def test_aggregation_matches_metric_v10():
    solution = pd.DataFrame({'row_id': [0, 1, 2], 'benchmark': ['invsqrt', 'dqi', 'dfthcsos'],
                             'baseline_cost': [8., 27., 64.]})
    submission = pd.DataFrame({'row_id': [0, 1, 2], 'cost': [4., 9., 16.], 'seconds': [1., 1., 1.]})
    score, _ = load_metric().score(solution, submission, 'row_id')
    assert score == math.prod([2., 3., 4.]) ** (1 / 3)


def test_partial_calibration_is_not_a_baseline(tmp_path):
    path = tmp_path / 'baseline.jsonl'
    path.write_text(json.dumps({'environment': {}}) + '\n')
    with pytest.raises(ValueError, match='Incomplete'):
        score_local.load_baseline(path)


def test_environment_drift_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / 'baseline.jsonl'
    path.write_text('{"environment": {"salt": "old"}}\n{"complete": true}\n')
    monkeypatch.setattr(score_local, 'fingerprint', lambda: {'salt': 'new'})
    with pytest.raises(ValueError, match='environment differs'):
        score_local.load_baseline(path)


def test_report_distinguishes_synthesized_t_and_dqi_t():
    inv = {'status': 'PASS', 'num_qubits': 2, 'toffoli_count': 3,
           't_count': 1, 'rotation_count': 0, 'score': 6.5}
    assert report('invsqrt', inv, 1)['T'] == 1
    dqi = {'status': 'PASS', 'num_qubits': 2, 'toffoli_count': 3,
           'repetition_factor': 1.2, 'score': 14.4, 'value_errors': 1, 'phase_errors': 2,
           'effective_error_rate': .01}
    row = report('dqi', dqi, 1)
    assert row['T'] == 3 and row['failures'] == 3


def test_report_rejects_wrong_formula():
    result = {'status': 'PASS', 'num_qubits': 2, 'toffoli_count': 3,
              't_count': 1, 'rotation_count': 0, 'score': 999}
    with pytest.raises(ValueError, match='accounting formula differs'):
        report('invsqrt', result, 1)
