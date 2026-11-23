"""Optimisation of a colour-map curve: a long path that does not come near
itself.

The curve is represented by M points x_1 ... x_M in sRGB, with CAM16-UCS
coordinates u_i under the path's viewing conditions. Its conditions are

    |u_{i+1} - u_i| = l                      equal steps (uniform contrast),
    |u_i - u_j|_o  >= p_o rho   for |i - j| >= w and every observer o
                                             (thickness),

together with the lightness floor and ceiling of an image and the sRGB cube.
Either rho is maximised at a given step l (a given total length), or l is
maximised at a given rho. The window w is the number of steps spanning an
arc of 2 rho, so that parts of the curve closer than that along its length
are exempt; the condition then also limits how sharply the curve can bend,
as the thickness of a curve does (Gonzalez and Maddocks 1999).

The method is sequential linear programming in a trust region, as in the
max-min polish of MCCP (mccp.optimise.polish_maxmin).
"""

import numpy as np

from ..space import Observer, Space
from .paths import PATH_VIEW


class CurveProblem:
    def __init__(self, m, view=PATH_VIEW, observers=(), bounds=None):
        self.m = m
        obs = (Observer(),) + tuple(observers)
        self.space = Space(view, obs)
        self.prio = np.array([o.priority for o in obs])
        self.k_l = self.space.ucs.K_L
        self.bounds = bounds

    def coords(self, x):
        return self.space.coords(x)  # (k, m, 3)

    def steps(self, u0):
        return np.linalg.norm(np.diff(u0, axis=0), axis=1)


def _pairs(m, w):
    i, j = np.triu_indices(m, w)
    return i, j


def thickness(u, w):
    """Least distance between points at least w apart along the curve."""
    i, j = _pairs(len(u), w)
    return float(np.linalg.norm(u[i] - u[j], axis=1).min()) if len(i) else np.inf


def _state(prob, x, w, step, rho, bounds):
    """Objective and violations of a curve: (objective, step deviation,
    bound violation, thickness shortfall, thickness, steps)."""
    u = prob.coords(x)
    k = len(prob.prio)
    rho_now = min(thickness(u[o], w) / prob.prio[o] for o in range(k))
    st = prob.steps(u[0])
    viol = 0.0
    if bounds is not None:
        viol = max(0.0, -float(bounds.slack(u[0], prob.k_l, np.ones(len(x))).min()))
    if step is not None:
        return rho_now, float(np.abs(st - step).max()), viol, 0.0, rho_now, st
    return float(st.min()), float(np.ptp(st)), viol, max(0.0, rho - rho_now), rho_now, st


