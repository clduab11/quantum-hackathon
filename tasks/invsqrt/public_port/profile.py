"""Read-only allocation and gate profile of the regenerated port schedule.

Run with ``uv run --group gpu python -m tasks.invsqrt.public_port.profile``.
This refits the port's tables and constructs its raw circuit without changing
the schedule or emitting a candidate. Conditional costs assume fair HMR bits,
as in generate.resources; they are estimates, not verifier measurements.
"""
import inspect
import json
from collections import Counter, defaultdict
from unittest.mock import patch

import kickmix as km

from . import schedule
from .model import Config


class Profile:
    def __init__(self):
        self.builder = km.CircuitBuilder()
        self.live = {}
        self.depth = 0
        self.peak = 0
        self.main_allocations = 0
        self.groups = defaultdict(lambda: dict(toffoli=0, expected_toffoli=0., peak=0,
                                               registers={}))

    def __getattr__(self, name):
        method = getattr(self.builder, name)

        def call(*args, **kwargs):
            frame = inspect.currentframe().f_back
            frames = []
            while frame is not None:
                frames.append(frame)
                if frame.f_code is schedule.build.__code__:
                    break
                frame = frame.f_back
            stage = 'normalize'
            for caller in frames:
                fn = caller.f_code.co_name
                if fn in ('inner', 'outer'):
                    stage = fn + (' inverse' if caller.f_locals['inverse'] else ' forward')
                    break
                if fn == 'phase':
                    stage = 'phase high' if caller.f_locals['lowbit'] == caller.f_locals['c'].fy - 8 else 'phase low'
                    break
                if fn in ('load', 'erase', 'repair_anf', 'anf_lookup'):
                    stage = fn
                    break
            else:
                build = frames[-1].f_locals
                if 'bits' in build:
                    stage = 'unnormalize' if 'repairtable' in build else 'demolish'
                elif 'res' in build:
                    stage = 'allocate outputs'
            if name == 'alloc_qubits' and frames[0].f_code.co_name == 'build' and self.main_allocations >= 2:
                stage = 'allocate outputs'
            group = self.groups[stage]
            result = method(*args, **kwargs)
            if name in ('alloc_qubits', 'create_quantum_register'):
                fn = frames[0].f_code.co_name
                label = dict(phase='phase extension', folded_gadd='adder carry',
                             and_all_into='normalization ladder', phase_all='normalization repair',
                             visit='lookup ladder', walk='lookup ladder',
                             monomials='repair monomials', repair_anf='repair constant',
                             outer='virtual carry').get(fn, fn)
                if fn == 'build':
                    labels = ['x', 'flags', 'res', 'coarse', 'low', 'high']
                    label = labels[self.main_allocations]
                    self.main_allocations += 1
                elif fn == 'load':
                    label = 'c2' if len(result) == frames[0].f_locals['c'].w2 else 'step'
                self.live.update({str(q): label for q in result})
            count = len(self.live)
            if count > group['peak']:
                group['peak'] = count
                group['registers'] = dict(sorted(Counter(self.live.values()).items()))
            self.peak = max(self.peak, count)
            if name == 'free':
                values = [args[0]] if isinstance(args[0], (km.q, km.b)) else args[0]
                for q in values:
                    if isinstance(q, km.q):
                        del self.live[str(q)]
            if name in ('ccx', 'cswap', 'init_and'):
                if not all(isinstance(q, km.q) for q in args):
                    raise ValueError('Only scalar Toffoli operations are supported')
                group['toffoli'] += 1
                group['expected_toffoli'] += 2. ** -self.depth
            if name in ('left_rotate', 'right_rotate') and kwargs.get('control') is not None:
                # This schedule rotates by one position, emitting n-1 CSWAPs.
                assert args[1] == 1
                group['toffoli'] += len(args[0]) - 1
                group['expected_toffoli'] += (len(args[0]) - 1) * 2. ** -self.depth
            if name == 'push_condition':
                self.depth += 1
            elif name == 'pop_condition':
                self.depth -= 1
            del frames, frame
            return result

        return call


def profile(fitted):
    measured = Profile()
    tables = {(e, a): fitted['rows'][128*e+a] for e in range(2) for a in range(128)}
    with patch.object(km, 'CircuitBuilder', return_value=measured):
        circuit, split = schedule.build(Config(), tables, group_bits=None,
                                       interpolation=fitted['interpolation'],
                                       main_lookup='anf', affine=True, joint_norm=False)
    total = int(circuit.operation_statistics().num_toffoli_like)
    assert total == sum(g['toffoli'] for g in measured.groups.values())
    assert circuit.num_qubits == measured.peak
    return dict(groups=dict(measured.groups), peak=measured.peak,
                raw_toffoli=total, split=split)


if __name__ == '__main__':
    from .fit import fit_tables
    print(json.dumps(profile(fit_tables()), indent=2))
