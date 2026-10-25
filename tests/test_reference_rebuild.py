"""The reference submission (submission-001) is rebuilt from committed source (R10, PRA-211).

The invsqrt reference circuit is rebuilt here because it is cheap (about six seconds). The dqi
and dfthcsos rebuilds are exercised by the recorded G5 run on the submission-001 manifest, not by
the unit suite (dqi.kmb is 886 MB).
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from ledger.gates.runner import CONFIG_DIR, load_config

ROOT = Path(__file__).resolve().parents[1]
# SHA-256 of sample_submission/invsqrt.kmb, as recorded in submission-001's manifest.
REFERENCE_INVSQRT_SHA256 = "e2bf8eb64350a4460a271fc7f1d591ef125b1e276377e9a0f64b96ab3ca321e1"


def test_invsqrt_reference_port_rebuilds_the_submitted_bytes(tmp_path: Path):
    pytest.importorskip("kickmix")
    proc = subprocess.run([sys.executable, "tasks/invsqrt/reference.py", "--out", str(tmp_path)],
                          cwd=ROOT, capture_output=True, text=True, check=True)
    assert "7,735 Toffolis, 260 qubits" in proc.stdout
    digest = hashlib.sha256((tmp_path / "invsqrt.kmb").read_bytes()).hexdigest()
    assert digest == REFERENCE_INVSQRT_SHA256


def test_reference_port_is_attributed_and_reads_no_package_file():
    text = (ROOT / "tasks" / "invsqrt" / "reference.py").read_text()
    assert "SPDX-License-Identifier: Apache-2.0" in text
    assert "verifiers/invsqrt/nr_reference_circuit.py" in text
    assert "Copyright Google Quantum AI" in text
    for token in ("VQCC_DATA", "sample_submission", "shutil", "copyfile"):
        assert token not in text, token


def test_reference_config_rebuilds_every_task_from_committed_builders():
    config = load_config(CONFIG_DIR / "reference.yaml")
    assert config.generators == {
        "invsqrt": ["{python}", "tasks/invsqrt/reference.py", "--out", "{out}"],
        "dqi": ["{python}", "tasks/dqi/reference_circuit.py", "--out", "{out}"],
        "dfthcsos": ["{python}", "tasks/dfthcsos/generate.py", "--out", "{out}"],
    }
    for argv in config.generators.values():
        assert (ROOT / argv[1]).is_file(), argv[1]
    # The copier that cleared G5 for submission-001 is retired (D-PRA211-01).
    assert not (ROOT / "ledger" / "examples" / "reference_generator.py").exists()
