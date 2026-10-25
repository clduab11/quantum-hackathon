"""Pins for the DQI port. These checks do not build the circuit."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DQI = ROOT / "tasks" / "dqi"
PORT = DQI / "bm_forney"

# Committed bytes. A drift here is a provenance change and must update PROVENANCE.md.
PINNED = {
    "gu_classical.py": "c05c9e7a84a69e3ad0590b972642dcb30c2c29ca2613a821c82d09d53556ba62",
    "gu_linear.py": "d0b89d494ae63ec28e8bac6f33b344c11aaaab378d0cec81683b1a5743ed25d3",
    "gu_port.py": "93a753e54e0ae28e0ca37a168f0c4e8a740f6e1ab82ff7106b1fdd24bb487250",
    "gu_formula_derivation.py": "d55e238aa5c7ccb26b0d5cea8fdb911ecbb4ae54782df3e50950140164204dbb",
    "round2_gadgets.py": "76dd907a2f19f16c38c49f6a631909cdb732d17fc7809d3797bb7c08e67c5645",
    "symbolic_runtime.py": "f25047e0138bfe75cf177afd6d50e7694d047ed8cacf26ac83b7eaa6224058a4",
    "port_runtime.py": "cbfc4562cd110bce7f3d214ec179e02ec00e1165446504be28c0c3e44fbdf293",
    "borrow.py": "8fd2f83cc831d9d60b6a13d75e0a36dd5ed9033dfe9d8b5ec0ee899780cdfe39",
    "contract.json": "b5fa02899021142b7f265f1e18f366b0d6f55944023b3cf249f976c655d2097e",
    "windows.json": "a5dff27decbf564d6b810ece4dd345099eac5e4ba3d8260dcbf263f22dc9da99",
    "LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "UPSTREAM_COMMIT.txt": "54c3f3a787ba58aab8e56bd313e878fcae93b7c3d1b24498ff2ff5e8ccf4741b",
}

FORBIDDEN = (
    "decoder_input",
    "selected/dqi",
    "femoco",
    "dfthc_group",
    "17301475",
    "np.load",
    "numpy.load",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pinned_port_bytes_match_the_provenance_map():
    for name, digest in PINNED.items():
        assert _sha(PORT / name) == digest, name
    commit = (PORT / "UPSTREAM_COMMIT.txt").read_text().strip()
    assert commit == "64b5a13aa249f1360846657392e6c66817b26d0f"


def test_field_and_windows_are_not_a_numeric_target_file():
    contract = json.loads((PORT / "contract.json").read_text())
    windows = json.loads((PORT / "windows.json").read_text())
    assert contract["gf_poly"] == 4179
    assert set(windows) == {"bm_windows", "psi_windows"}
    for banned in ("KT12", "KT6", "KT3", "CUBE3Q", "PAIR3", "LIN"):
        assert banned not in windows


def test_generator_sources_do_not_name_forbidden_parents():
    for path in DQI.rglob("*"):
        if path.suffix not in {".py", ".json"} or not path.is_file():
            continue
        text = path.read_text(errors="replace")
        for token in FORBIDDEN:
            assert token not in text, f"{path.relative_to(ROOT)} contains {token}"
        assert path.suffix not in {".kmb", ".npz"}


def test_modified_files_carry_a_port_notice():
    runtime = (PORT / "port_runtime.py").read_text()
    borrow = (PORT / "borrow.py").read_text()
    driver = (DQI / "generate.py").read_text()
    notice = (ROOT / "notices" / "20-dqi.txt").read_text()
    assert "Modified port of src/gen_dqi_v6/port_runtime.py" in runtime
    assert "Modified extract of borrow_template" in borrow
    assert "not independent clean-room authorship" in driver
    assert "64b5a13aa249f1360846657392e6c66817b26d0f" in notice
    assert "tasks/dqi/PROVENANCE.md" in notice
    assert "arXiv:2610.22367" in notice


def test_reference_rebuild_uses_the_reference_decoder(tmp_path):
    import subprocess
    import sys

    from ledger.gates.runner import CONFIG_DIR, load_config
    from tasks.dqi.reference_circuit import build_reference_circuit

    config = load_config(CONFIG_DIR / "reference.yaml")
    assert config.generators["dqi"] == [
        "{python}", "tasks/dqi/reference_circuit.py", "--out", "{out}"
    ]
    subprocess.run(
        [sys.executable, config.generators["dqi"][1], "--out", str(tmp_path),
         "--m", "7", "--n", "2", "--degree", "3"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    expected = tmp_path / "expected.kmb"
    build_reference_circuit(7, 2, 3).to_file(expected, format="kmb")
    assert (tmp_path / "dqi.kmb").read_bytes() == expected.read_bytes()
