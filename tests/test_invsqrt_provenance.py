"""Pins for the invsqrt port. These checks do not build the circuit."""

import hashlib
from pathlib import Path

from tasks.invsqrt.fit_coefficients import EXPECTED_ROW_SHA256, PROVENANCE, RECIPE
from tasks.invsqrt.generate import CIRCUIT_AUTHORSHIP

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "tasks" / "invsqrt"

# Committed bytes. A drift here is a provenance change and must update PROVENANCE.md.
PINNED = {
    "fit_coefficients.py": "1e97f77e6d3498e8dde2fe9312bfbf5c505c62e5c68938c846e0c8fc0d39aba3",
    "signed_digit.py": "f106ea0a6f3a5d37d3e44cbe79d8f2f4777c86636d52ee9888ede09595db0c72",
    "generate.py": "c6248e89382cacd193123da35188c63b9b5e7cf390b1182eccdb588c171a14a1",
    "schedule90.py": "48adbc9ae7adb0e40f0290ef8d0b5ecb467c510288c887bb1324cca856439f2d",
    "affine.py": "aa351a287c507c264a8aa7d172e1c7b9bfc1d0dcb78c8fa61b92996947eba290",
    "peephole.py": "d5ed02b0d28392cc637111fc94fb1760c71feda4f8ca7aad6f73944e81fff54c",
    "calibrate.py": "7fc0c1cac6ff45753c25d98dfa7cd82fb4803332c37fb616af18fabe47cef309",
    "mirror.py": "44f9928fe54f84c45977e9cfe637e7ad2068ab7cda7dd9fb2949a6666cd1513d",
    "gates.py": "3f569d70c97f3c41f7b627050e7a40494d54c546da196788c1bc08f55162890d",
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
    assert PROVENANCE == "own"
    assert CIRCUIT_AUTHORSHIP == "port"
    for key in (
        "precision",
        "domain",
        "objective",
        "rounding",
        "determinism",
        "optimiser_start",
        "row_sha256",
    ):
        assert RECIPE[key], key
    assert RECIPE["provenance"] == "own"
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
    notice = (ROOT / "NOTICE").read_text()
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
