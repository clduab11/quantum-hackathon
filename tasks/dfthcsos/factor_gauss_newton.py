# SPDX-License-Identifier: Apache-2.0
"""CPU tangent Gauss–Newton with bounded preconditioned CG; see FIT_V3.md."""
import numpy as np
from tasks.dfthcsos.factor_merge import projectors


class Geometry:
    def __init__(self, u, w):
        self.u = u / np.linalg.norm(u, axis=-1, keepdims=True)
        self.w = w
        self.i, self.j = np.tril_indices(u.shape[-1])
        self.scale = np.where(self.i == self.j, 1., np.sqrt(2.))
        self.p = projectors(self.u)
        self.x = self.columns(self.p @ w)
        self.gram = self.x.T @ self.x

    def columns(self, x):
        return x.transpose(1, 0, 2).reshape(len(self.i), -1)

    def tangent(self, du):
        return du - self.u * np.sum(du * self.u, axis=-1, keepdims=True)

    def unpack(self, flat):
        return self.tangent(flat[:self.u.size].reshape(self.u.shape)), flat[self.u.size:].reshape(self.w.shape)

    def jvp(self, flat):
        du, dw = self.unpack(flat)
        dp = ((du[:, :, self.i]*self.u[:, :, self.j] +
               self.u[:, :, self.i]*du[:, :, self.j])*self.scale).transpose(0, 2, 1)
        return self.columns(dp @ self.w + self.p @ dw)

    def vjp(self, gx):
        gr = gx.reshape(len(self.i), self.w.shape[0], self.w.shape[2]).transpose(1, 0, 2)
        gw = self.p.transpose(0, 2, 1) @ gr
        gp = (gr @ self.w.transpose(0, 2, 1)).transpose(0, 2, 1) / self.scale
        matrix = np.zeros((*self.u.shape, self.u.shape[-1]))
        matrix[:, :, self.i, self.j] = gp
        matrix[:, :, self.j, self.i] = gp
        gu = 2 * (matrix @ self.u[..., None])[..., 0]
        return np.r_[self.tangent(gu).ravel(), gw.ravel()]

    def normal(self, flat):
        dx = self.jvp(flat)
        return self.vjp(2 * (dx @ self.gram + self.x @ (dx.T @ self.x)))

    def diagonal(self):
        g = np.diag(self.gram).reshape(self.w.shape[0], self.w.shape[2])
        ud = 4 * np.sum(self.w**2 * g[:, None, :], axis=-1)
        return np.maximum(np.r_[np.broadcast_to(ud[..., None], self.u.shape).ravel(),
                                 np.broadcast_to(2*g[:, None, :], self.w.shape).ravel()], 1e-9)

    def trial(self, step, alpha):
        du, dw = self.unpack(step)
        u = self.u + alpha * du
        return u / np.linalg.norm(u, axis=-1, keepdims=True), self.w + alpha * dw


def pcg(geometry, rhs, damping, iterations):
    diagonal = geometry.diagonal()
    x, residual = np.zeros_like(rhs), rhs.copy()
    norm = np.linalg.norm(rhs)
    if norm == 0:
        return x, dict(iterations=0, relative_residual=0.)
    z = residual / ((1+damping)*diagonal)
    direction, rz = z.copy(), residual @ z
    for index in range(iterations):
        applied = geometry.normal(direction) + damping*diagonal*direction
        denominator = direction @ applied
        if denominator <= 0:
            break
        alpha = rz / denominator
        x += alpha*direction
        residual -= alpha*applied
        if np.linalg.norm(residual) < .05*norm:
            break
        z = residual / ((1+damping)*diagonal)
        new_rz = residual @ z
        direction = z + new_rz/rz*direction
        rz = new_rz
    return x, dict(iterations=index+1, relative_residual=float(np.linalg.norm(residual)/norm))


def refine(params, target, iterations, cg_iterations, callback=None):
    if min(iterations, cg_iterations) < 1:
        raise ValueError('Gauss–Newton and CG iterations must be positive')
    out = {k: np.array(v, copy=True) for k, v in params.items()}
    damping, history = .001, []
    for index in range(iterations):
        geometry = Geometry(out['U'], out['W'])
        residual = geometry.x @ geometry.x.T - target
        before = float(np.sum(residual**2))
        if np.sqrt(before) < .015:
            break
        grad = geometry.vjp(2 * (residual @ geometry.x))
        step, cg = pcg(geometry, -grad, damping, cg_iterations)
        accepted, error = False, before
        for alpha in (1., .5, .25, .125, .0625, .03125):
            u, w = geometry.trial(step, alpha)
            x = geometry.columns(projectors(u) @ w)
            trial = float(np.sum((x @ x.T-target)**2))
            if np.isfinite(trial) and trial < before:
                out.update(U=u, W=w)
                damping = max(1e-8, damping*(.5 if alpha >= .5 else 2.))
                accepted, error = True, trial
                break
        if not accepted:
            damping = min(100., damping*10)
        history.append(dict(iteration=index+1, error=float(np.sqrt(error)),
                            accepted=accepted, alpha=alpha if accepted else None,
                            damping=damping, cg=cg))
        if callback:
            callback(out)
        if not accepted and damping >= 100:
            break
    return out, dict(iterations=len(history), history=history)
