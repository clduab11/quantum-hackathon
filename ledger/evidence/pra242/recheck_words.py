"""Re-evaluate the six hash-pinned own-generated v3 diagnostic archives.

Run from this repo with --starter, --competition and --data-root pointing to
the same inputs used in FIT_V3.md. Requires completed pra242-r6-v3 and
pra242-thc-v3 directories. Writes nothing. Nonzero exit means a hash or metric
mismatch: restore the recorded inputs/outputs before trusting the evidence.
"""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ['OPENBLAS_NUM_THREADS'] = '2'
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import numpy as np
from tasks.dfthcsos.factor_support import checked_inputs, sha256

parser = argparse.ArgumentParser(description=__doc__)
for name in ('starter', 'competition', 'data-root'):
    parser.add_argument('--'+name, type=Path, required=True)
args = parser.parse_args()
pins = checked_inputs(args.starter)
for item in pins['competition_files']:
    if sha256(args.competition/item['path']) != item['sha256']:
        raise ValueError('Competition hash mismatch; restore pinned package')
sys.path[:0] = [str(args.competition/'kickmix'), str(args.competition/'verifiers')]
from dfthcsos.verify import load_inputs, evaluate_words

checked = []
for name in ('r6', 'thc'):
    report = json.loads((Path(__file__).parent/f'{name}-report.json').read_text())
    for row in report['rows']:
        path = args.data_root/f'pra242-{name}-v3'/row['file']
        if sha256(path) != row['sha256']:
            raise ValueError(f'Factor hash mismatch: {path.name}; restore recorded own-generated file')
        with np.load(path, allow_pickle=False) as z:
            words, edges, bits = z['angle_words'], z['tree_edges'], int(z['brot'])
        metrics = evaluate_words(load_inputs(path), words, edges, bits)
        difference = max(abs(metrics[k]-row[k]) for k in
                         ('error_1', 'error_2', 'Lambda', 'E_gap', 'lambda_eff'))
        if not np.isfinite(difference) or difference > 1e-10:
            raise ValueError(f'Evaluator mismatch for {name}/{row["file"]}: {difference}')
        checked.append(dict(run=name, bits=bits, max_metric_difference=difference,
                            sha256=row['sha256']))
print(json.dumps(dict(status='PASS', checked=checked), indent=2))
