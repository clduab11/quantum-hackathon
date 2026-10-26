import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'pra245_measure', ROOT / 'ledger/evidence/pra245/measure_declared_factors.py')
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)

# SpinFreeData_V1(1, 496, 384, 76, 10, 11) as the verifier's heuristic_costs reports it.
HEURISTIC = dict(toffoli=11310, persistent_qubits=83, temporary_qubits=640)


def test_angle_cap_stops_at_nine_words_for_572_addresses_at_11_bits():
    rows = measure.angle_rows(76, 1, 496, 11, HEURISTIC, 47.855856272)
    assert [r['J'] for r in rows] == list(range(1, 10))  # 10 + 9 + 10*11 = 129 > 128
    assert rows[-1]['angle_qubits'] == 118
    best = max(rows, key=lambda r: r['ratio'])
    assert (best['J'], best['T'], best['Q']) == (9, 21570, 822)
    assert best['ratio'] == pytest.approx(3.954696, abs=1e-6)


def test_recorded_measurements_match_the_pins_and_pass_every_gate():
    pins = json.loads((ROOT / 'ledger/manifests/inputs/pra245-thc-public.json').read_text())
    results = json.loads((ROOT / 'ledger/evidence/pra245/measurements.json').read_text())
    assert results['verifier_sha256'] == pins['verifier']['verify_py_sha256']
    assert results['costs_prepare_sha256'] == pins['verifier']['costs_prepare_py_sha256']
    by_hash = {r['sha256']: r for r in results['results']}
    for pin in (pins['shipping'], pins['fallback'], *pins['measured_not_shipped']):
        row = by_hash[pin['sha256']]
        assert row['bytes'] == pin['bytes']
        assert row['problems'] == [] and row['passes_accuracy']
        assert row['words_changed'] == 0
    ratios = {h: r['best']['ratio'] for h, r in by_hash.items()}
    assert max(ratios, key=ratios.get) == pins['shipping']['sha256']
