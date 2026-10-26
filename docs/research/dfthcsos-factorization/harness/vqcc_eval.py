"""Windows-side evaluation harness for the dfthcsos lane (no kickmix).

Uses the UNCHANGED competition verifier code:

* ``dfthcsos.scoreinfra.reference``  (FCIDUMP, fixed shifts, NPZ loader)
* ``dfthcsos.scoreinfra.dfthc_math`` (evaluate_dfthc_angle_words)
* ``dfthcsos.scoreinfra.costs_prepare`` (SpinFreeData_V1)
* ``native_inputs`` and ``heuristic_costs`` and the gate constants, taken
  verbatim from ``dfthcsos/verify.py`` by AST extraction (verify.py itself
  cannot be imported on Windows because it imports kickmix).

Nothing here reimplements a metric. Numbers produced here are
``evaluate_words``-equivalent metrics and cost-model values, NOT verifier
results: the verifier also simulates the circuits (WSL only).
"""

from __future__ import annotations

import ast
import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(r"C:\Users\cld-main\work\vqcc-dfthcsos")
VERIFIERS = ROOT / "competition" / "verifiers"
VERIFY_PY = VERIFIERS / "dfthcsos" / "verify.py"
if str(VERIFIERS) not in sys.path:
    sys.path.insert(0, str(VERIFIERS))

from dfthcsos.scoreinfra import reference as _reference  # noqa: E402
from dfthcsos.scoreinfra.costs_prepare import SpinFreeData_V1  # noqa: E402
from dfthcsos.scoreinfra.dfthc_math import (  # noqa: E402
    evaluate_dfthc_angle_words,
    symmetric_from_lower,
)

N = _reference.ORBITALS
UPPER_ENERGY = _reference.UPPER_ENERGY

_WANTED_FUNCS = ("native_inputs", "heuristic_costs", "_floor_rejection_reasons", "passes_accuracy")
_WANTED_CONSTS = (
    "ERROR_2_THRESHOLD", "ERROR_1_THRESHOLD", "LAMBDA_FLOOR", "E_GAP_FLOOR", "QUBIT_CAP", "KEEP_BITS",
)


def _extract_from_verify() -> dict[str, Any]:
    src = VERIFY_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    ns: dict[str, Any] = {
        "np": np, "npt": npt, "Mapping": Mapping, "Any": Any,
        "symmetric_from_lower": symmetric_from_lower, "SpinFreeData_V1": SpinFreeData_V1,
    }
    found = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in _WANTED_CONSTS:
                exec(compile(ast.Module([node], []), str(VERIFY_PY), "exec"), ns)
                found.add(node.targets[0].id)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANTED_FUNCS:
            exec(compile(ast.Module([node], []), str(VERIFY_PY), "exec"), ns)
            found.add(node.name)
    missing = set(_WANTED_FUNCS + _WANTED_CONSTS) - found
    if missing:
        raise RuntimeError(f"verify.py no longer defines {sorted(missing)}")
    ns["verify_py_sha256"] = hashlib.sha256(VERIFY_PY.read_bytes()).hexdigest()
    return ns


_V = _extract_from_verify()
native_inputs = _V["native_inputs"]
heuristic_costs = _V["heuristic_costs"]
passes_accuracy = _V["passes_accuracy"]
ERROR_1_THRESHOLD = _V["ERROR_1_THRESHOLD"]
ERROR_2_THRESHOLD = _V["ERROR_2_THRESHOLD"]
LAMBDA_FLOOR = _V["LAMBDA_FLOOR"]
E_GAP_FLOOR = _V["E_GAP_FLOOR"]
QUBIT_CAP = _V["QUBIT_CAP"]
KEEP_BITS = _V["KEEP_BITS"]
VERIFY_PY_SHA256 = _V["verify_py_sha256"]

_REF_CACHE: dict[str, Any] = {}


def reference() -> dict[str, Any]:
    """The packaged FCIDUMP via the verifier's own checksum check and reader (cached)."""
    if "ref" not in _REF_CACHE:
        _REF_CACHE["ref"] = _reference.load_reference(_reference.check_fcidump())
    return _REF_CACHE["ref"]


