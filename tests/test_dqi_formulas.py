"""Regenerated GF(2^12) formulas for modulus 4179. Does not build the circuit."""

import tempfile
from pathlib import Path

from tasks.dqi.generate import regenerate_tables


def test_regenerated_tables_match_the_competition_field():
    with tempfile.TemporaryDirectory() as tmp:
        report = regenerate_tables(Path(tmp))
    assert report["modulus"] == 4179
    assert report["primitive"] == 2
    assert report["timings"]["KT12_s"] >= 0
