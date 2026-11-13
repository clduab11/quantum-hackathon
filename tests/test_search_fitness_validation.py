# SPDX-License-Identifier: Apache-2.0
"""A malformed feasible record must never receive a perfect search fitness."""
import pytest

from search.fitness import combined_score


@pytest.mark.parametrize('task', ['invsqrt', 'dqi', 'dfthcsos'])
def test_incomplete_feasible_record_is_rejected(task):
    with pytest.raises(ValueError, match='feasible.*cost'):
        combined_score({'feasible': True, 'task': task})


VALID_FIELDS = {
    'invsqrt': {'qubit_count': 63.0, 'cost_c': 1643.6},
    'dqi': {'qubit_count': 889.0, 'toffoli_count': 474308.0, 'r_eps': 1.19126},
    'dfthcsos': {'qubit_count': 430.0, 'toffoli_count': 16366.0, 'lambda_eff': 48.0},
}


@pytest.mark.parametrize('task,field', [
    (task, field) for task, fields in VALID_FIELDS.items() for field in fields
])
@pytest.mark.parametrize('bad', [None, 0.0, -1.0, float('nan'), float('inf'), 'bad', True])
def test_invalid_feasible_resource_is_rejected(task, field, bad):
    record = {'feasible': True, 'task': task, **VALID_FIELDS[task], field: bad}
    with pytest.raises(ValueError, match='feasible.*cost'):
        combined_score(record)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), 'bad', True])
@pytest.mark.parametrize('field', ['log_cost', 'log_qubits'])
def test_invalid_log_override_is_rejected(field, bad):
    record = {'feasible': True, 'task': 'dqi', **VALID_FIELDS['dqi'], field: bad}
    with pytest.raises(ValueError, match='feasible.*cost'):
        combined_score(record)


def test_finite_log_cost_override_remains_supported():
    assert combined_score({'feasible': True, 'task': 'dqi', 'log_cost': 20.0}) == pytest.approx(11 / 14)


def test_aliases_and_explicit_log_terms_preserve_cost():
    import math
    record = {'feasible': True, 'task': 'dqi', **VALID_FIELDS['dqi']}
    aliases = {**record, 'num_qubits': record['qubit_count'], 'R_eps': record['r_eps']}
    del aliases['qubit_count'], aliases['r_eps']
    assert combined_score(aliases) == combined_score(record)
    logs = {'feasible': True, 'task': 'dqi',
            'log_qubits': math.log(record['qubit_count']),
            'log_toffoli': math.log(record['toffoli_count']),
            'log_r_eps': math.log(record['r_eps'])}
    assert combined_score(logs) == pytest.approx(combined_score(record))


def test_proxy_records_keep_graded_infeasible_fitness_without_costs():
    assert combined_score({'feasible': False, 'fraction_correct': .99}) < .5


@pytest.mark.parametrize('field', ['toffoli_count', 'num_qubits', 'lambda_eff'])
def test_evaluator_does_not_invent_missing_full_verifier_costs(field):
    from search.evaluator import score_policy
    full = {'status': 'PASS', 'toffoli_count': 93237.0,
            'num_qubits': 730.0, 'lambda_eff': 49.3}
    del full[field]
    with pytest.raises(ValueError, match='feasible.*cost'):
        score_policy(True, 1.0, None, full, resources={'q': 1.0, 't': 1.0})


@pytest.mark.parametrize('field', ['qubit_count', 'toffoli_count', 'lambda_eff'])
@pytest.mark.parametrize('value', [.5, 1e-300])
def test_subunit_raw_resources_keep_existing_scoring_floor(field, value):
    from search.fitness import feasible_score, task_log_cost
    record = {'feasible': True, 'task': 'dfthcsos', **VALID_FIELDS['dfthcsos'], field: value}
    assert combined_score(record) == pytest.approx(feasible_score(task_log_cost('dfthcsos', record)))


@pytest.mark.parametrize('task,term', [
    ('invsqrt', 'log_qubits'), ('invsqrt', 'log_cost_c'),
    ('dqi', 'log_qubits'), ('dqi', 'log_toffoli'), ('dqi', 'log_r_eps'),
    ('dfthcsos', 'log_qubits'), ('dfthcsos', 'log_toffoli'),
    ('dfthcsos', 'log_lambda_eff'),
])
def test_none_log_override_uses_valid_raw_evidence(task, term):
    record = {'feasible': True, 'task': task, **VALID_FIELDS[task]}
    assert combined_score({**record, term: None}) == combined_score(record)


def test_unknown_task_rejected_even_with_log_cost_override():
    with pytest.raises(ValueError, match='unknown task'):
        combined_score({'feasible': True, 'task': 'unknown', 'log_cost': 20.0})


def test_numeric_string_cost_evidence_remains_supported():
    record = {'feasible': True, 'task': 'dqi', **VALID_FIELDS['dqi']}
    strings = {key: str(value) for key, value in VALID_FIELDS['dqi'].items()}
    assert combined_score({**record, **strings}) == combined_score(record)


@pytest.mark.parametrize('task,field', [('dqi', 'r_eps'), ('dfthcsos', 'lambda_eff')])
def test_adapters_do_not_invent_missing_feasible_cost_terms(task, field):
    from search.adapters.dqi import DqiAdapter
    from search.adapters.dfthcsos import DfthcsosAdapter
    adapter = {'dqi': DqiAdapter, 'dfthcsos': DfthcsosAdapter}[task]()
    verified = {'feasible': True, **VALID_FIELDS[task]}
    del verified[field]
    fields = adapter.cost_fields(None, {}, verified)
    with pytest.raises(ValueError, match='feasible.*cost'):
        combined_score(fields)


@pytest.mark.parametrize('task', ['dqi', 'dfthcsos'])
def test_adapter_infeasible_proxy_needs_no_cost_terms(task):
    from search.adapters.dqi import DqiAdapter
    from search.adapters.dfthcsos import DfthcsosAdapter
    adapter = {'dqi': DqiAdapter, 'dfthcsos': DfthcsosAdapter}[task]()
    assert combined_score(adapter.cost_fields(None, {}, None)) < .5
