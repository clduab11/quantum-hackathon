# SPDX-License-Identifier: Apache-2.0
"""PRA-197 allocation experiment; the default generator stays unchanged.

Run from the repository root:
  uv run python ledger/evidence/pra197-compact64/allocation_probe.py OUT [64]

Without 64, instrument the shipped schedule and check its artifact hash.
With 64, use the existing compact quotient from BM round 64 onward.
OUT receives dqi.kmb and profile.json. Neither output is a submission.
"""
import sys, json, tempfile, time, hashlib
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from tasks.dqi import generate as G
G._port_modules()
import symbolic_runtime as S
Original = S.SymbolicBuilder
class Profiled(Original):
    latest = None
    def __init__(self):
        super().__init__()
        self.native_profile = {}
        Profiled.latest = self
    def wire(self, q):
        fresh = self.physical[q] is None
        wire = super().wire(q)
        if fresh:
            phase = self.current_phase or self.phase_name
            count = self.k.num_allocated_qubits
            old = self.native_profile.get(phase, {}).get('peak', 0)
            if count > old:
                owners = {}
                for i,p in enumerate(self.physical):
                    if p is not None:
                        name = self.owners.get(i, 'unclaimed')
                        owners[name] = owners.get(name, 0) + 1
                self.native_profile[phase] = {'peak': count, 'allocation_id_at_peak': wire.id, 'owners': owners}
        return wire
S.SymbolicBuilder = Profiled
if len(sys.argv) > 2:
    compact_from = int(sys.argv[2])
    install_sweep = G._install_sweep
    def install_experiment(port, symbolic):
        from contextlib import contextmanager
        import round2_gadgets as gadgets
        install_sweep(port, symbolic)
        original_quotient = port.BM.quotient
        @contextmanager
        def quotient(self, ctl, bb_l):
            if self.A.round >= compact_from:
                with gadgets.compact_quotient(port, self, ctl, bb_l) as q:
                    yield q
            else:
                with original_quotient(self, ctl, bb_l) as q:
                    yield q
        port.BM.quotient = quotient
    G._install_sweep = install_experiment
out = Path(sys.argv[1]);out.mkdir(parents=True, exist_ok=True)
start = time.monotonic()
with tempfile.TemporaryDirectory(prefix='pra197-profile-') as tmp:
    circuit, report = G.build_decoder(Path(tmp))
report['compact_from'] = int(sys.argv[2]) if len(sys.argv) > 2 else 70
report['phases'] = Profiled.latest.native_profile
report['elapsed_seconds'] = time.monotonic() - start
circuit.to_file(out/'dqi.kmb', format='kmb')
with (out/'dqi.kmb').open('rb') as f:
    report['sha256'] = hashlib.file_digest(f, 'sha256').hexdigest()
report['size_bytes'] = (out/'dqi.kmb').stat().st_size
(out/'profile.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='phases'}))
print(json.dumps(sorted(report['phases'].items(), key=lambda kv:kv[1]['peak'], reverse=True)[:6]))
