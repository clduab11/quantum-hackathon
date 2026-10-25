# SPDX-License-Identifier: Apache-2.0
"""Deterministic bounded optimizer alternatives for the same structural objective."""
from types import SimpleNamespace
import numpy as np
from scipy.optimize import minimize


def optimize(fun, start, steps, method, maxcor, callback, learning_rate):
    if steps < 1 or maxcor < 1 or not np.isfinite(learning_rate) or learning_rate <= 0:
        raise ValueError('steps/maxcor and learning rate must be positive and finite')
    if method == 'lbfgs':
        return minimize(fun, start, jac=True, method='L-BFGS-B', callback=callback,
                        options=dict(maxiter=steps, maxls=20, ftol=1e-12,
                                     gtol=1e-8, maxcor=maxcor))
    if method == 'trust-ncg':
        def hessp(x, p):
            scale = np.linalg.norm(p)
            if scale == 0:
                return np.zeros_like(p)
            delta = 1e-5 * max(1., np.linalg.norm(x)) / scale
            return (fun(x + delta*p)[1] - fun(x - delta*p)[1]) / (2*delta)
        return minimize(fun, start, jac=True, hessp=hessp, method='trust-ncg',
                        callback=callback, options=dict(maxiter=steps, gtol=1e-8))
    if method != 'adam':
        raise ValueError('optimizer must be lbfgs, trust-ncg or adam')
    x, first, second = start.copy(), np.zeros_like(start), np.zeros_like(start)
    for step in range(1, steps+1):
        _, gradient = fun(x)
        first = .9*first + .1*gradient
        second = .999*second + .001*gradient**2
        x -= learning_rate * (first/(1-.9**step)) / (np.sqrt(second/(1-.999**step)) + 1e-8)
        if callback is not None:
            callback(x)
    value, _ = fun(x)
    return SimpleNamespace(x=x, nit=steps, nfev=steps+1, success=False,
                           message='Adam fixed iteration budget exhausted', fun=value)
