# SPDX-License-Identifier: Apache-2.0
"""Compare the GPU loss against the pinned official numpy verifier; no fitting."""
import argparse
import os
from pathlib import Path
import sys
import time

# Set before JAX initializes: coexist with T3 without reserving most GPU memory.
os.environ.setdefault('XLA_PYTHON_CLIENT_PREALLOCATE','false')
import numpy as np
from tasks.dfthcsos.factor_math import packed_target
from tasks.dfthcsos.factor_support import checked_inputs, sha256, json_text

FACTOR_SHA256 = '809a992900937425f01a0593803921873f7bb472d590592c378d3ceb23657df5'


def accelerator():
    import jax
    jax.config.update('jax_enable_x64',True)
    devices = [d for d in jax.devices() if d.platform in ('gpu','tpu')]
    if not devices:
        raise ValueError('GPU/TPU unavailable; install the gpu group and check CUDA visibility; CPU fitting is forbidden')
    return devices[0]


def intake(starter, competition, factor):
    """Verify all source/input pins before import; use official fixed shifts."""
    pins = checked_inputs(starter)
    for item in pins['competition_files']:
        if sha256(competition/item['path']) != item['sha256']:
            raise ValueError(f"competition SHA-256 mismatch: {item['path']}; restore pinned package")
    if sha256(factor) != FACTOR_SHA256:
        raise ValueError('public factor SHA-256 mismatch; use the declared PRA-245 v8 factor')
    sys.path[:0] = [str(competition/'verifiers'),str(competition/'kickmix'),str(starter/'starter_kit')]
    inputs, fixed = physics(factor)
    with np.load(factor,allow_pickle=False) as archive:
        angles = archive['angle_words'].astype(np.float64)/(1 << 10)
        edges = archive['tree_edges'].copy()
    params = dict(angles=angles,w=inputs.w,offsets=inputs.W)
    return inputs,params,fixed,edges,pins


def physics(factor):
    """The single fixed-shift intake path, also exercised with corrupted shifts."""
    from dfthcsos.verify import load_inputs
    inputs = load_inputs(factor)
    fixed = dict(target=packed_target(inputs.ref['tei'],inputs.S),h1_thc=inputs.ref['h1_thc'],
                 S=inputs.S,beta_1=inputs.beta_1,electrons=inputs.ref['electrons'],
                 ecore=inputs.ref['ecore'],energy_upper=inputs.energy_upper)
    return inputs,fixed


def compare(actual, expected):
    """Absolute 1e-10 only: no relative allowance for the large SOS energy."""
    differences = {key:abs(float(actual[key])-expected[key]) for key in actual}
    for key,difference in differences.items():
        if not np.isfinite(difference) or difference > 1e-10:
            raise AssertionError(f'{key} mirror differs by {difference:.17g} Ha; limit 1e-10')
    return differences


