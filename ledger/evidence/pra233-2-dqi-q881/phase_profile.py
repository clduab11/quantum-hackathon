"""Source rebuild with allocation observations and an enforced native cap.

The observed peak covers explicit Python allocation/free boundaries. Native
operations may use internal scratch; their total allocation is bounded by the
881-qubit cap enforced inside Kickmix. Byte identity checks instrumentation.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tasks.dqi.jfraction.common import build
from tasks.dqi.jfraction.decoder import PairedDecoder
from tasks.dqi.jfraction.mc4_inverse import builder_class


class AllocationProbe:
    def __init__(self, native):
        self.native = native
        self.peak = 0
        self.calls = 0
        native.set_max_qubits(881)

    def observe(self):
        self.peak = max(self.peak, self.native.num_allocated_qubits)

    def alloc_qubits(self, count):
        value = self.native.alloc_qubits(count)
        self.calls += 1
        self.observe()
        return value

    def create_quantum_register(self, *args, **kwargs):
        value = self.native.create_quantum_register(*args, **kwargs)
        self.observe()
        return value

    def free(self, value):
        self.observe()
        self.native.free(value)

    def __getattr__(self, name):
        return getattr(self.native, name)


class ProfileDecoder(PairedDecoder):
    @staticmethod
    def _record(builder, name):
        PairedDecoder._record(builder, name)
        probe = builder.native
        builder.stage_records[-1].update(
            observed_allocation_peak=probe.peak,
            native_allocation_upper_bound=881,
            explicit_allocation_calls=probe.calls)
        probe.peak = probe.native.num_allocated_qubits
        probe.calls = 0


builder = builder_class()()
builder.native = AllocationProbe(builder.native)
circuit = build(builder, decoder_type=ProfileDecoder)
output = Path(sys.argv[1])
circuit.to_file(output, format='kmb')
with output.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
expected = 'dec77920d4b9f5964b6cd52c947aa0c91468d56b7ed28cd475fdfc18d067729d'
assert digest == expected, (digest, expected)
print(json.dumps(dict(sha256=digest, byte_identical=True,
                     note=__doc__, phases=builder.stage_records), indent=2))
