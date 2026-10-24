"""Exact DQI algebra checks. These do not build the full decoder."""

from tasks.dqi.algebra import smoke
from tasks.dqi.gates import g1_smoke


def test_g1_smoke_checks_field_and_one_product():
    result = g1_smoke(None)
    assert result["status"] == "PASS"
    assert result["modulus"] == 4179
    assert result["primitive_element"] == 2
    assert result["product"] == smoke()["product"]
    assert result["toffoli"] >= 1
