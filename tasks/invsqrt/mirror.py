"""Exhaustive integer mirror of the invsqrt arithmetic (gate G2).

For every x in 1..3,133,452 the pinned quadratic signed-digit pipeline is
evaluated in integers. The phase, in units of 2^-64 turns, must sit within
2^-24 / sqrt(x) of 1/sqrt(x). The derivative split is checked on all
4,194,304 normalized address/offset pairs, so the circuit's shorter residual
equals that pipeline.

    python tasks/invsqrt/mirror.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tasks.invsqrt.signed_digit import (  # noqa: E402
    _derivative_reference,
    exhaustive_certificate,
    layout,
    load_or_build_tables,
    prepare_derivative_split,
)

NORMALIZED_PAIRS = 4_194_304


def run_mirror() -> dict:
    """Return the certificate. `pass` is true only when every x and every split pair holds."""
    cfg, tables, table_worst = load_or_build_tables()
    certificate = exhaustive_certificate(cfg, tables)
    reference = _derivative_reference(True)
    _split, bounds = prepare_derivative_split(reference, cfg, tables)
    place = layout(cfg, tables)
    split_ok = (
        bounds["normalized_addresses_checked"] == NORMALIZED_PAIRS
        and place["w1"] == 18
        and place["LB"] == 21
        and place["S"] == 20
        and place["whi"] == 8
    )
    from tasks.invsqrt.generate import compilation_report

    built = compilation_report()
    phase_ok = built["phase"]["phase_match"] is True
    calibration_margin = int(built["calibration"]["margin_units"])
    passed = bool(certificate["pass"]) and split_ok and phase_ok and calibration_margin > 0
    if "estimated_expected_cost" not in built["estimate"]:
        raise KeyError("compilation_report estimate lacks estimated_expected_cost")
    return {
        "pass": passed,
        "tested_inputs": certificate.get("tested_inputs"),
        "worst_ratio": certificate.get("worst_ratio"),
        "worst_x": certificate.get("worst_x"),
        "min_margin_units": certificate.get("min_margin_units"),
        "phase_fraction_bits": certificate.get("phase_fraction_bits"),
        "table_worst_relative_error": table_worst,
        "derivative_split": bounds,
        "layout": {key: place[key] for key in ("w1", "LB", "S", "whi")},
        "first_bad_x": certificate.get("first_bad_x"),
        "phase_match": phase_ok,
        "calibration_margin_units": calibration_margin,
        "calibration_worst_x": built["calibration"]["worst_x"],
        "qubits": built["final"]["qubits"],
        "static_toffoli": built["final"]["static_toffoli"],
        "expected_toffoli": built["final"]["expected_toffoli"],
        "rotations": built["final"]["rotations"],
        "estimated_ratio": built["estimate"]["ratio"],
        "estimated_expected_cost": built["estimate"]["estimated_expected_cost"],
        "sha256": built["sha256"],
        "coefficient_provenance": built["coefficient_provenance"],
        "circuit_authorship": built["circuit_authorship"],
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    report = run_mirror()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
