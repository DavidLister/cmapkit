"""Optimisation of a colour-map curve: a long path that does not come near
itself.

The curve is represented by M points x_1 ... x_M in sRGB, with CAM16-UCS
coordinates u_i under the path's viewing conditions, and a_ij denotes the
length of the polyline between points i and j. Its conditions are

    |u_{i+1} - u_i| = l                      equal steps (uniform contrast),
    |u_i - u_j|_o  >= p_o rho s(a_ij / rho)  for |i - j| >= 2 and every
                                             observer o (thickness),     (1)

with s(x) = sin(min(x, pi / 2)), together with the lightness floor and
ceiling of an image and the sRGB cube. The right side of (1) is the chord
of a circle of diameter rho spanning the arc a_ij, up to a quarter turn,
and rho beyond. Parts of the curve far apart along it must therefore stay
rho apart, and nearby parts may approach no closer than they would on that
circle, so that the curve cannot turn more sharply than the circle. This is
a discrete form of the thickness of a curve (Gonzalez and Maddocks 1999).
Without the second part the curve folds back on itself between samples,
and the map then reverses over a step or two, as an oscillating map does at
its peaks.

Either rho is maximised at a given step l (a given total length), or l is
maximised at a given rho. The method is sequential linear programming in a
trust region, as in the max-min polish of MCCP (mccp.optimise.polish_maxmin).
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


def _pairs(m):
    return np.triu_indices(m, 2)


def pair_limits(d, a):
    """For pairs at distance d and arc a, the largest rho that satisfies
    (1) for each pair. The right side of (1) increases with rho, so the
    thickness of the curve is the least of these."""
    d, a = np.broadcast_arrays(np.asarray(d, float), np.asarray(a, float))
    out = np.full(d.shape, np.inf)
    near = d <= 2 * a / np.pi            # bound at rho <= 2 a / pi: rho = d
    out[near] = d[near]
    mid = ~near & (d < a)                # solve sin(x) / x = d / a, rho = a / x
    if mid.any():
        r = d[mid] / a[mid]
        lo, hi = np.zeros(r.shape), np.full(r.shape, np.pi / 2)
        for _ in range(50):
            x = 0.5 * (lo + hi)
            big = np.sinc(x / np.pi) > r     # sin(x)/x decreases on (0, pi/2]
            lo, hi = np.where(big, x, lo), np.where(big, hi, x)
        out[mid] = a[mid] / hi
    return out


def thickness(u, priority=1.0, arc=None):
    """Largest rho for which a sampled curve u (M, 3) satisfies (1), for an
    observer of the given priority. The arcs are measured along u unless
    given (the optimiser measures them in normal vision for every
    observer)."""
    m = len(u)
    if m < 3:
        return np.inf
    if arc is None:
        arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(u, axis=0), axis=1))])
    i, j = _pairs(m)
    d = np.linalg.norm(u[i] - u[j], axis=1) / priority
    return float(pair_limits(d, arc[j] - arc[i]).min())


def _state(prob, x, step, rho, bounds):
    """Objective and violations of a curve: (objective, step deviation,
    bound violation, thickness shortfall, thickness, steps)."""
    u = prob.coords(x)
    k = len(prob.prio)
    st = prob.steps(u[0])
    arc = np.concatenate([[0], np.cumsum(st)])
    rho_now = min(thickness(u[o], prob.prio[o], arc) for o in range(k))
    viol = 0.0
    if bounds is not None:
        viol = max(0.0, -float(bounds.slack(u[0], prob.k_l, np.ones(len(x))).min()))
    if step is not None:
        return rho_now, float(np.abs(st - step).max()), viol, 0.0, rho_now, st
    return float(st.min()), float(np.ptp(st)), viol, max(0.0, rho - rho_now), rho_now, st


def optimise(x, step=None, rho=None, observers=(), bounds=None, view=PATH_VIEW, iters=300,
             radius=0.01, active_margin=4.0, penalty=20.0, verbose=False):
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
    k = len(prob.prio)
    nv = 3 * m + 4
    Z, ES, EB, ET = 3 * m, 3 * m + 1, 3 * m + 2, 3 * m + 3
    i_all, j_all = _pairs(m)

    def merit(st):
        return st[0] - penalty * (st[1] + st[2] + st[3])

    cur = _state(prob, x, step, rho, bounds)
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
        # Thickness (1), every observer, pairs near the bound only. The right
        # side p rho s(a / rho) is linearised in the free variable Z, the
        # thickness or the step (on which the arcs depend), as c1 Z + c0:
        # d + n.(J_i dx_i - J_j dx_j) >= p (c1 Z + c0) - e_t.
        arc = np.concatenate([[0], np.cumsum(L)])
        a = arc[j_all] - arc[i_all]
        if rho is None:
            xc = np.minimum(a / cur[4], np.pi / 2)
            c1, c0 = np.sin(xc) - xc * np.cos(xc), a * np.cos(xc)
        else:
            xc = np.minimum(a / rho, np.pi / 2)
            c1 = a / L.mean() * np.cos(xc)
            c0 = rho * np.sin(xc) - a * np.cos(xc)
        z0 = cur[4] if rho is None else L.mean()
        for o in range(k):
            diff = u[o, i_all] - u[o, j_all]
            d = np.linalg.norm(diff, axis=1)
            p = prob.prio[o]
            act = np.flatnonzero(d < p * (c1 * z0 + c0) + active_margin)
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
            T[:, Z] = p * c1[act]
            rows.append(T)
            rhs.append(dd - p * c0[act])
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
        new = _state(prob, x_new, step, rho, bounds)
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
    info = dict(history=history, rho=cur[4], step=float(np.mean(cur[5])),
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
