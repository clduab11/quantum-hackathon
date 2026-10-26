# SPDX-License-Identifier: Apache-2.0
"""PRA-246 port of ViberTeam v2 methods; attribution and changes in FIT_V4.md."""
from __future__ import annotations
import math
import numpy as np
import torch

def x_sym(u, w, tg):
    """Rows of the R*C squares X^{rc} = sum_b w_b u_b u_b^T in the symmetric pair basis."""
    v = u[:, :, tg.ri] * u[:, :, tg.ci] * tg.scale
    a = torch.einsum('rbm,rbc->rcm', v, w)
    return a.reshape(-1, a.shape[-1])


def frob_err(a, tg):
    e = a.T @ a - tg.Ts
    return torch.sqrt((e * e).sum())


def d_penalty(w):
    a = w.abs().sum(dim=1)
    s = w.sum(dim=1)
    return 0.5 * (a * a - s * s).sum()


def log_depth_tree_edges(n):
    edges, level, depth = [], [0], 0
    while len(edges) < n - 1:
        nxt = []
        for label in level:
            nxt.append(label)
            right = label + (1 << depth)
            if right < n:
                edges.append((label, right))
                nxt.append(right)
        level, depth = nxt, depth + 1
    return np.asarray(edges, dtype=np.int64)


EDGES = log_depth_tree_edges(76)

class Tree:
    def __init__(self, edges=EDGES, n=76, device='cuda'):
        self.n = n
        levels, cur, used = [], [], set()
        for t, (p, q) in enumerate(edges):
            if p in used or q in used:
                levels.append(cur)
                cur, used = [], set()
            cur.append(t)
            used.update((int(p), int(q)))
        levels.append(cur)
        self.plan = []
        for level in levels:
            colmap = np.full(n, n - 1, dtype=np.int64)
            sign = np.zeros(n)
            perm = np.arange(n)
            for t in level:
                p, q = int(edges[t][0]), int(edges[t][1])
                colmap[p] = colmap[q] = t
                sign[p], sign[q] = -1.0, 1.0
                perm[p], perm[q] = q, p
            self.plan.append((torch.tensor(colmap, device=device), torch.tensor(sign, device=device, dtype=torch.float32),
                              torch.tensor(perm, device=device)))

    def __call__(self, theta):
        k = theta.shape[0]
        ang = math.pi * theta
        c = torch.cat([torch.cos(ang), torch.ones(k, 1, device=theta.device)], dim=1)
        s = torch.cat([torch.sin(ang), torch.zeros(k, 1, device=theta.device)], dim=1)
        u = torch.zeros(k, self.n, device=theta.device, dtype=theta.dtype)
        u[:, 0] = 1.0
        for colmap, sign, perm in self.plan:
            u = u * c[:, colmap] + u[:, perm] * (s[:, colmap] * sign)
        return u


def gauge_angles(u, edges=EDGES):
    """Signed half-open gauge: theta/pi in [-1/2, 1/2], each row reproduced up to sign."""
    a = np.array(u, dtype=np.float64, copy=True)
    ang = np.zeros((a.shape[0], len(edges)))
    for j in reversed(range(len(edges))):
        p, q = edges[j]
        norm = np.hypot(a[:, p], a[:, q])
        sign = np.where(np.abs(a[:, p]) < 1e-12, np.where(a[:, q] > 0, -1.0, 1.0), np.where(a[:, p] < 0, -1.0, 1.0))
        ang[:, j] = np.where(norm < 1e-12, 0.0, np.arctan2(a[:, q] * sign, a[:, p] * sign))
        a[:, p] = np.where(norm < 1e-12, 0.0, norm * sign)
        a[:, q] = 0.0
    return ang / np.pi