def mirror(starter, competition, factor):
    import jax
    from .angles import quantize, decode
    from .loss import terms, objective
    device = accelerator()
    inputs,params,fixed,edges,pins = intake(starter,competition,factor)
    from dfthcsos.verify import evaluate_words
    from dfthcsos.scoreinfra.dfthc_math import reconstruct_u_vectors
    from starter.task2_angles.encode import encode_inputs
    from verifier.score import SubmissionInputs
    encoder = SubmissionInputs('FeMoCo76o113e',None,inputs.params,inputs.ref,inputs.w,
                               inputs.W,inputs.S,inputs.beta_1,inputs.energy_upper)
    report = dict(jax=jax.__version__,device=str(device),device_kind=device.device_kind,
                  x64=jax.config.x64_enabled,factor_sha256=sha256(factor),points=[],
                  source_hashes={p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')},
                  competition_pins=pins['competition_files'],
                  full_circuit_verified=False,fit_performed=False,initialization='pinned encode_inputs at each precision')
    with jax.default_device(device):
        p,f,e = jax.device_put((params,fixed,edges),device)
        assert all(a.device.platform in ('gpu','tpu') for a in jax.tree.leaves((p,f,e)))
        for bits in (12,11,8):
            start = time.monotonic()
            words = encode_inputs(encoder,edges,bits)
            # Fresh one-body target for each precision, as in the pinned encoder.
            p = {**p,'angles':jax.device_put(words.astype(np.float64)/(1 << (bits-1)),device)}
            rounded = quantize(p['angles'],bits)
            np.testing.assert_array_equal(np.asarray(rounded)*(1 << (bits-1)),words)
            vectors = np.asarray(jax.jit(decode)(rounded,e))
            expected_vectors = reconstruct_u_vectors(words/(1 << (bits-1)),edges)
            np.testing.assert_allclose(vectors,expected_vectors,rtol=0,atol=1e-13)
            actual = jax.jit(lambda p,f: terms(p,f,e,bits))(p,f)
            actual = {k:float(v) for k,v in actual.items()}
            expected = evaluate_words(inputs,words,edges,bits)
            differences = compare(actual,expected)
            # Permuting submitted one-body rows cannot change the matched loss.
            permuted = {**p,'angles':p['angles'].at[:inputs.num_orbitals].set(p['angles'][:inputs.num_orbitals][::-1])}
            reordered = jax.jit(lambda q: terms(q,f,e,bits))(permuted)
            compare(reordered,expected)
            report['points'].append(dict(bits=bits,jax=actual,official=expected,
                absolute_difference=differences,seconds=time.monotonic()-start))
        # Stored words are a separate 11-bit case, not the fresh encoder output.
        stored_p = {**p,'angles':jax.device_put(params['angles'],device)}
        stored_actual = jax.jit(lambda q: terms(q,f,e,11))(stored_p)
        stored_expected = evaluate_words(inputs,np.rint(params['angles']*1024).astype(np.int64),edges,11)
        stored_delta = compare(stored_actual,stored_expected)
        report['stored_words_11'] = dict(official=stored_expected,absolute_difference=stored_delta)
        # Perturb both submitted shifts through the very same physics intake.
        altered = {**inputs.params,'H1_I':inputs.params['H1_I']+123.,
                   'Hsym_lower':inputs.params['Hsym_lower']+17.}
        _, shifted_fixed = physics(altered)
        for name in fixed:
            np.testing.assert_array_equal(shifted_fixed[name],fixed[name])
        shifted = jax.jit(lambda q,g: terms(q,g,e,11))(stored_p,jax.device_put(shifted_fixed,device))
        report['perturbed_shift_difference'] = compare(shifted,{k:float(v) for k,v in stored_actual.items()})
        # One gradient evaluation proves the assignment/rounding path composes
        # with autodiff on real data. This does not take an optimizer step.
        p = {**p,'angles':jax.device_put(params['angles'],device)}
        value, gradient = jax.jit(jax.value_and_grad(lambda p: objective(terms(p,f,e,11))))(p)
        norms = {k:float(np.linalg.norm(np.asarray(v))) for k,v in gradient.items()}
        if not np.isfinite(float(value)) or not all(np.isfinite(v) and v > 0 for v in norms.values()):
            raise AssertionError(f'nonfinite or zero loss gradient: {norms}')
        report['gradient_norms'] = norms
    report['max_absolute_difference'] = max([max(p['absolute_difference'].values()) for p in report['points']] + [max(stored_delta.values())])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,epilog=(
        'Requires uv sync --group gpu and the pinned starter/competition packages. '
        'Example: python -m tasks.dfthcsos.fit_jax.mirror --starter /home/cld-main/work/vqcc-data/starter-kit '
        '--competition /home/cld-main/work/vqcc-data/google-verifiable-quantum-circuit-compilation '
        '--factor /home/cld-main/work/vqcc-data/inputs/thc/femoco_thc_r5.npz. '
        'Prints JSON only; writes no files. Missing GPU, hash mismatch or numerical disagreement exits nonzero.'))
    for flag in ('starter','competition','factor'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args = parser.parse_args()
    try:
        print(json_text(mirror(args.starter,args.competition,args.factor)))
        return 0
    except (ValueError,AssertionError,OSError,RuntimeError) as error:
        print(f'JAX mirror: {error}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