def optimise(x, step=None, rho=None, observers=(), bounds=None, view=PATH_VIEW, w=None,
             rho_guess=12.0, iters=300, radius=0.01, active_margin=4.0, penalty=20.0,
             verbose=False):
    """Improve a curve x (M, 3) in sRGB.

    Give `step` to maximise the thickness at that step length, or `rho` to
    maximise the step at that thickness. The conditions are elastic: each
    linear programme may violate them at a cost `penalty` per unit, so that a
    start that does not meet them exactly can still move. Returns (x, info)."""
    from scipy.optimize import linprog

    if (step is None) == (rho is None):
        raise ValueError("Give exactly one of step and rho.")
    x = np.clip(np.asarray(x, float), 0, 1)
    m = len(x)
    prob = CurveProblem(m, view, observers, bounds)
    l0 = float(np.mean(prob.steps(prob.coords(x)[0])))
    if w is None:
        # The window spans an arc of 2 rho; without a given rho, use the
        # caller's guess (for a path through an MCCP palette, its spacing).
        w = max(2, int(np.ceil(2 * (rho or rho_guess) / (step or l0))))
    k = len(prob.prio)
    nv = 3 * m + 4
    Z, ES, EB, ET = 3 * m, 3 * m + 1, 3 * m + 2, 3 * m + 3
    i_all, j_all = _pairs(m, w)

    def merit(st):
        return st[0] - penalty * (st[1] + st[2] + st[3])

    cur = _state(prob, x, w, step, rho, bounds)
    history = [dict(it=0, objective=cur[0], dev=cur[1], viol=cur[2], short=cur[3],
                    rho=cur[4], radius=radius)]
    for it in range(1, iters + 1):
        u, jac = prob.space.jacobian(x)
        rows, rhs = [], []
        # Equal steps (normal vision), elastic: |lin_i - s| <= e_s.
        e = u[0, 1:] - u[0, :-1]
        L = np.linalg.norm(e, axis=1)
        nvec = e / L[:, None]
        G = np.zeros((m - 1, nv))
        idx = np.arange(m - 1)
        gi = -np.einsum("nc,ncd->nd", nvec, jac[0, :-1])
        gj = np.einsum("nc,ncd->nd", nvec, jac[0, 1:])
        for c in range(3):
            G[idx, 3 * idx + c] = gi[:, c]
            G[idx, 3 * (idx + 1) + c] = gj[:, c]
        if step is None:
            G[:, Z] = -1.0
            off = L
        else:
            off = L - step
        for sign in (1.0, -1.0):
            g = sign * G
            g[:, ES] = -1.0
            rows.append(g)
            rhs.append(-sign * off)
        # Thickness, every observer, pairs near the bound only:
        # d + n.(J_i dx_i - J_j dx_j) >= p rho - e_t.
        level = rho if rho is not None else cur[4]
        for o in range(k):
            diff = u[o, i_all] - u[o, j_all]
            d = np.linalg.norm(diff, axis=1)
            act = np.flatnonzero(d < prob.prio[o] * level + active_margin)
            if not len(act):
                continue
            ii, jj, dd = i_all[act], j_all[act], d[act]
            nn = diff[act] / dd[:, None]
            T = np.zeros((len(act), nv))
            ti = -np.einsum("nc,ncd->nd", nn, jac[o, ii])
            tj = np.einsum("nc,ncd->nd", nn, jac[o, jj])
            r = np.arange(len(act))
            for c in range(3):
                T[r, 3 * ii + c] = ti[:, c]
                T[r, 3 * jj + c] = tj[:, c]
            T[:, ET] = -1.0
            if rho is None:
                T[:, Z] = prob.prio[o]
                rows.append(T)
                rhs.append(dd)
            else:
                rows.append(T)
                rhs.append(dd - prob.prio[o] * rho)
        # Lightness floor and ceiling (normal vision): slack + grad.dx >= -e_b.
        if bounds is not None:
            sl = bounds.slack(u[0], prob.k_l, np.ones(m))        # (2, m)
            sg = bounds.slack_grad(u[0], prob.k_l, np.ones(m))   # (2, m, 3)
            for c2 in range(2):
                Bm = np.zeros((m, nv))
                gb = -np.einsum("nc,ncd->nd", sg[c2], jac[0])
                for c in range(3):
                    Bm[np.arange(m), 3 * np.arange(m) + c] = gb[:, c]
                Bm[:, EB] = -1.0
                rows.append(Bm)
                rhs.append(sl[c2])
        lo = list(np.maximum(-radius, -x.ravel())) + [0.0, 0.0, 0.0, 0.0]
        hi = list(np.minimum(radius, 1 - x.ravel())) + [None, None, None, None]
        cvec = np.zeros(nv)
        cvec[Z] = -1.0
        cvec[ES] = cvec[EB] = cvec[ET] = penalty
        res = linprog(cvec, A_ub=np.vstack(rows), b_ub=np.concatenate(rhs),
                      bounds=list(zip(lo, hi)), method="highs")
        if res.status != 0:
            radius *= 0.5
            if radius < 1e-6:
                break
            continue
        x_new = np.clip(x + res.x[:3 * m].reshape(m, 3), 0, 1)
        new = _state(prob, x_new, w, step, rho, bounds)
        if merit(new) > merit(cur) + 1e-9:
            x, cur = x_new, new
            history.append(dict(it=it, objective=cur[0], dev=cur[1], viol=cur[2],
                                short=cur[3], rho=cur[4], radius=radius))
            if verbose and len(history) % 10 == 0:
                print(f"{it}: objective {cur[0]:.3f} rho {cur[4]:.2f} step dev {cur[1]:.3f} "
                      f"bound viol {cur[2]:.3f} r {radius:.4f}", flush=True)
            radius = min(radius * 1.5, 0.05)
        else:
            radius *= 0.5
            if radius < 1e-6:
                break
    info = dict(window=w, history=history, rho=cur[4], step=float(np.mean(cur[5])),
                length=float(cur[5].sum()), step_dev=cur[1], bound_violation=cur[2])
    return x, info


def resample_equal(rgb, m, view=PATH_VIEW):
    """m points at equal arc length along the polyline through rgb, in sRGB."""
    from ..space import CAM16UCS, linear_to_srgb
    ucs = CAM16UCS(view)
    u = ucs(np.asarray(rgb, float))
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(u, axis=0), axis=1))])
    t = np.linspace(0, arc[-1], m)
    us = np.stack([np.interp(t, arc, u[:, k]) for k in range(3)], -1)
    return linear_to_srgb(ucs.to_linear(us))
