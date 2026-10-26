"""Route A uses reference invsqrt without loading the held implementation (PRA-226)."""

import importlib
import io
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ledger.gates.runner import CONFIG_DIR, load_config

ROOT = Path(__file__).resolve().parents[1]
HOOK_MODULE = "tasks.invsqrt.reference_gates"
REFERENCE_SHA256 = "e2bf8eb64350a4460a271fc7f1d591ef125b1e276377e9a0f64b96ab3ca321e1"


@pytest.fixture(scope="module")
def reference_bytes():
    pytest.importorskip("kickmix")
    from tasks.invsqrt.reference import build_nr_circuit

    buf = io.BytesIO()
    build_nr_circuit(10).to_file(buf, format="kmb")
    return buf.getvalue()


@pytest.fixture
def submission(tmp_path, reference_bytes):
    (tmp_path / "invsqrt.kmb").write_bytes(reference_bytes)
    return tmp_path


def test_route_a_retains_its_reference_factor_and_bm_forney_contract():
    path = CONFIG_DIR / "reference-invsqrt.yaml"
    config = load_config(path)
    # Route A is historical. New default candidates must not change its factor,
    # shot count or DQI builder. Compare against the frozen reference config.
    expected = yaml.safe_load((CONFIG_DIR / 'reference.yaml').read_text())
    expected["generators"]["dqi"][1] = "tasks/dqi/generate.py"
    for gate in expected["gates"]:
        if gate["id"] in {"G1", "G2"}:
            old = gate["params"]["hooks"]["invsqrt"]
            gate["params"]["hooks"]["invsqrt"] = old.replace("invsqrt.gates", "invsqrt.reference_gates")
    assert yaml.safe_load(path.read_text()) == expected
    assert config.generators == expected["generators"]


def test_g1_accepts_reference_output(submission):
    result = importlib.import_module(HOOK_MODULE).g1_smoke(submission)
    assert result["status"] == "PASS"
    assert result["sha256"] == REFERENCE_SHA256
    assert result["num_qubits"] == 260
    assert result["static_toffoli"] == 7735


@pytest.mark.parametrize("hook", ["g1_smoke", "g2_proxy"])
def test_hooks_reject_one_changed_byte(submission, reference_bytes, hook):
    data = bytearray(reference_bytes)
    data[-1] ^= 1
    (submission / "invsqrt.kmb").write_bytes(data)
    assert getattr(importlib.import_module(HOOK_MODULE), hook)(submission)["status"].startswith("FAIL")


def test_g2_simulates_submitted_reference_and_is_not_parity(submission):
    result = importlib.import_module(HOOK_MODULE).g2_proxy(submission)
    assert result["status"] == "PASS"
    assert result["parity"] is False
    assert result["shots"] == 1536
    assert result["failures"] == 0
    assert result["sha256"] == REFERENCE_SHA256


def test_g2_propagates_simulator_failure(submission, monkeypatch):
    from invsqrt import verify_submission_invsqrt as verifier

    def fail(circuit, spec, **kwargs):
        assert spec.width == 22 and spec.num_shots == 1536
        raise AssertionError("x was not restored.")

    monkeypatch.setattr(verifier, "verify", fail)
    result = importlib.import_module(HOOK_MODULE).g2_proxy(submission)
    assert result["status"] == "FAIL: x was not restored."
    assert result["parity"] is False


def test_hook_import_excludes_every_held_module():
    pytest.importorskip("kickmix")
    code = '''
import sys
import tasks.invsqrt.reference_gates
held = {"generate", "gates", "affine", "calibrate", "fit_coefficients", "schedule90",
        "signed_digit", "mirror", "peephole"}
loaded = {name for name in sys.modules if name.startswith("tasks.invsqrt.")
          and name.split(".")[2] in held}
assert not loaded, sorted(loaded)
'''
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, capture_output=True, text=True)
