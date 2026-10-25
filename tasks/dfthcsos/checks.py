"""Fast dfthcsos checks against the packaged verifier.

G2 uses ``angle_words`` (an extra key the verifier ignores) plus
``heuristic_costs``. It does not simulate the ANGLE circuits. Full simulation
is the verifier log, not this proxy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Same floors as verifiers/dfthcsos/verify.py. The proxy also calls that module.
ERROR_HA = 0.020
LAMBDA_FLOOR = 49.0
E_GAP_FLOOR = 3.914898


def acceptance_problems(metrics: dict) -> list[str]:
    """Reasons the accuracy gates would reject ``metrics``. Empty means they pass."""
    problems = []
    error_1 = float(metrics["error_1"])
    error_2 = float(metrics["error_2"])
    lambda_value = float(metrics["Lambda"])
    e_gap = float(metrics["E_gap"])
    if not error_1 <= ERROR_HA:
        problems.append(f"error_1 {error_1} Ha > {ERROR_HA} Ha")
    if not error_2 <= ERROR_HA:
        problems.append(f"error_2 {error_2} Ha > {ERROR_HA} Ha")
    if not lambda_value > LAMBDA_FLOOR:
        problems.append(f"Lambda {lambda_value} <= {LAMBDA_FLOOR}")
    if not e_gap > E_GAP_FLOOR:
        problems.append(f"E_gap {e_gap} <= {E_GAP_FLOOR}")
    if not metrics.get("gap_in_domain", True):
        problems.append("E_gap is outside (0, 2*Lambda)")
    return problems


def _chemistry_dir(submission_dir: Path) -> Path:
    direct = submission_dir / "submission.npz"
    nested = submission_dir / "dfthcsos" / "submission.npz"
    if nested.is_file():
        return nested.parent
    if direct.is_file():
        return submission_dir
    raise FileNotFoundError(f"no submission.npz under {submission_dir}")


def proxy_submission(submission_dir: Path) -> dict:
    """Heuristic cost plus the Hamiltonian-error, Lambda and E_gap gates."""
    from dfthcsos.verify import evaluate_words, heuristic_costs, load_inputs, load_tree_edges

    chemistry = _chemistry_dir(Path(submission_dir))
    npz_path = chemistry / "submission.npz"
    inputs = load_inputs(npz_path)
    edges = load_tree_edges(npz_path, chemistry)
    with np.load(npz_path, allow_pickle=False) as archive:
        if "angle_words" not in archive.files:
            return {"status": "FAIL: submission.npz has no angle_words; G2 cannot check the Hamiltonian error without simulation"}
        words = np.array(archive["angle_words"])
        # Width is a scale, not inferable from the largest word. Legacy inputs
        # are the 12-bit reference; a precision sweep must declare its width.
        width = np.asarray(archive['brot']) if 'brot' in archive.files else np.array(12)
    if width.shape != () or not np.issubdtype(width.dtype, np.integer) or not 1 <= int(width) <= 63:
        raise ValueError('brot must be an integer scalar in [1, 63]')
    brot = int(width)
    if not np.issubdtype(words.dtype, np.integer) or np.any(words < 0) or np.any(words >= (1 << brot)):
        raise ValueError('angle_words must be integers in [0, 2**brot)')
    metrics = evaluate_words(inputs, words, edges, brot)
    rank_r, bases_b, ensemble_c = inputs.w.shape
    heuristic = heuristic_costs(inputs.num_orbitals, rank_r, bases_b, ensemble_c, brot)
    problems = acceptance_problems(metrics)
    payload = {
        "error_1": float(metrics["error_1"]),
        "error_2": float(metrics["error_2"]),
        "Lambda": float(metrics["Lambda"]),
        "E_gap": float(metrics["E_gap"]),
        "lambda_eff": float(metrics["lambda_eff"]),
        "heuristic_toffoli": int(heuristic["toffoli"]),
        "heuristic_qubits": int(heuristic["qubits"]),
        "brot": brot,
        "parity": False,
    }
    if problems:
        return {"status": "FAIL: " + "; ".join(problems), **payload}
    return {"status": "PASS", **payload}
