# SPDX-License-Identifier: Apache-2.0
"""Givens angles in units of pi; exact half-up words, identity surrogate tangent."""
from functools import partial
import jax
import jax.numpy as jnp


@partial(jax.custom_jvp, nondiff_argnums=(1,))
def quantize(angles, bits):
    """Match starter angles_to_words(nearest), not ties-to-even jnp.round."""
    if bits not in (8, 11, 12):
        raise ValueError('use a reviewed precision: 8, 11 or 12 bits')
    scale = 1 << (bits-1)
    return jnp.mod(jnp.floor(jnp.mod(angles, 2.)*scale + .5), 1 << bits)/scale


@quantize.defjvp
def _quantize_jvp(bits, primals, tangents):
    return quantize(primals[0], bits), tangents[0]


def decode(angles, edges):
    """Ordered tree rotations on e0; every angle remains an independent variable."""
    vectors = jnp.zeros((angles.shape[0], angles.shape[1]+1), dtype=angles.dtype)
    vectors = vectors.at[:, 0].set(1.)
    def rotate(k, vectors):
        p, c = edges[k]
        a, b = vectors[:, p], vectors[:, c]
        co, si = jnp.cos(jnp.pi*angles[:, k]), jnp.sin(jnp.pi*angles[:, k])
        return vectors.at[:, p].set(co*a-si*b).at[:, c].set(si*a+co*b)
    return jax.lax.fori_loop(0, angles.shape[1], rotate, vectors)
