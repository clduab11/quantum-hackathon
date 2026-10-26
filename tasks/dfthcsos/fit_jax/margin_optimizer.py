# SPDX-License-Identifier: Apache-2.0
"""Bounded Adam for Phase M; finite infeasible training states are permitted."""
import time
import jax
import jax.numpy as jnp
from .margin_loss import penalty, eligible, effective

RATES = dict(angles=1e-4, w=1e-6, offsets=1e-5)


def update(params, moments, gradient, iteration):
    m, v = moments
    m = jax.tree.map(lambda a,g: .9*a+.1*g, m, gradient)
    v = jax.tree.map(lambda a,g: .999*a+.001*g*g, v, gradient)
    decay = jnp.sqrt(1+iteration/50)
    proposed = {k:params[k]-RATES[k]/decay*(m[k]/(1-.9**iteration))/
                (jnp.sqrt(v[k]/(1-.999**iteration))+1e-8) for k in params}
    return proposed, (m,v)


def fit(params, evaluate, target, seconds, steps, checkpoint):
    started = time.monotonic()
    value_grad = jax.jit(jax.value_and_grad(lambda p: penalty(evaluate(p), target)))
    advance = jax.jit(update)
    zeros = jax.tree.map(jnp.zeros_like, params)
    moments, selected, best = (zeros,zeros), None, params
    best_value, best_score, accepted = float(penalty(evaluate(params),target)), float('inf'), 0
    for iteration in range(1, steps+1):
        if time.monotonic()-started >= seconds:
            break
        value, gradient = value_grad(params)
        if not bool(jnp.isfinite(value)) or not all(bool(jnp.all(jnp.isfinite(g))) for g in gradient.values()):
            raise ValueError('nonfinite Phase M gradient; retain previous unverified checkpoints')
        proposal, next_moments = advance(params,moments,gradient,iteration)
        metrics = evaluate(proposal)
        after = float(penalty(metrics,target))
        if not bool(jnp.isfinite(after)) or not all(bool(jnp.isfinite(v)) for v in metrics.values()):
            raise ValueError('nonfinite Phase M proposal; parameters and moments not accepted')
        params, moments, accepted = proposal, next_moments, accepted+1
        if after < best_value:
            best_value, best = after, params
        ready = bool(eligible(metrics,target))
        if ready and float(effective(metrics)) < best_score:
            selected, best_score = params, float(effective(metrics))
        if iteration == 1 or iteration % 10 == 0 or ready:
            checkpoint(params,dict(iteration=iteration,penalty_before=float(value),penalty_after=after,
                eligible=ready,metrics={k:float(v) for k,v in metrics.items()},seconds=time.monotonic()-started))
        if ready:
            break  # smallest proving run; score this point before any further experiment
    return selected, best, dict(steps=accepted,best_penalty=best_value,seconds=time.monotonic()-started)
