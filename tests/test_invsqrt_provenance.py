"""Pins for the invsqrt port. These checks do not build the circuit."""

import hashlib
from pathlib import Path

from ledger.registers import notice_text
from tasks.invsqrt.fit_coefficients import EXPECTED_ROW_SHA256, PROVENANCE, RECIPE
from tasks.invsqrt.generate import CIRCUIT_AUTHORSHIP

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "tasks" / "invsqrt"

# Committed bytes. A drift here is a provenance change and must update PROVENANCE.md.
PINNED = {
    "fit_coefficients.py": "35d36f95aa4bb7c63bf8cd24d72df594abdd679a3ed770cb2fcced0200cda839",
    "signed_digit.py": "ab08c1f178405cae9872281fbe73ca41c5de160bea4b5ddeece41b55ac708cd5",
    "generate.py": "9ccdffd0cba53a097c78d99d833b9bcc37e9be387f62ed723a8173cd2cdf498c",
    "schedule90.py": "58c88937e18e2c96e5e92f3a2576b3d32661de0d93221d4f288e314bb4c81edb",
    "affine.py": "aa351a287c507c264a8aa7d172e1c7b9bfc1d0dcb78c8fa61b92996947eba290",
    "peephole.py": "d5ed02b0d28392cc637111fc94fb1760c71feda4f8ca7aad6f73944e81fff54c",
    "calibrate.py": "7fc0c1cac6ff45753c25d98dfa7cd82fb4803332c37fb616af18fabe47cef309",
    "mirror.py": "44f9928fe54f84c45977e9cfe637e7ad2068ab7cda7dd9fb2949a6666cd1513d",
    "gates.py": "d43b4e21cf1fa5aa7ae1519f6378a981538b769e3d54a2f6eb40b38f73d38265",
}

FORBIDDEN = (
    "coefficients.json",
    "fusion/",
    "selected/invsqrt",
    "np.load",
    "numpy.load",
    ".npz",
    "mizeroluckygall",
)


def test_pinned_module_bytes_match_the_provenance_map():
    for name, digest in PINNED.items():
        data = (INV / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
        assert digest in (INV / "PROVENANCE.md").read_text()


def test_recipe_records_the_fit_and_excludes_the_old_table():
    assert PROVENANCE == "regenerated; dataset-adapted calibration; licence unresolved"
    assert CIRCUIT_AUTHORSHIP == "port"
    for key in (
        "calibration_lineage",
        "precision",
        "domain",
        "objective",
        "rounding",
        "determinism",
        "optimiser_start",
        "row_sha256",
    ):
        assert RECIPE[key], key
    assert RECIPE["provenance"] == "regenerated; dataset-adapted calibration; licence unresolved"
    assert RECIPE["row_sha256"] == EXPECTED_ROW_SHA256
    start = RECIPE["optimiser_start"].lower()
    assert "lawson" in start
    assert "not the start" in start
    assert "21136269" in " ".join(RECIPE["excluded_inputs"])
    assert RECIPE["widths"] == {"f2": 8, "f1": 19, "fyr": 27, "gy": 1, "drop2": [5]}


def test_python_does_not_name_forbidden_inputs():
    for path in INV.rglob("*.py"):
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        for token in FORBIDDEN:
            assert token not in text, f"{path.relative_to(ROOT)} contains {token}"


def test_provenance_map_credits_the_lineage_and_the_reference_only_notebooks():
    text = (INV / "PROVENANCE.md").read_text()
    notice = notice_text(ROOT)
    for name in (
        "Sumit",
        "Rudra",
        "Alex",
        "Kirill",
        "Kozykorpesh",
        "anazemcev",
        "Gluzdov",
        "Mizero",
        "LightningV08",
    ):
        assert name in text, name
    assert "reference-only" in text
    assert "code/coefficients.json" in text
    assert "fusion/*.npz" in text
    assert "selected/invsqrt.kmb" in text
    assert "PRA-205" in text
    assert "tasks/invsqrt/PROVENANCE.md" in notice
    assert "Mizero v1" in notice
    assert "Alex Chilton v8" in notice