def quantize(U, w, tg, brot=10, kappa=2e-5, steps=1200, final_steps=4000, probes=16, log=print,
             fracs=(0.3, 0.5, 0.65, 0.75, 0.83, 0.89, 0.93, 0.95, 0.97, 0.98, 0.985, 0.99, 0.993, 0.996, 0.998, 1.0),closed_endpoint=False, callback=None):
    """Progressive, sensitivity-ordered quantization of the two-body gauge angles."""
    if U.device.type != 'cuda' or w.device.type != 'cuda':
        raise ValueError('QAT requires CUDA; CPU fitting is forbidden')
    R, B, N = U.shape
    tree = Tree(device=U.device)
    u0 = (U / U.norm(dim=2, keepdim=True)).detach().cpu().numpy().reshape(-1, N)
    scale = float(1 << (brot - 1))
    # Optional search extension: +pi/2 is a valid integer rotation too.
    # The caller must signed-canonicalize the final words before compiling;
    # that changes row gauge, never the represented rank-one projector.
    # Default preserves the original public trainer's half-open search.
    lo, hi = -0.5, (0.5 if closed_endpoint else 0.5 - 1.0 / scale)
    theta = torch.tensor(gauge_angles(u0), device=U.device, dtype=torch.float32)
    w = w.detach().clone()
    frozen = torch.zeros_like(theta, dtype=torch.bool)
    qvals = torch.zeros_like(theta)

    def qround(t):
        return torch.clamp(torch.round(t * scale) / scale, lo, hi)

    def resid(th, w):
        return frob_err(x_sym(tree(th).reshape(R, B, N), w, tg), tg)
    lf = torch.compile(resid)

    def impact():
        th = torch.where(frozen, qvals, theta).detach().clone().requires_grad_(True)
        a = x_sym(tree(th).reshape(R, B, N), w, tg)
        e = a.T @ a - tg.Ts
        acc = torch.zeros_like(th)
        for _ in range(probes):
            v = torch.randn_like(e)
            g, = torch.autograd.grad((e * (v + v.T)).sum(), th, retain_graph=True)
            acc += g * g
        r = qround(theta) - theta
        return acc * r * r

    for stage, frac in enumerate(list(fracs) + [None]):
        if frac is not None:
            need = int(frac * theta.numel()) - int(frozen.sum())
            if need > 0:
                imp = impact()
                with torch.no_grad():
                    imp[frozen] = -1.0
                    idx = torch.argsort(imp.flatten(), descending=True)[:need]
                    fl, qv = frozen.flatten().clone(), qvals.flatten().clone()
                    fl[idx] = True
                    qv[idx] = qround(theta).flatten()[idx]
                    frozen, qvals = fl.view_as(frozen), qv.view_as(qvals)
        n_steps = steps if frac is not None else final_steps
        th_p = theta.clone().requires_grad_(True)
        w_p = w.clone().requires_grad_(True)
        groups = [{'params': [w_p], 'lr': 3e-4}] + ([] if bool(frozen.all()) else [{'params': [th_p], 'lr': 1e-3}])
        opt = torch.optim.Adam(groups)
        ff = frozen.float()
        best = (float('inf'), None, None, None)
        for s in range(n_steps + 1):
            e = lf(ff * qvals + (1 - ff) * th_p, w_p)
            total = e + kappa * d_penalty(w_p)
            if s % 25 == 0 and total.item() < best[0]:
                best = (total.item(), th_p.detach().clone(), w_p.detach().clone(), e.item())
            if s == n_steps:
                break
            opt.zero_grad(set_to_none=True)
            total.backward()
            opt.step()
            with torch.no_grad():
                th_p.clamp_(lo, hi)
            for g in opt.param_groups:
                g['lr'] *= 0.2 ** (1.0 / n_steps)
        theta, w = best[1], best[2]
        if callback:
            current = torch.where(frozen, qvals, theta).detach()
            callback(tree(current).reshape(R, B, N).cpu().numpy().astype(float), w.cpu().numpy().astype(float), stage)
        log(f'  quantize stage {stage:2d} frozen {float(frozen.float().mean()):.4f} error_2 {1e3 * best[3]:8.3f} mHa')
    final = torch.where(frozen, qvals, qround(theta)).cpu().numpy().astype(np.float64)
    words = np.mod(np.round(final * scale).astype(np.int64), 1 << brot)
    return words, w.cpu().numpy().astype(np.float64)

