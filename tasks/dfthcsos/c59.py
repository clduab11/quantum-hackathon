# SPDX-License-Identifier: Apache-2.0
"""Build PRA-294 chemistry: the pinned C59 factor through the exact J=4 streamed compiler.

Example: python -m tasks.dfthcsos.c59 --data /home/cld-main/work/vqcc-data
  --out /tmp/pra294-build --dry-run
Requires NumPy, organizer Kickmix, and the declared factor under --data.
Writes only a new OUT/dfthcsos directory. Invalid inputs or an occupied output
fail nonzero. The factor is copied unchanged; every circuit is generated from
the plan parameters below (no certificate or circuit is an input).
"""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from tasks.dfthcsos.generate import DEFAULT_DATA, batch_deltas, sha256_file, write_family
from tasks.dfthcsos.kernel_plan import plan_balanced, plan_tensor
from tasks.dfthcsos.paired_algebra import coefficients
from tasks.dfthcsos.projective_gauge import signed_gauge
from tasks.dfthcsos.streamed_qrom import STAGES, build_streamed

INPUT_PATH = Path('inputs/mrmeows/qcc-1375-v8-C59-submission.npz')
INPUT_SHA256 = '8229861b3ee22316e144c900737dfc54f7a30ea88de77ff5391f3375d050fa87'
BATCH_SIZE = 4
# mrmeows v8 cost-first-shape-screen plan parameters, one first-stage seed per circuit.
FIRST_STAGE = dict(group_size=3, nrelations=38, plane_mode='pairs', trials=16)
FIRST_STAGE_SEEDS = (1, 4, 0, 0, 0, 0, 3, 2, 0, 2, 6, 2, 0, 1, 2, 3, 2, 0, 1)
SECOND_STAGE = dict(group_size=4, nrelations=12, seed=0, plane_mode='original', trials=24)


def compile_batch(delta, seed):
    """Plan both stages for one batch and emit the circuit; raises if planning is not exact."""
    ac = coefficients(delta, 8, 4)
    left, _ = plan_balanced(ac[1:, STAGES[0][0]:STAGES[0][-1] + 1, :], seed=seed, **FIRST_STAGE)
    right, _ = plan_tensor(ac[1:, STAGES[1][0]:STAGES[1][-1] + 1, :], **SECOND_STAGE)
    if left is None or right is None:
        raise RuntimeError('exact J=4 planning failed')
    return build_streamed(delta, ac, [left, right])


def generate(out, *, data=DEFAULT_DATA, dry_run=False):
    source = Path(data) / INPUT_PATH
    if sha256_file(source) != INPUT_SHA256:
        raise ValueError('C59 factor SHA-256 mismatch; restore the declared input')
    destination = Path(out) / 'dfthcsos'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('output dfthcsos directory must be empty; use a fresh directory')
    with np.load(source, allow_pickle=False) as archive:
        words, _ = signed_gauge(archive['angle_words'], archive['tree_edges'], 8)
    deltas = batch_deltas(words, BATCH_SIZE)
    if len(deltas) != len(FIRST_STAGE_SEEDS):
        raise ValueError(f'{len(deltas)} batches but {len(FIRST_STAGE_SEEDS)} plan seeds')
    built = [compile_batch(delta, seed) for delta, seed in zip(deltas, FIRST_STAGE_SEEDS)]
    report = dict(input_sha256=INPUT_SHA256, brot=8, batch_size=BATCH_SIZE,
                  circuits=[r for _, r in built], dry_run=dry_run)
    if dry_run:
        return report
    destination.mkdir(parents=True, exist_ok=True)
    factor = destination / 'submission.npz'
    shutil.copyfile(source, factor)
    paths = [factor, *write_family([c for c, _ in built], destination)]
    report['files'] = {str(p.relative_to(out)): dict(sha256=sha256_file(p), size=p.stat().st_size)
                       for p in paths}
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
