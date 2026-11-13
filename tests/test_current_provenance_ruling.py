"""Current board rulings keep byte pins, not obsolete author exclusions."""
from ledger.benchmark_health import declared_input_problems


def test_pinned_apache_archive_is_not_rejected_by_author_name():
    entry = {
        'kind': 'vendored_circuit',
        'path': 'inputs/jday-archive/dqi.kmb',
        'sha256': 'a' * 64,
        'source_url': 'https://github.com/jday96314/QuantumAI-archive',
        'version': 'pinned-archive-commit',
        'licence': 'Apache-2.0',
        'licence_record': 'docs/decisions/D-HERMES-20261112-02.md',
    }
    assert declared_input_problems('dqi', entry) == []
