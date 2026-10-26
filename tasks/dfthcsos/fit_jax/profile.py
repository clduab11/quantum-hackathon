# SPDX-License-Identifier: Apache-2.0
"""Time the reviewed assignment on the current point's real overlap matrix."""
import time
import jax
import jax.numpy as jnp
from .angles import decode, quantize
from .assignment import assign


def profiler(fixed, edges, bits):
    @jax.jit
    def overlap(params):
        vectors = decode(quantize(params['angles'],bits),edges)
        vectors /= jnp.linalg.norm(vectors,axis=1,keepdims=True)
        w, offsets = params['w'],params['offsets']
        n = vectors.shape[1]
        body = vectors[n:].reshape(*w.shape[:2],n)
        body /= jnp.linalg.norm(body,axis=2,keepdims=True)
        x = jnp.einsum('rbp,rbq,rbc->rcpq',body,body,w)
        x = jnp.tril(x)+jnp.swapaxes(jnp.tril(x,k=-1),-1,-2)
        h = (fixed['h1_thc']-.5*fixed['electrons']*fixed['S']+fixed['beta_1']*jnp.eye(n)
             -jnp.einsum('rc,rcpq->pq',offsets,x))
        _, columns = jnp.linalg.eigh(h,symmetrize_input=False)
        return jnp.abs(vectors[:n]@columns)
    assignment = jax.jit(assign)
    def measure(params):
        matrix = overlap(params).block_until_ready()
        assignment(matrix).block_until_ready()  # compile/warm-up outside timed sample
        started = time.monotonic()
        assignment(matrix).block_until_ready()
        return time.monotonic()-started
    return measure
