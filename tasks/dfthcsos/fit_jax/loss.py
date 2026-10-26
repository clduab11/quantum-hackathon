# SPDX-License-Identifier: Apache-2.0
"""Verifier terms and a separate training penalty; no acceptance or score claims."""
import jax
import jax.numpy as jnp
from .angles import decode, quantize
from .assignment import assign


def terms(parameters, fixed, edges, bits):
    """Five float64 verifier terms, with rounded angles inside every evaluation.

    parameters: angles (N+RB,N-1), w (R,B,C), offsets (R,C).
    fixed: packed target, h1_thc, S, beta_1, electrons, ecore, energy_upper.
    The fixed data must come from the hash-checked competition load_inputs.
    """
    if not jax.config.x64_enabled:
        raise ValueError('enable jax_enable_x64 before creating loss arrays')
    angles, w, offsets = (parameters[k] for k in ('angles','w','offsets'))
    return _from_vectors(decode(quantize(angles, bits), edges), w, offsets, fixed)


def _from_vectors(vectors, w, offsets, fixed):
    # Continuous kernel for testing the STE tangent; public terms always rounds.
    vectors = vectors / jnp.linalg.norm(vectors, axis=1, keepdims=True)
    n = vectors.shape[1]
    body = vectors[n:].reshape(w.shape[0],w.shape[1],n)
    # The official math normalizes twice, once before splitting and once in X.
    body = body / jnp.linalg.norm(body, axis=2, keepdims=True)
    x = jnp.einsum('rbp,rbq,rbc->rcpq', body, body, w)
    x = jnp.tril(x)+jnp.swapaxes(jnp.tril(x,k=-1),-1,-2)
    h = (fixed['h1_thc']-.5*fixed['electrons']*fixed['S']
         +fixed['beta_1']*jnp.eye(n)-jnp.einsum('rc,rcpq->pq',offsets,x))
    values, columns = jnp.linalg.eigh(h, symmetrize_input=False)
    pairing = assign(jnp.abs(vectors[:n] @ columns))
    hq = jnp.einsum('j,jp,jq->pq',values[pairing],vectors[:n],vectors[:n])
    error_1 = jnp.linalg.norm(hq-h)
    # Orthonormal symmetric-pair basis preserves the full N**4 Frobenius norm.
    i,j = jnp.tril_indices(n)
    packed = (x[:,:,i,j]*jnp.where(i==j,1.,jnp.sqrt(2.))).reshape(-1,len(i))
    error_2 = jnp.linalg.norm(packed.T @ packed-fixed['target'])
    lam1 = jnp.abs(values).sum()
    lam2 = .25*jnp.sum((jnp.abs(w).sum(axis=1)+jnp.abs(offsets+w.sum(axis=1)))**2)
    sos = (fixed['ecore']-fixed['electrons']*fixed['beta_1']
           -(lam1-values.sum())-.5*jnp.sum(offsets**2))
    return dict(error_1=error_1,error_2=error_2,Lambda=lam1+lam2,
                E_SOS=sos,E_gap=fixed['energy_upper']-sos)


def objective(metrics, score_weight=1.):
    """Training only: effective normalization plus squared margin violations.

    Margin targets are stricter than the verifier. The radicand extension only
    keeps training defined outside its domain; it never changes reported terms.
    Official Decimal/domain checks and acceptance remain with the verifier.
    """
    lam, gap = metrics['Lambda'],metrics['E_gap']
    violations = jnp.stack([metrics['error_1']-.0195, metrics['error_2']-.0195,
                            49.0001-lam,3.915-gap,gap-2*lam+.0001])
    return (score_weight*jnp.sqrt(jnp.maximum(gap*(2*lam-gap),1e-20))
            +1e6*jnp.sum(jax.nn.relu(violations)**2))


def admissible(metrics):
    """Reject an infeasible proposed step; final acceptance still needs the verifier."""
    values = jnp.stack(list(metrics.values()))
    return (jnp.all(jnp.isfinite(values)) & (metrics['error_1'] >= 0)
            & (metrics['error_1'] <= .020) & (metrics['error_2'] >= 0)
            & (metrics['error_2'] <= .020) & (metrics['Lambda'] > 49.)
            & (metrics['E_gap'] > 3.914898) & (metrics['E_gap'] < 2*metrics['Lambda']))
