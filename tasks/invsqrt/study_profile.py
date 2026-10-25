"""Profile allocations and scalar Toffolis in the unchanged PRA-200 schedule.

Run with ``uv run python -m tasks.invsqrt.study_profile``. This constructs the
baseline; it does not simulate, emit a candidate, or run a verifier. Counts are
before affine compilation and rotation calibration. Classical bits are excluded.
"""

from __future__ import annotations

from collections import defaultdict
import inspect
import json
from unittest.mock import patch

import kickmix as km

from tasks.invsqrt import schedule90, signed_digit as sd

STAGES = {
    "normalize", "unnormalize", "init_anf", "phase_from_records",
    "restore_boolean", "inner", "outer", "phase",
}


class Profile:
    def __init__(self):
        self.builder = km.CircuitBuilder()
        self.live = set()
        self.peak = 0
        self.groups = defaultdict(lambda: dict(toffoli=0, peak=0, rotations=0))

    def __getattr__(self, name):
        method = getattr(self.builder, name)

        def call(*args, **kwargs):
            frame = inspect.currentframe().f_back
            tag = "other"
            while frame is not None:
                function = frame.f_code.co_name
                if function in STAGES:
                    tag = function
                    if function in ("inner", "outer"):
                        tag += " inverse" if frame.f_locals["inverse"] else " forward"
                    if function == "phase":
                        tag += " high" if frame.f_locals["low_bit"] == 20 else " low"
                    break
                frame = frame.f_back
            del frame
            group = self.groups[tag]
            result = method(*args, **kwargs)
            if name in ("alloc_qubits", "create_quantum_register"):
                self.live.update(map(str, result))
            if name == "free":
                values = [args[0]] if isinstance(args[0], (km.q, km.b)) else list(args[0])
                self.live.difference_update(str(q) for q in values if isinstance(q, km.q))
            group["peak"] = max(group["peak"], len(self.live))
            self.peak = max(self.peak, len(self.live))
            if name in ("ccx", "cswap", "init_and"):
                if not all(isinstance(q, km.q) for q in args):
                    raise ValueError("Profile only supports scalar Toffoli operations")
                group["toffoli"] += 1
            if name == "z_pow":
                group["rotations"] += 1
            return result

        return call


def profile():
    measured = Profile()
    cfg, tables, _ = sd.load_or_build_tables()
    with patch.object(km, "CircuitBuilder", return_value=measured):
        circuit, schedule = schedule90.build_raw(cfg, tables)
    total = int(circuit.operation_statistics().num_toffoli_like)
    assert total == sum(group["toffoli"] for group in measured.groups.values())
    assert circuit.num_qubits == measured.peak
    return dict(groups=dict(measured.groups), peak=measured.peak,
                schedule=schedule, raw_toffoli=total)


if __name__ == "__main__":
    print(json.dumps(profile(), indent=2, sort_keys=True))
