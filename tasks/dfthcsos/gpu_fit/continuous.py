# SPDX-License-Identifier: Apache-2.0
"""CUDA continuous stages with the published L-BFGS and tangent GN budgets."""
import math
import time
import numpy as np
import torch
from .geometry import physical_error
from .gauss_newton import Geometry, pcg


def structural(u, w, target, checkpoint, *, steps=8000, seconds=700):
    device = 'cuda'
    if not torch.cuda.is_available():
        raise RuntimeError('CPU fitting is forbidden')
    raw = torch.nn.Parameter(torch.tensor(u, dtype=torch.float32, device=device))
    weights = torch.nn.Parameter(torch.tensor(w, dtype=torch.float32, device=device))
    h = torch.tensor(target, dtype=torch.float32, device=device)
    i, j = np.tril_indices(u.shape[-1])
    i, j = torch.tensor(i, device=device), torch.tensor(j, device=device)
    scale = torch.where(i == j, 1., math.sqrt(2.))
    optimizer = torch.optim.LBFGS([raw, weights], lr=1., max_iter=5, history_size=20,
        line_search_fn='strong_wolfe', tolerance_grad=1e-10, tolerance_change=1e-13)
    calls = 0
    def closure():
        nonlocal calls
        optimizer.zero_grad(set_to_none=True)
        unit = raw / torch.linalg.vector_norm(raw, dim=-1, keepdim=True)
        projectors = (unit[:, :, i] * unit[:, :, j] * scale).transpose(1, 2)
        x = (projectors @ weights).permute(1, 0, 2).reshape(len(i), -1)
        residual = torch.linalg.vector_norm(x @ x.T - h)
        penalty = .5 * (weights.abs().sum(dim=1)**2 - weights.sum(dim=1)**2).sum()
        loss = 1000 * (residual + 2e-6 * penalty)
        if not torch.isfinite(loss):
            raise ValueError('nonfinite CUDA structural objective')
        loss.backward()
        calls += 1
        return loss
    start = time.monotonic()
    best = math.inf
    best_u, best_w = u.copy(), w.copy()
    for step in range(steps + 1):
        if step:
            optimizer.step(closure)
        expired = time.monotonic() - start >= seconds
        if step % 100 == 0 or step == steps or expired:
            un = (raw / raw.norm(dim=-1, keepdim=True)).detach().cpu().numpy().astype(float)
            wn = weights.detach().cpu().numpy().astype(float)
            exact = physical_error(un, wn, target)
            if exact < best:
                best, best_u, best_w = exact, un.copy(), wn.copy()
            checkpoint(un, wn, dict(step=step, calls=calls, residual=exact))
        if expired or (best < .015 and step >= 100):
            break
    return best_u, best_w, dict(steps=step, calls=calls, best_error=best,
        elapsed=time.monotonic()-start, limit_steps=steps, limit_seconds=seconds,
        stop='source_time_limit' if expired else 'target' if best < .015 else 'iteration_limit')


def gauss_newton(u, w, target, checkpoint, *, iterations=300, cg_iterations=100, seconds=450):
    if not torch.cuda.is_available():
        raise RuntimeError('CPU fitting is forbidden')
    g = Geometry(u, w, device='cuda', dtype='float32')
    h = torch.tensor(target, dtype=g.dtype, device='cuda')
    start, damping, best = time.monotonic(), .001, math.inf
    best_u, best_w = u.copy(), w.copy()
    stop = 'iteration_limit'
    total_cg = 0
    for iteration in range(iterations + 1):
        residual = g.x @ g.x.T - h
        loss = float((residual * residual).sum()) * .5
        un, wn = g.u.cpu().numpy().astype(float), g.w.cpu().numpy().astype(float)
        exact = physical_error(un, wn, target)
        if exact < best:
            best, best_u, best_w = exact, un.copy(), wn.copy()
        checkpoint(un, wn, dict(iteration=iteration, residual=exact, damping=damping))
        if exact < .015:
            stop = 'target'; break
        if time.monotonic() - start >= seconds:
            stop = 'source_time_limit'; break
        if iteration == iterations:
            break
        grad, diagonal = g.vjp(2 * (residual @ g.x)), g.diagonal()
        if not torch.isfinite(grad).all():
            raise ValueError('nonfinite GN gradient')
        if float(torch.linalg.vector_norm(grad)) == 0:
            stop = 'zero_gradient'; break
        step, info = pcg(g, -grad, diagonal, damping, iterations=cg_iterations)
        total_cg += info['cg_iterations']
        accepted = False
        for alpha in (1., .5, .25, .125, .0625, .03125):
            ut, wt = g.apply(step, alpha)
            xt = g.trial_x(ut, wt)
            rt = xt @ xt.T - h
            trial = float((rt * rt).sum()) * .5
            if math.isfinite(trial) and trial < loss:
                g.u, g.w = ut, wt
                g.refresh()
                damping = max(1e-8, damping * (.5 if alpha >= .5 else 2.))
                accepted = True; break
        if not accepted:
            damping = min(100, damping * 10)
            if damping >= 100:
                stop = 'source_damping_limit'; break
    return best_u, best_w, dict(iterations=iteration, cg_iterations=total_cg,
        best_error=best, elapsed=time.monotonic()-start, stop=stop,
        limit_iterations=iterations, limit_cg=cg_iterations, limit_seconds=seconds)
