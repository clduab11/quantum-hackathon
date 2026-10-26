"""Exact Schur arithmetic and oracle regressions, shared with G1."""
from tasks.dqi.schur.gates import check_joint_cover, check_small_generator, check_inverse_phase


def test_joint_cover_all_inputs():
    check_joint_cover()


def test_small_generator_restores_registers_and_applies_error_phase(tmp_path):
    check_small_generator(tmp_path)


def test_inverse_phase_complete_domain_restores_mask_and_scratch():
    check_inverse_phase()


def test_schur_source_map():
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'tasks/dqi/schur'
    for name, record in json.loads((root / 'source-pins.json').read_text())['files'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == record['port_sha256']
