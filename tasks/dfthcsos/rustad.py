# SPDX-License-Identifier: Apache-2.0
"""Build PRA-280 chemistry from the pinned rustad v1 non-circuit input.

Example: python -m tasks.dfthcsos.rustad --data /home/cld-main/work/vqcc-data
  --out /tmp/pra280-build --dry-run
Requires NumPy, organizer Kickmix, and the declared factor under --data.
Writes only a new OUT/dfthcsos directory. Invalid inputs or an occupied output
fail nonzero. The factor is copied unchanged; every circuit is generated.
"""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from tasks.dfthcsos.generate import DEFAULT_DATA, batch_deltas, sha256_file, write_family
from tasks.dfthcsos.paired_qrom import build_qrom
from tasks.dfthcsos.projective_gauge import signed_gauge

INPUT_PATH = Path('inputs/rustad/dfthc_r10_b129_c60_brot8.npz')
INPUT_SHA256 = '27dda66f38c60821665cfc74e51d1bd2bfd2a7f0d902dbaffcdc5b26543dadad'


def generate(out, *, data=DEFAULT_DATA, dry_run=False):
    source = Path(data) / INPUT_PATH
    if sha256_file(source) != INPUT_SHA256:
        raise ValueError('rustad v1 SHA-256 mismatch; restore the declared input')
    destination = Path(out) / 'dfthcsos'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('output dfthcsos directory must be empty; use a fresh directory')
    with np.load(source, allow_pickle=False) as archive:
        words, _ = signed_gauge(archive['angle_words'], archive['tree_edges'], 8)
    built = [build_qrom(delta, 8) for delta in batch_deltas(words, 3)]
    report = dict(input_sha256=INPUT_SHA256, brot=8, batch_size=3,
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
