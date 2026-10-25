"""Retained DQI attributions and reference entry point after the PRA-231 recovery."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("credit, required", [
    ("anazemcev v4 cell-45", (
        "Original experiments, explanations and added implementations: anazemcev / ViberTeam.",
        "https://www.kaggle.com/code/anazemcev/quantum-circuits-source-exact-compilation",
        "4f017407a40e0988583c9645662407046f04019357adac648b90b2b94598acdb",
        "tasks/dqi/bm_forney/", "tasks/dqi/generate.py",
    )),
    ("Gluzdov field/adapter", (
        "competition-field formula derivation, Kickmix adapter",
        "V3", "V1",
        "https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361529794",
        "https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361509836",
        "gu_formula_derivation.py", "port_runtime.py", "gu_port.py",
    )),
    ("Kozykorpesh symbolic lowering", (
        "V3/run361677445", "symbolic DQI lowering",
        "https://www.kaggle.com/code/kozykappa/quantum-ai-lb-score-6-68108?scriptVersionId=361677445",
        "symbolic_runtime.py", "tasks/dqi/generate.py",
    )),
    ("Gluzdov V6", (
        "V6/run361592338", "Compact inverse-norm schedules, template-word loans and streamed sweep",
        "https://www.kaggle.com/code/dmitriigluzdov/quantum-circuit-compilation-from-source?scriptVersionId=361592338",
        "round2_gadgets.py", "borrow.py", "gu_port.py", "tasks/dqi/generate.py",
    )),
])
def test_inherited_dqi_attributions_are_distributed(credit, required):
    notice = (ROOT / "notices" / "20-dqi.txt").read_text()
    entries = [line for line in notice.splitlines() if line.startswith(f"- {credit}:")]
    assert len(entries) == 1, f"missing or duplicate attribution: {credit}"
    for token in (*required, "Apache", "cell 45"):
        assert token in entries[0], f"{credit}: missing {token}"


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
