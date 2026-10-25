# SPDX-License-Identifier: Apache-2.0
"""Circuit-aware G2 model for PRA-232; factor-only proxy remains independent."""
from pathlib import Path
import numpy as np
from tasks.dfthcsos.checks import _chemistry_dir, acceptance_problems

def proxy_circuits(submission_dir: Path) -> dict:
    """Heuristic cost plus the Hamiltonian-error, Lambda and E_gap gates."""
    from dfthcsos.verify import evaluate_words, heuristic_costs, load_inputs, load_tree_edges, resource_costs
    from dfthcsos.scoreinfra.circuits import load_circuits, register_layout

    chemistry = _chemistry_dir(Path(submission_dir))
    npz_path = chemistry / "submission.npz"
    inputs = load_inputs(npz_path)
    edges = load_tree_edges(npz_path, chemistry)
    with np.load(npz_path, allow_pickle=False) as archive:
        if "angle_words" not in archive.files:
            return {"status": "FAIL: submission.npz has no angle_words; G2 cannot check the Hamiltonian error without simulation"}
        words = np.array(archive["angle_words"])
    circuits = load_circuits(chemistry)
    brot = register_layout(circuits).brot
    if np.any(words < 0) or np.any(words >= 1 << brot):
        return {"status": "FAIL: angle_words do not fit circuit precision"}
    metrics = evaluate_words(inputs, words, edges, brot)
    rank_r, bases_b, ensemble_c = inputs.w.shape
    heuristic = heuristic_costs(inputs.num_orbitals, rank_r, bases_b, ensemble_c, brot)
    # Static counts are an upper bound when gates are conditional. They are exact
    # for PRA-232, whose measurement-conditioned corrections are Clifford only.
    angle_t = 2 * sum(int(c.operation_statistics().num_toffoli_like) for c in circuits)
    resources = resource_costs(inputs, circuits, brot, angle_t)
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
        "estimated_toffoli": resources["toffoli"],
        "estimated_qubits": resources["qubits"],
        "estimated_cost": float(metrics["lambda_eff"]) * resources["toffoli"] * resources["qubits"],
        "resources": resources,
    }
    if not resources["angles_within_cap"]:
        problems.append("ANGLE circuit exceeds 128 qubits")
    if problems:
        return {"status": "FAIL: " + "; ".join(problems), **payload}
    return {"status": "PASS", **payload}
