# SPDX-License-Identifier: Apache-2.0
"""Maximum total overlap by shortest augmenting paths, entirely on the device."""
import jax
import jax.numpy as jnp


def assign(overlap):
    """Return one ideal-column index per submitted row; no greedy pairing.

    The discrete assignment has no tangent. Potentials use one-based rows and
    columns; column zero is the augmenting-path sentinel. Ties choose the first
    minimum column. At exact eigenvalue degeneracy the pairing is not unique.
    """
    cost = -jax.lax.stop_gradient(overlap)
    n = cost.shape[0]
    if cost.shape != (n, n):
        raise ValueError('overlap must be square')
    zeros = jnp.zeros(n+1, dtype=cost.dtype)
    indices = jnp.arange(n+1, dtype=jnp.int32)
    def add_row(i, state):
        u, v, p = state
        p = p.at[0].set(jnp.int32(i))
        initial = (u, v, jnp.zeros(n+1, bool), jnp.full(n+1, jnp.inf),
                   jnp.zeros(n+1, jnp.int32), jnp.int32(0))
        def search(state):
            u, v, used, minimum, way, j0 = state
            used = used.at[j0].set(True)
            reduced = jnp.concatenate((jnp.array([jnp.inf]), cost[p[j0]-1]-u[p[j0]]-v[1:]))
            better = (~used) & (reduced < minimum)
            minimum = jnp.where(better, reduced, minimum)
            way = jnp.where(better, j0, way)
            j1 = jnp.argmin(jnp.where(used, jnp.inf, minimum)).astype(jnp.int32)
            delta = minimum[j1]
            u = u.at[p].add(jnp.where(used, delta, 0.))
            v = v-jnp.where(used, delta, 0.)
            minimum = minimum-jnp.where(used, 0., delta)
            return u, v, used, minimum, way, j1
        u, v, _, _, way, j0 = jax.lax.while_loop(lambda s: p[s[-1]] != 0, search, initial)
        def augment(state):
            p, j = state
            prev = way[j]
            return p.at[j].set(p[prev]), prev
        p, _ = jax.lax.while_loop(lambda s: s[1] != 0, augment, (p, j0))
        return u, v, p
    _, _, p = jax.lax.fori_loop(1, n+1, add_row, (zeros, zeros, jnp.zeros(n+1,jnp.int32)))
    return jax.lax.stop_gradient(jnp.zeros(n,jnp.int32).at[p[1:]-1].set(indices[1:]-1))
