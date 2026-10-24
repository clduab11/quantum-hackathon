"""Derive the invsqrt QROM coefficient table from the specification.

The 256 triples are the output of the Lawson weighted minimax followed by the
exact-domain integer search in `signed_digit.regenerate_tables_exact`. No
external dataset is read. The SHA-256 below is a drift check: if the numeric
libraries move a coefficient, generation stops instead of silently changing
the scored circuit.

    python tasks/invsqrt/fit_coefficients.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tasks.invsqrt import signed_digit as sd  # noqa: E402

# Digest of the integer rows this environment derives. Not a dataset pin.
EXPECTED_ROW_SHA256 = "a36d1636d31d6b28a3bd5dce475bb3f8ef451b8b50deefc403853f184d4e6dcc"
PROVENANCE = "own"

# Committed fitting recipe. The integer search starts at the rounded Lawson
# coefficient of the mathematical target. No external table is read, and none
# is the optimiser start. Historical P0 copies stay in the old records.
RECIPE = {
    "provenance": PROVENANCE,
    "target": (
        "For each segment, y = 2**((e - 1) / 2) / sqrt(M) with M in [1, 2). "
        "The emitted phase is beta / sqrt(x) at beta = 1."
    ),
    "precision": (
        "IEEE-754 float64 Lawson fit (numpy.linalg.lstsq, rcond=None) on a "
        "fixed grid. Stored triples are Python ints. Relative error is judged "
        "in units of 2^-24."
    ),
    "domain": (
        "x = 1..3133452. Segment key (e, a) with e in {0, 1} and a in 0..127. "
        "The residual set is valid_residuals. M = x_norm / 2^21 in [1, 2)."
    ),
    "objective": (
        "Minimise the maximum relative error of the quadratic signed-digit "
        "Horner value against the target. Continuous stage: Lawson reweighting, "
        "80 iterations, 3001-point grid, weight sqrt(M) / scale. Integer stage: "
        "the same relative error inside a radius of the rounded continuous "
        "coefficients, then K0 by an integer centre search."
    ),
    "rounding": (
        "K2 and K1 centres use Python round (half to even) of co[2] * 2^f2 and "
        "-co[1] * 2^f1. Horner shifts use rd: for a non-negative value, add the "
        "bit immediately below the kept field. K0 is the integer argmin."
    ),
    "widths": {"f2": 8, "f1": 19, "fyr": 27, "gy": 1, "drop2": [5]},
    "search": {
        "first_c_radius": 1,
        "first_b_radius": 3,
        "refine_if_ratio_above": 0.95,
        "refine_c_radius": 4,
        "refine_b_radius": 7,
    },
    "optimiser_start": (
        "Rounded Lawson coefficient of the mathematical target. An imported "
        "coefficient table is not read and is not the start."
    ),
    "determinism": (
        "No random seed. The grid, iteration count and radii are fixed. A "
        "second in-process fit must return the same integers. Numeric drift "
        "fails closed: generation raises unless the row SHA-256 equals the "
        "pinned digest. This is not a saved checkpoint."
    ),
    "row_sha256": EXPECTED_ROW_SHA256,
    "row_encoding": (
        "JSON array of 256 [K2, K1, K0] triples, row-major (e, a), "
        "separators (',', ':'), UTF-8, no spaces"
    ),
    "excluded_inputs": [
        "Kaggle coefficient dataset version 21136269",
        "toolbox fusion archives",
        "a selected invsqrt circuit binary",
    ],
}


def coefficient_rows(tables: dict) -> list[list[int]]:
    """Row-major (e, a) order used by the 256-entry QROM."""
    return [[int(v) for v in tables[(e, a)]] for e in range(2) for a in range(128)]


def row_sha256(rows: list[list[int]]) -> str:
    blob = json.dumps(rows, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


@lru_cache(maxsize=1)
def derived_tables():
    """Fit the selected configuration once per process and check the digest."""
    cfg = sd.selected_cfg()
    tables, report = sd.regenerate_tables_exact(cfg)
    rows = coefficient_rows(tables)
    digest = row_sha256(rows)
    if digest != EXPECTED_ROW_SHA256:
        raise RuntimeError(
            f"Derived coefficient digest {digest} != {EXPECTED_ROW_SHA256}. "
            "The numeric fit moved; refuse to build a different circuit."
        )
    worst = float(report["worst_ratio"]) / 2**24
    return cfg, tables, worst, report


def main(argv: list[str] | None = None) -> int:
    del argv
    _cfg, _tables, worst, report = derived_tables()
    payload = {
        "provenance": PROVENANCE,
        "source": "tasks/invsqrt/fit_coefficients.py",
        "method": "Lawson weighted minimax plus exact-domain integer search",
        "recipe": RECIPE,
        "row_sha256": EXPECTED_ROW_SHA256,
        "normalized_worst_relative_error": worst,
        "worst_ratio": report["worst_ratio"],
        "worst_key": report["worst_key"],
        "reachable_normalized_inputs": report["reachable_normalized_inputs"],
        "rows": 256,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
