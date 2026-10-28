# SPDX-License-Identifier: Apache-2.0
"""Build PRA-321 chemistry: the pinned (8, 143, 60) factor through the full-XOR J=5 compiler.

Example: python -m tasks.dfthcsos.b143 --data /home/cld-main/work/vqcc-data
  --out /tmp/pra321-build --dry-run
Requires NumPy, organizer Kickmix, and the declared factor under --data.
Writes only a new OUT/dfthcsos directory. Invalid inputs or an occupied output
fail nonzero. The factor is copied unchanged. Every circuit is regenerated from
the committed plan and schedule in full_xor/plans.json (no circuit, certificate
or .kmb is an input).
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil

import numpy as np

from tasks.dfthcsos.full_xor.emitter import build_staged
from tasks.dfthcsos.full_xor.planio import plan_from_dict
from tasks.dfthcsos.full_xor.validation import assert_independent
from tasks.dfthcsos.generate import DEFAULT_DATA, sha256_file

INPUT_PATH = Path('inputs/somejoint/qcc-our-chemistry-b143-c60-xor2-v1/submission.npz')
INPUT_SHA256 = 'aef36d39b83bbbf696e909884218f6c02f067baef14a29de1c41306bc1f6395b'
PLANS_PATH = Path(__file__).resolve().parent / 'full_xor' / 'plans.json'
BATCH_SIZE = 5
ADDRESSES = 1220
# Circuits the emitter must reproduce. These are checks, not inputs.
CIRCUIT_SHA256 = (
    'd0f7e6bf8057b171c22a0cbef041ccecf1334fb17e968fd924286ff70d66d08a',
    '468475d7214894af0616870bdce211799bc2e97682699c97f89d5afbc20824f8',
    'f31de4b7672f853cbecc21be77e30cb6e1ecc837a5d4680ffee77fe7d147bf14',
    '3b175fb0abaa7e20fe22d021c77cb27e16658fd088d6f78bf307286e50319736',
    '2990dbbf6177c166e32426803dd6f2a969659238b580a8500b9359cb12252ab2',
    'b4d36019132b43661850f984cf8eb723482cfb0af7eeb4cadb0964b6cc103e2a',
    '5c0bd4a2cd9436c925569a33044bac964653709b38a84d1df57e15bb2d60d6c6',
    'dead802918d2183ecb2d3c96d6ea1df5ba7e5240d3a20cf63dbfc8fa146bb05f',
    'd2e22516ab580482d755dca2f1f999cb2acb83cffda74df0ef1d7f0531fa3a73',
    '663497ad211daa8803a60e1cfff5d4e760499f971054c2908fe3a59489aa597c',
    '2aa48c950a5d0850ddd544886eb5720f4a92f0b7cf496f182f4b9b9a980a8de7',
    '78c041703bbc43f795ae4ab9224a15e2a6dc97d60c76cf9927226de6c959a466',
    'e43da6265070311362619ce8c57f780e41f519d0be0590049bba8c2c885c41fd',
    'fbdac0002c7cd3e66487f966ccac1edf2ac40f628fb7d22af048c1ce66f60219',
    '8b6d5738e981696154031d1f7c71b90fcde08ffd2fea1ae8525b545fd2c6c5c1',
)
SUBMISSION_SHA256 = 'c88f058efddd1b273a7161ebdb57740ff3da36452acf337995c19ff67951a414'


def load_plans():
    """The 15 committed plans. Raises if a record is not a replayable J=5 plan."""
    rows = json.loads(PLANS_PATH.read_text())
    if len(rows) != len(CIRCUIT_SHA256):
        raise ValueError(f'{len(rows)} plans but {len(CIRCUIT_SHA256)} circuit checks')
    return rows


def batch_deltas(words):
    """XOR of consecutive five-word batches. Batch 0 is the words themselves."""
    if words.shape != (ADDRESSES, 75):
        raise ValueError(f'angle_words shape {words.shape}, expected {(ADDRESSES, 75)}')
    batches = np.asarray(words, np.int64).reshape(ADDRESSES, 15, BATCH_SIZE)
    deltas = batches.copy()
    deltas[:, 1:] ^= batches[:, :-1]
    return deltas


def compile_batch(delta, row):
    """Emit one circuit from a committed plan and schedule. Raises unless it is exact."""
    if hashlib.sha256(np.ascontiguousarray(delta).tobytes()).hexdigest() != row['delta_sha256']:
        raise RuntimeError(f"batch {row['batch']} delta does not match the committed plan")
    plan = plan_from_dict(row['plan'])
    assert_independent(plan, delta)
    circuit, metadata = build_staged(plan, row['schedule'])
    stream = io.BytesIO()
    circuit.to_file(stream, format='kmb')
    blob = stream.getvalue()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != CIRCUIT_SHA256[row['batch']]:
        raise RuntimeError(f"angle_k_{row['batch']} sha256 {digest} is not the recorded circuit")
    if metadata['Q'] > 128:
        raise RuntimeError(f"angle_k_{row['batch']} uses {metadata['Q']} qubits")
    report = dict(batch=row['batch'], toffoli_per_call=metadata['T'], num_qubits=metadata['Q'],
                  sha256=digest, products=metadata['products'])
    return circuit, blob, report


def generate(out, *, data=DEFAULT_DATA, dry_run=False):
    source = Path(data) / INPUT_PATH
    if sha256_file(source) != INPUT_SHA256:
        raise ValueError('B143 factor SHA-256 mismatch; restore the declared input')
    destination = Path(out) / 'dfthcsos'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('output dfthcsos directory must be empty; use a fresh directory')
    with np.load(source, allow_pickle=False) as archive:
        words = np.asarray(archive['angle_words'])
        brot = int(archive['brot'])
        edges = archive['tree_edges']
        payload = {key: archive[key] for key in archive.files}
    if brot != 8:
        raise ValueError(f'brot {brot}, expected 8')
    deltas = batch_deltas(words)
    built = [compile_batch(deltas[:, k], row) for k, row in enumerate(load_plans())]
    from dfthcsos.scoreinfra.circuits import recover_words_from_circuits, submission_sha256
    circuits = [circuit for circuit, _, _ in built]
    recovered, _, _ = recover_words_from_circuits(
        circuits, num_vectors=len(words), num_angles=75, shots_per_address=1, seed=1901728)
    if not np.array_equal(recovered, words):
        raise RuntimeError('the circuits do not load the submitted angle words')
    digest = submission_sha256(circuits, payload, edges)
    if digest != SUBMISSION_SHA256:
        raise RuntimeError(f'submission digest {digest} is not {SUBMISSION_SHA256}')
    report = dict(input_sha256=INPUT_SHA256, brot=brot, batch_size=BATCH_SIZE,
                  submission_sha256=digest, circuits=[row for _, _, row in built], dry_run=dry_run)
    if dry_run:
        return report
    destination.mkdir(parents=True, exist_ok=True)
    factor = destination / 'submission.npz'
    shutil.copyfile(source, factor)
    paths = [factor]
    for _, blob, row in built:
        path = destination / f"angle_k_{row['batch']}.kmb"
        path.write_bytes(blob)
        paths.append(path)
    report['files'] = {str(path.relative_to(out)): dict(sha256=sha256_file(path), size=path.stat().st_size)
                       for path in paths}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--dry-run', action='store_true', help='Validate and compile without writing files.')
    args = parser.parse_args()
    print(json.dumps(generate(args.out, data=args.data, dry_run=args.dry_run), indent=2))


if __name__ == '__main__':
    main()
