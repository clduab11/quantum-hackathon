"""The held PRA-231 recovery uses existing ledger gates to withdraw Route A."""

import hashlib
import json
from pathlib import Path

import pytest

from ledger.gates.runner import GateOrderError, enqueue
from ledger.run_manifest import ManifestError, read_manifest
from ledger.scorecard import reserve_slot, submit

ROOT = Path(__file__).resolve().parents[1]


def candidate():
    return read_manifest(ROOT / "ledger/manifests/candidates/pra226-dqi-only.json")


def test_route_a_recovery_withdraws_eligibility_without_erasing_passes():
    manifest = candidate()
    assert manifest.shipping_problems() == [
        "G5 not cleared on the current zip", "G5 is FAIL, it must PASS"
    ]
    assert len(manifest.gates) == 7
    assert manifest.gates[-2].gate == "G5"
    assert manifest.gates[-2].status == "PASS"
    assert "D-PRA226-03" in manifest.gates[-1].reason
    assert manifest.is_measured()
    raw = json.loads((ROOT / "ledger/manifests/candidates/pra226-dqi-only.json").read_text())
    assert hashlib.sha256(json.dumps(raw["gates"][:-1], sort_keys=True).encode()).hexdigest() == (
        "cdfa6ac4fa6aaf1606eea7fdc5851441442f95cef837ea3864cb6d27f1612c82"
    )
    evidence = ROOT / "ledger/evidence/pra231-recovery/withdrawal.json"
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == manifest.gates[-1].evidence_sha256
    pointer = ROOT / "ledger/queue/pra226-dqi-only.json"
    assert hashlib.sha256(pointer.read_bytes()).hexdigest() == json.loads(
        evidence.read_text()
    )["queue_pointer_sha256"]


@pytest.mark.parametrize("boundary", ["enqueue", "reserve", "submit"])
def test_withdrawn_route_a_stops_before_zip_or_slot_access(tmp_path, boundary):
    manifest = candidate()
    missing_zip = tmp_path / "not-opened.zip"
    destination = tmp_path / "not-created"

    def forbidden_upload(_):
        pytest.fail("withdrawn candidate reached uploader")

    error = GateOrderError if boundary == "enqueue" else ManifestError
    with pytest.raises(error, match="G5 not cleared"):
        if boundary == "enqueue":
            enqueue(manifest, missing_zip, destination)
        elif boundary == "reserve":
            reserve_slot(manifest, root=destination)
        else:
            submit(manifest, missing_zip, forbidden_upload, root=destination)
    assert not destination.exists()


def test_restored_dqi_generator_matches_preserved_reference_entry_point(tmp_path):
    from tasks.dqi import generate, reference_circuit
    from tasks.dqi.gates import g1_smoke

    restored = generate.build_reference_circuit(7, 2, 3)
    reference = reference_circuit.build_reference_circuit(7, 2, 3)
    restored.to_file(tmp_path / "restored.kmb", format="kmb")
    reference.to_file(tmp_path / "reference.kmb", format="kmb")
    assert (tmp_path / "restored.kmb").read_bytes() == (tmp_path / "reference.kmb").read_bytes()
    smoke = g1_smoke(None)
    assert smoke == {
        "status": "PASS", "qubits": int(restored.num_qubits),
        "toffoli": int(restored.operation_statistics().num_toffoli_like),
    }


@pytest.mark.parametrize("path", [
    "configs/gates/reference-invsqrt.yaml",
    "tasks/invsqrt/reference_gates.py",
    "tests/test_reference_invsqrt_gates.py",
])
def test_route_a_gate_extension_is_removed(path):
    assert not (ROOT / path).exists()