def load_inputs(factorization: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Same steps as ``verify.load_inputs``: load NPZ, force fixed shifts, native (w, W, S, beta_1)."""
    params = _reference.load_factorization(factorization)
    params.update(_reference.load_fixed_shifts())
    w, W, S, beta_1 = native_inputs(params)
    return {"params": params, "w": w, "W": W, "S": S, "beta_1": beta_1}


def evaluate_words(inputs: Mapping[str, Any], angle_words, tree_edges, brot: int) -> dict[str, Any]:
    """Same call as ``verify.evaluate_words``."""
    return evaluate_dfthc_angle_words(
        angle_words, inputs["w"], inputs["W"], inputs["S"], inputs["beta_1"], reference(),
        brot=int(brot), tree_edges=np.asarray(tree_edges, dtype=np.int64), energy_upper=UPPER_ENERGY,
    )


def cost_model(R: int, B: int, C: int, brot: int, J: int,
               angles_toffoli: float | None = None, angles_temporary: int | None = None) -> dict[str, Any]:
    """``verify.heuristic_costs`` plus the J*brot word registers.

    With ``angles_toffoli`` / ``angles_temporary`` (e.g. from a verifier JSON or
    an estimate) it also returns T_total and Q_total as ``resource_costs`` forms them.
    """
    h = dict(heuristic_costs(N, R, B, C, brot))
    out = {"shape": (R, B, C), "brot": brot, "J": J, **h}
    out["persistent_with_words"] = h["persistent_qubits"] + J * brot
    if angles_toffoli is not None:
        out["T_total"] = float(angles_toffoli) + h["toffoli"]
    temp = h["temporary_qubits"] if angles_temporary is None else max(h["temporary_qubits"], int(angles_temporary))
    out["Q_total"] = out["persistent_with_words"] + temp
    return out


_TOTAL_NAME_CLASHES = ("toffoli", "persistent_qubits", "qubits", "temporary_qubits")


def check_resources_against_verifier(model: Mapping[str, Any], resources: Mapping[str, Any]) -> dict[str, Any]:
    """Compare ``cost_model(...)`` with a verifier ``resources`` block and assert agreement.

    ``heuristic_costs`` uses the names ``toffoli``, ``persistent_qubits``,
    ``qubits`` and ``temporary_qubits`` for the state-prep + Givens part
    only; ``verify.resource_costs`` uses the same names for the totals (and
    calls the state-prep part ``heuristic_*``). Same-name fields with the same
    meaning are compared directly. The clashing names are mapped explicitly:

        heuristic toffoli    + ANGLE Toffolis  == total toffoli
        heuristic persistent + J*brot          == total persistent_qubits
        heuristic qubits     + J*brot          == total qubits
        max(heuristic temporary, ANGLE temporary) == total temporary_qubits

    The third identity is only valid while the heuristic temporaries are at
    least the ANGLE temporaries (Q_total takes the max), so that precondition
    is asserted as well. The ``heuristic_*`` fields of the verifier must equal
    the model's state-prep values.
    """
    jbrot = int(model["J"]) * int(model["brot"])
    shared = sorted(k for k in resources if k in model)
    direct = [k for k in shared if k not in _TOTAL_NAME_CLASHES]
    direct_mismatch = [(k, model[k], resources[k]) for k in direct if model[k] != resources[k]]
    assert not direct_mismatch, f"same-meaning fields differ: {direct_mismatch}"

    aliases = {
        "heuristic_toffoli": "toffoli",
        "heuristic_persistent_qubits": "persistent_qubits",
        "heuristic_temporary_qubits": "temporary_qubits",
        "heuristic_qubits": "qubits",
    }
    alias_mismatch = [(v, k, model[k], resources[v]) for v, k in aliases.items() if model[k] != resources[v]]
    assert not alias_mismatch, f"verifier heuristic_* fields differ from the model: {alias_mismatch}"

    assert int(resources["angles_persistent_qubits"]) == jbrot, (
        f"angles_persistent_qubits {resources['angles_persistent_qubits']} != J*brot {jbrot}"
    )
    assert model["temporary_qubits"] >= resources["angles_temporary_qubits"], (
        "ANGLE temporaries exceed the state-prep temporaries; heuristic qubits + J*brot is not the total"
    )

    mapped = {
        "toffoli": (model["toffoli"], resources["angles_toffoli"], resources["toffoli"]),
        "persistent_qubits": (model["persistent_qubits"], jbrot, resources["persistent_qubits"]),
        "qubits": (model["qubits"], jbrot, resources["qubits"]),
    }
    assert model["toffoli"] + resources["angles_toffoli"] == resources["toffoli"], mapped["toffoli"]
    assert model["persistent_qubits"] + jbrot == resources["persistent_qubits"], mapped["persistent_qubits"]
    assert model["qubits"] + jbrot == resources["qubits"], mapped["qubits"]
    assert max(model["temporary_qubits"], resources["angles_temporary_qubits"]) == resources["temporary_qubits"]

    return {
        "n_shared_fields": len(shared),
        "direct_fields": direct,
        "differing_same_name_fields": [k for k in shared if model[k] != resources[k]],
        "mapped_heuristic_plus_term_equals_total": mapped,
        "temporary_qubits_agree_because": (
            f"max(heuristic {model['temporary_qubits']}, ANGLE {resources['angles_temporary_qubits']})"
            f" = {resources['temporary_qubits']}"
        ),
        "all_assertions_passed": True,
    }


def gate_report(m: Mapping[str, Any]) -> dict[str, Any]:
    """Margins against the verifier's gates (positive = inside the gate)."""
    return {
        "error_1_mHa": 1e3 * m["error_1"],
        "error_2_mHa": 1e3 * m["error_2"],
        "error_1_margin_mHa": 1e3 * (ERROR_1_THRESHOLD - m["error_1"]),
        "error_2_margin_mHa": 1e3 * (ERROR_2_THRESHOLD - m["error_2"]),
        "Lambda_margin": m["Lambda"] - LAMBDA_FLOOR,
        "E_gap_margin_mHa": 1e3 * (m["E_gap"] - E_GAP_FLOOR),
        "passes_accuracy": bool(passes_accuracy(m)),
    }


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
