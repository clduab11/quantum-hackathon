"""Drop one invsqrt rotation when every x keeps a positive margin.

This file is our scipy linprog calibrator. The slack-maximising drop is
credited to LightningV08 and to Mizero Lucky Gall. Mizero v1 has no
notebook-wide licence grant and is reference-only: it is not loaded, and it
is not a shipping parent. This file is not a port of that notebook.

The linear program maximises the worst slack. Rounding is then checked in
integers on all 3,133,452 inputs. No verifier salt, calibration file, or
circuit binary is an input.

The activation bits and the starting phase come from the affine compiler.
Only unconditioned, exactly representable Z_POW gates are moved. Clifford
Z_POW gates stay fixed.
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
from scipy.optimize import linprog

from tasks.invsqrt.peephole import optimize

MAX_X = 3_133_452
UNIT = 1 << 64
HALF = UNIT // 2
REFERENCE_COST = 2_076_774.233715282


def reference_target_tolerance(xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Official invsqrt target and tolerance for beta = 1, precision 24.

    `r = isqrt(floor(2^130 / x))`, target is `r` rounded at bit 0, tolerance
    is `min(r >> 25, 2^63)`.
    """
    roots = [math.isqrt((1 << 130) // int(x)) for x in xs.tolist()]
    target = np.array([((root + 1) >> 1) & (UNIT - 1) for root in roots], dtype=np.uint64)
    tolerance = np.array([min(root >> 25, 1 << 63) for root in roots], dtype=np.uint64)
    return target, tolerance


def model_phase(cfg, tables) -> np.ndarray:
    """Integer-model phase in units of 2^-64 turns, for every x."""
    from tasks.invsqrt.signed_digit import integer_model

    xs = np.arange(1, MAX_X + 1, dtype=np.int64)
    shift = np.uint64(64 - (cfg.fy + 10))
    phase = np.empty(MAX_X, dtype=np.uint64)
    for start in range(0, MAX_X, 131072):
        block = xs[start : start + 131072]
        values = integer_model(block, cfg, tables).astype(np.uint64)
        phase[start : start + len(block)] = values << shift
    return phase


def assert_phase_matches(compiled, cfg, tables) -> dict:
    """Require the compiled unconditional phase to equal the integer model."""
    expected = model_phase(cfg, tables)
    mismatch = np.flatnonzero(compiled.phase != expected)
    if len(mismatch):
        index = int(mismatch[0])
        raise RuntimeError(
            "Compiled phase does not match the integer model at "
            f"x={index + 1}: circuit {int(compiled.phase[index])} "
            f"model {int(expected[index])} mismatches {len(mismatch)}"
        )
    return {"phase_match": True, "inputs": MAX_X}


def _matvec(bits: np.ndarray, columns: list[int], delta: np.ndarray) -> np.ndarray:
    acc = np.zeros(bits.shape[0], dtype=np.float64)
    for index, column in enumerate(columns):
        if delta[index] == 0:
            continue
        acc += bits[:, column] * float(delta[index])
    return acc


def _fit(error, tolerance, bits, free, fixed, bound_units, scale=2.0**28):
    """Maximise slack with cutting planes. `fixed` is the dropped-rotation shift."""
    residual = (error.astype(np.float64) + fixed) / scale
    limit = tolerance.astype(np.float64) / scale
    width = len(free)
    active = set(np.linspace(0, MAX_X - 1, 4096, dtype=np.int64).tolist())
    initial = limit - np.abs(residual)
    active.update(np.argpartition(initial, 4095)[:4096].tolist())
    delta = np.zeros(width, dtype=np.float64)
    margin = 0.0
    converged = False
    iterations = 0
    for iterations in range(1, 61):
        chosen = np.fromiter(sorted(active), dtype=np.int64)
        block = bits[chosen][:, free].astype(np.float64)
        matrix = np.vstack(
            [np.c_[block, np.ones(len(chosen))], np.c_[-block, np.ones(len(chosen))]]
        )
        rhs = np.r_[limit[chosen] - residual[chosen], limit[chosen] + residual[chosen]]
        bounds = [(-bound_units / scale, bound_units / scale)] * width + [(None, None)]
        result = linprog(
            np.r_[np.zeros(width), -1.0],
            A_ub=matrix,
            b_ub=rhs,
            bounds=bounds,
            method="highs",
        )
        if not result.success:
            raise RuntimeError(result.message)
        delta, margin = result.x[:width], float(result.x[width])
        corrected = residual + _matvec(bits, free, delta)
        slack = limit - np.abs(corrected)
        actual = float(slack.min())
        print(
            f"calibration LP {iterations}: rows {len(chosen)} "
            f"lp {margin * scale:.3f} exhaustive {actual * scale:.3f}",
            flush=True,
        )
        if actual >= margin - 1e-9 * max(1.0, abs(margin)):
            converged = True
            break
        added = set(np.argpartition(slack, 399)[:400].tolist())
        if added.issubset(active):
            break
        active.update(added)
    return np.rint(delta * scale).astype(np.int64), {
        "iterations": iterations,
        "lp_converged": converged,
        "active_inputs": len(active),
    }


def _exact_margin(error, tolerance, bits, deltas) -> tuple[int, int]:
    shift = np.zeros(MAX_X, dtype=np.int64)
    for index, delta in enumerate(deltas):
        if int(delta) == 0:
            continue
        shift += bits[:, index].astype(np.int64) * np.int64(delta)
    largest = max(abs(int(error.min())), abs(int(error.max())))
    if largest + sum(abs(int(delta)) for delta in deltas) >= HALF:
        raise RuntimeError("Rounded correction can overflow signed 64-bit phase")
    corrected = error.astype(np.int64) + shift
    slack = tolerance.astype(np.int64) - np.abs(corrected)
    worst = int(np.argmin(slack))
    return int(slack[worst]), worst


def _angle_key(theta: Fraction) -> float:
    reduced = theta % 2
    return abs(float(min(reduced, 2 - reduced)))


def _estimate(qubits, expected_toffoli, t_like, rotations, margin) -> dict:
    if rotations <= 0 or margin <= 0:
        return {"estimated_expected_cost": math.inf, "ratio": 0.0, "per_rotation_t": None}
    epsilon = math.pi * (margin / UNIT) / rotations
    per_rotation = 0.56 * math.log2(1 / epsilon) + 5.3
    extra = (t_like + rotations * per_rotation) / 4
    cost = qubits * (expected_toffoli + extra)
    return {
        "estimated_expected_cost": cost,
        "ratio": REFERENCE_COST / cost,
        "per_rotation_t": per_rotation,
        "epsilon": epsilon,
    }


def _rewrite(lines: list[str], rotations: list[dict], deltas: dict[int, int], dropped: set[int]) -> str:
    from decimal import Decimal, localcontext

    def exponent_text(theta: Fraction) -> str:
        with localcontext() as ctx:
            ctx.prec = 80
            rendered = format(Decimal(theta.numerator) / Decimal(theta.denominator), "f")
        if "." not in rendered:
            rendered += ".0"
        return rendered

    remove = set()
    out = list(lines)
    for index, rotation in enumerate(rotations):
        if index in dropped:
            remove.add(rotation["line"])
            continue
        delta = int(deltas.get(index, 0))
        if delta == 0:
            continue
        theta = rotation["theta"] + Fraction(delta, HALF)
        qubit = lines[rotation["line"]].split()[1]
        out[rotation["line"]] = f"Z_POW {qubit} {exponent_text(theta)}"
    body = "\n".join(line for index, line in enumerate(out) if index not in remove and line)
    return body + "\n"


def calibrate(compiled, resources: dict) -> dict:
    """Try the original angles and each single counted drop. Keep the cheapest legal one."""
    rotations = compiled.rotations
    counted = [index for index, rotation in enumerate(rotations) if rotation["counted"]]
    if not counted:
        raise RuntimeError("The compiled circuit has no counted rotation")
    bits = np.column_stack([rotation["bits"] for rotation in rotations])
    xs = np.arange(1, MAX_X + 1, dtype=np.int64)
    _target, tolerance = reference_target_tolerance(xs)
    # Reuse the packed target. reference_target_tolerance already walked every x.
    target = _target
    error = (compiled.phase - target).view(np.int64)
    order = sorted(counted, key=lambda index: _angle_key(rotations[index]["theta"]))
    # The public build drops one rotation. Try the original and the smallest
    # angle first. Search the other single drops only when that drop has no margin.
    candidates = [(), (order[0],)]
    best = None
    trials = []
    expanded = False
    for dropped in candidates:
        fixed = np.zeros(MAX_X, dtype=np.float64)
        bound = float(1 << 36)
        for index in dropped:
            units = rotations[index]["units"]
            fixed += bits[:, index] * float(-units)
            bound = max(bound, 4.0 * abs(units))
        free = [index for index in counted if index not in dropped]
        rounded, fit_report = _fit(error, tolerance, bits, free, fixed, bound)
        deltas = np.zeros(len(rotations), dtype=np.int64)
        for column, index in enumerate(free):
            deltas[index] = rounded[column]
        for index in dropped:
            deltas[index] = -int(rotations[index]["units"])
        margin, worst = _exact_margin(error, tolerance, bits, deltas)
        kept = len(counted) - len(dropped)
        estimate = _estimate(
            resources["qubits"],
            resources["expected_toffoli"],
            resources["t_like"],
            kept,
            margin,
        )
        trial = {
            "dropped": [int(index) for index in dropped],
            "margin_units": margin,
            "worst_index": worst,
            "rotations": kept,
            "fit": fit_report,
            **estimate,
        }
        trials.append({key: trial[key] for key in ("dropped", "margin_units", "rotations", "ratio")})
        print(
            f"calibration drop {list(dropped) or 'none'}: margin {margin} "
            f"rotations {kept} ratio {estimate['ratio']:.6f}",
            flush=True,
        )
        if margin <= 0:
            if dropped == (order[0],) and not expanded:
                expanded = True
                candidates.extend((index,) for index in order[1:])
            continue
        if best is None or estimate["estimated_expected_cost"] < best["estimate"]["estimated_expected_cost"]:
            best = {"deltas": deltas, "dropped": set(dropped), "trial": trial, "estimate": estimate}
    if best is None:
        raise RuntimeError(f"No calibration kept a positive margin: {trials}")
    lines = compiled.text.splitlines()
    rewritten = _rewrite(
        lines,
        rotations,
        {index: int(best["deltas"][index]) for index in range(len(rotations))},
        best["dropped"],
    )
    peepholed, cancelled = optimize(rewritten)
    return {
        "text": peepholed,
        "margin_units": best["trial"]["margin_units"],
        "worst_x": int(best["trial"]["worst_index"]) + 1,
        "rotations": best["trial"]["rotations"],
        "dropped_rotation_indexes": best["trial"]["dropped"],
        "peephole_cancelled": cancelled,
        "estimate": best["estimate"],
        "trials": trials,
    }
