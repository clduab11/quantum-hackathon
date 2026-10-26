# SPDX-License-Identifier: Apache-2.0
"""Scale-normalized Adam proposals with a hard, rounded feasibility line search."""
import time
import jax
import jax.numpy as jnp
from .loss import admissible, objective


def step(params, moments, iteration, gradient, evaluate, rate, before, attempts=40):
    """Return an accepted state or the identical old state (including moments)."""
    m, v = moments
    next_m = jax.tree.map(lambda a,g: .9*a+.1*g, m, gradient)
    next_v = jax.tree.map(lambda a,g: .999*a+.001*g*g, v, gradient)
    direction = jax.tree.map(lambda a,b: (a/(1-.9**iteration))/(jnp.sqrt(b/(1-.999**iteration))+1e-8),next_m,next_v)
    trials = []
    for backtrack in range(attempts):
        scale = rate * 2.**-backtrack
        proposed = jax.tree.map(lambda p,d: p-scale*d,params,direction)
        metrics = evaluate(proposed)
        valid, value = bool(admissible(metrics)), float(objective(metrics))
        trials.append(dict(rate=scale,admissible=valid,objective=value))
        if valid and value < before:
            return proposed,(next_m,next_v),metrics,trials
    return params,moments,None,trials


def fit(params, evaluate, seconds, steps, rate, checkpoint, profile):
    """Deterministic steps; clock budget includes JIT, each step is fully audited."""
    started = time.monotonic()
    value_grad = jax.jit(jax.value_and_grad(lambda p: objective(evaluate(p))))
    zeros = jax.tree.map(jnp.zeros_like,params)
    moments, accepted, adam_steps, records = (zeros,zeros),0,0,[]
    for iteration in range(1,steps+1):
        if time.monotonic()-started >= seconds:
            break
        before, gradient = value_grad(params)
        before = float(before)
        assignment_seconds = profile(params)
        previous, previous_moments = params,moments
        params,moments,metrics,trials = step(params,moments,adam_steps+1,gradient,evaluate,rate,before)
        restart_trials = []
        if metrics is None and adam_steps:
            # Stale momentum need not be a descent direction after a sharp penalty.
            params,moments,metrics,restart_trials = step(previous,(zeros,zeros),1,gradient,evaluate,rate,before)
            if metrics is None:
                moments = previous_moments
            else:
                adam_steps = 0
        accepted += metrics is not None
        adam_steps += metrics is not None
        record = dict(iteration=iteration,accepted=metrics is not None,objective_before=before,
                      gradient_norms={k:float(jnp.linalg.norm(v)) for k,v in gradient.items()},
                      assignment_seconds=assignment_seconds,trials=trials,restart_trials=restart_trials,seconds=time.monotonic()-started)
        if metrics is not None:
            record['metrics'] = {k:float(v) for k,v in metrics.items()}
        checkpoint(params,record)
        records.append(record)
        if metrics is None:
            break  # identical deterministic state cannot improve by retrying it
    return params,dict(accepted_steps=accepted,steps=records,seconds=time.monotonic()-started)
