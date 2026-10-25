"""Reproduce the first fixed-rounded-U probe from the hash-checked own short refit.

Run from the repository root with `uv run python ledger/evidence/pra235/run_quantized_probe.py`.
Requires the PRA-235 deterministic rerun at the explicit path below; writes a new
probe directory and refuses overwrite. Exits 3 for a 19 mHa miss, 0 for a pass.
"""
from tasks.dfthcsos import factor_pipeline
from tasks.dfthcsos.factor_support import checked_inputs, sha256, write_npz, json_text, prediction
from tasks.dfthcsos.factor_math import packed_target
from tasks.dfthcsos.factor_quantized import refit_quantized
from tasks.dfthcsos.factor_offsets import refine_offsets
from tasks.dfthcsos.checks import acceptance_problems
from pathlib import Path
from dataclasses import replace
import numpy as np
import sys
import time

starter = Path('/home/cld-main/work/vqcc-data/starter-kit')
competition = Path('/home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation')
checkpoint = Path('/home/cld-main/work/vqcc-data/pra235-determinism-01/factors-01.npz')
out = Path('/home/cld-main/work/vqcc-data/pra235-quantized-probe-01')
pins = checked_inputs(starter)
for entry in pins['competition_files']:
    assert sha256(competition/entry['path']) == entry['sha256'], entry['path']
assert sha256(checkpoint) == 'cc7dd377b1c98c1267caac98e64835b516016e4be97392cff791f96fc219a297'
out.mkdir()
sys.path[:0] = [str(competition/'kickmix'), str(competition/'verifiers'), str(starter/'starter_kit')]
from dfthcsos.verify import load_inputs, native_inputs, evaluate_words, heuristic_costs
from verifier.score import SubmissionInputs as EncoderInputs
from starter.task2_angles.encode import encode_inputs, angles_to_words, words_to_vectors
from starter.task2_angles.trees import tree_angles, log_depth_tree_edges

start = time.monotonic()
with np.load(checkpoint, allow_pickle=False) as archive:
    params = {k:archive[k] for k in archive.files}
inputs = load_inputs(params)
target = packed_target(inputs.ref['tei'], inputs.S)
edges = log_depth_tree_edges(76)
def quantize(u):
    words = angles_to_words(tree_angles(u.reshape(-1, 76), edges), 12)
    return words_to_vectors(words, edges, 12).reshape(u.shape)
params, fit = refit_quantized(params, target, 100, 2e-5, quantize, maxcor=20)
params, offsets = refine_offsets(params, inputs, 100)
write_npz(out/'factors.npz', params)
w, off, shift, beta = native_inputs(params)
point = replace(inputs, params=params, w=w, W=off, S=shift, beta_1=beta)
encoder = EncoderInputs('FeMoCo76o113e', None, params, inputs.ref, w, off, shift, beta, inputs.energy_upper)
rows = []
for bits in (12, 11, 10, 9, 8):
    words = encode_inputs(encoder, edges, bits)
    metrics = evaluate_words(point, words, edges, bits)
    problems = acceptance_problems(metrics)
    margin = not problems and max(metrics['error_1'], metrics['error_2']) <= .019
    costs = prediction(76, 65, 60, bits, heuristic_costs(76, 65, 60, 30, bits))
    row = dict(shape=[65,60,30], brot=bits, **metrics, **costs, problems=problems, margin_19mHa=margin)
    write_npz(out/f'encoded-{bits}.npz', {**params, 'angle_words':words, 'tree_edges':edges, 'brot':np.array(bits)})
    row['encoded_sha256'] = sha256(out/f'encoded-{bits}.npz')
    rows.append(row)
    (out/'progress.json').write_text(json_text(rows))
    print(json_text(row), flush=True)
report = dict(rows=rows, structure=fit, offsets=offsets, fit_bits=12, penalty=2e-5,
              seconds=time.monotonic()-start, factor_sha256=sha256(out/'factors.npz'),
              input_sha256=sha256(checkpoint), numpy=np.__version__, scipy=factor_pipeline.scipy.__version__,
              source_hashes={str(p):sha256(p) for p in [Path(__file__),
                  Path('tasks/dfthcsos/factor_quantized.py'), Path('tasks/dfthcsos/factor_offsets.py')]})
(out/'report.json').write_text(json_text(report))
raise SystemExit(0 if rows[0]['margin_19mHa'] else 3)
