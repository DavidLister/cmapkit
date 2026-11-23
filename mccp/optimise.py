"""Choice of N colours by maximising the least scaled distance.

Stages (README, Section 3):
  1. starting sets: farthest-point selection on a candidate grid followed by a
     swap search, plus seeded random draws;
  2. refinement: L-BFGS-B on a soft minimum of the scaled distances, with
     penalties for the anchor and background conditions, at increasing
     sharpness;
  3. polish: sequential linear programming on a trust region, maximising the
     exact minimum over all pairs and observers;
  4. spreading: sequential linear programming on the sum of each colour's
     soft minimum, with the exact minimum held.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog, minimize
from scipy.sparse import coo_matrix

from .space import Observer, Space, hex_to_rgb, relative_luminance, rgb_to_hex, to_hex, viewing


@dataclass
class Anchor:
    """A fixed colour that chosen colours must keep clear of.

    clearance: least distance in CAM16-UCS units, multiplied by the radius.
    lightness: least lightness difference, for the background; None otherwise.
    """

    colour: str
    clearance: float
    lightness: float | None = None

    @property
    def rgb(self):
        return hex_to_rgb(self.colour)[0]


@dataclass
class Eval:
    u: np.ndarray      # (k, n, 3) coordinates of chosen colours
    jac: np.ndarray    # (k, n, 3, 3)
    q: np.ndarray      # (k, P) scaled pair distances
    diff: np.ndarray   # (k, P, 3)
    dist: np.ndarray   # (k, P)
    aslack: np.ndarray  # (k, n, M) anchor slack
    adiff: np.ndarray
    adist: np.ndarray
    lslack: np.ndarray  # (k, n) background lightness slack (one-sided)
    bslack: np.ndarray = None  # (2, n) hue-dependent lightness bounds, normal vision
    bgrad: np.ndarray = None   # (2, n, 3) derivative of bslack with respect to u


@dataclass
class Problem:
    n: int
    space: Space
    anchors: list
    radii: np.ndarray
    fixed_rgb: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    fixed_radii: np.ndarray = field(default_factory=lambda: np.zeros(0))
    bounds: object = None  # HueBounds, or None

    def __post_init__(self):
        self.radii = np.asarray(self.radii, dtype=float)
        k = len(self.space.observers)
        m = len(self.anchors)
        self.anchor_d = np.array([a.clearance for a in self.anchors], dtype=float)
        self.anchor_coords = (self.space.coords(np.array([a.rgb for a in self.anchors]))
                              if m else np.zeros((k, 0, 3)))
        bg = [i for i, a in enumerate(self.anchors) if a.lightness is not None]
        self.bg_index = bg[0] if bg else None
        # The lightness condition is stated in ordinary J' units. Coordinates
        # carry J'/K_L, so the requirement is scaled to match.
        self.bg_dj = self.anchors[bg[0]].lightness / self.space.ucs.K_L if bg else 0.0
        # side[i] = +1 if colour i must be lighter than the background, -1 darker.
        self.side = np.full(self.n, -1.0)
        self.fixed_coords = (self.space.coords(self.fixed_rgb) if len(self.fixed_rgb)
                             else np.zeros((k, 0, 3)))
        n, f = self.n, len(self.fixed_rgb)
        i, j = np.triu_indices(n, 1)
        fi, fj = np.meshgrid(np.arange(n), np.arange(f), indexing="ij")
        self.pi = np.concatenate([i, fi.ravel()]).astype(int)
        self.pj = np.concatenate([j, n + fj.ravel()]).astype(int)
        allr = np.concatenate([self.radii, np.asarray(self.fixed_radii, dtype=float)])
        self.prr = allr[self.pi] + allr[self.pj]
        # Per observer: the required spacing of a pair is s * (r_i + r_j) * f_o.
        f = np.array([o.priority for o in self.space.observers], dtype=float)
        if np.any(f <= 0) or np.any(f > 1):
            raise ValueError("Observer priorities must lie in (0, 1].")
        self.prrk = f[:, None] * self.prr[None, :]
        self.priority = f

    def set_sides(self, rgb):
        if self.bounds is not None:
            self.side = self.bounds.side_of(self.space.coords(rgb)[0], self.space.ucs.K_L)
            return
        if self.bg_index is None:
            return
        u = self.space.coords(rgb)[0]
        jb = self.anchor_coords[0, self.bg_index, 0]
        self.side = np.where(u[:, 0] >= jb, 1.0, -1.0)

    def evaluate(self, rgb, with_jac=True):
        if with_jac:
            u, jac = self.space.jacobian(rgb)
        else:
            u, jac = self.space.coords(rgb), None
        ua = np.concatenate([u, self.fixed_coords], axis=1)
        diff = ua[:, self.pi] - ua[:, self.pj]
        dist = np.linalg.norm(diff, axis=-1)
        q = dist / self.prrk
        adiff = u[:, :, None, :] - self.anchor_coords[:, None, :, :]
        adist = np.linalg.norm(adiff, axis=-1)
        aslack = adist - self.anchor_d[None, None, :] * self.radii[None, :, None]
        if self.bg_index is not None:
            dj = u[..., 0] - self.anchor_coords[:, self.bg_index, None, 0]
            lslack = self.side[None, :] * dj - self.bg_dj * self.radii[None, :]
        else:
            lslack = np.zeros(u.shape[:2])
        bslack = bgrad = None
        if self.bounds is not None:
            k_l = self.space.ucs.K_L
            bslack = self.bounds.slack(u[0], k_l, self.side)
            bgrad = self.bounds.slack_grad(u[0], k_l, self.side) if with_jac else None
        return Eval(u, jac, q, diff, dist, aslack, adiff, adist, lslack, bslack, bgrad)

    def score(self, ev):
        return ev.q.min() if ev.q.size else np.inf

    def violation(self, ev):
        v = 0.0
        if ev.aslack.size:
            v = max(v, -ev.aslack.min())
        if self.bg_index is not None:
            v = max(v, -ev.lslack.min())
        if ev.bslack is not None and ev.bslack.size:
            v = max(v, -ev.bslack.min())
        return max(v, 0.0)


# --- gradients -------------------------------------------------------------


def _pair_grad(prob, ev, coef):
    """Gradient wrt chosen sRGB of sum(coef * q), coef of shape (k, P)."""
    n = prob.n
    g = np.zeros((n, 3))
    unit = ev.diff / np.maximum(ev.dist, 1e-12)[..., None] * (coef / prob.prrk)[..., None]
    gi = np.einsum("kpa,kpab->pb", unit, ev.jac[:, prob.pi])
    np.add.at(g, prob.pi, gi)
    free = prob.pj < n
    gj = np.einsum("kpa,kpab->pb", unit[:, free], ev.jac[:, prob.pj[free]])
    np.add.at(g, prob.pj[free], -gj)
    return g


def _softmin(q, beta):
    m = q.min()
    w = np.exp(-beta * (q - m))
    s = w.sum()
    return m - np.log(s) / beta, w / s


def _penalty(prob, ev, mu):
    val = 0.0
    g = np.zeros((prob.n, 3))
    if ev.aslack.size:
        v = np.minimum(ev.aslack, 0.0)
        val += mu * np.sum(v ** 2)
        coef = 2 * mu * v / np.maximum(ev.adist, 1e-12)
        gu = np.sum(coef[..., None] * ev.adiff, axis=2)
        g += np.einsum("kna,knab->nb", gu, ev.jac)
    if prob.bg_index is not None:
        v = np.minimum(ev.lslack, 0.0)
        val += mu * np.sum(v ** 2)
        g += np.einsum("kn,knb->nb", 2 * mu * v * prob.side[None, :], ev.jac[:, :, 0, :])
    if ev.bslack is not None:
        v = np.minimum(ev.bslack, 0.0)
        val += mu * np.sum(v ** 2)
        g += np.einsum("sn,sna,nab->nb", 2 * mu * v, ev.bgrad, ev.jac[0])
    return val, g


# --- stage 1: starting sets --------------------------------------------------


def candidate_grid(steps=24):
    g = np.linspace(0, 1, steps)
    return np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3)


def _capacity(prob, u):
    """Largest radius each candidate can carry under the anchor and
    background conditions, for every observer: (C,)."""
    cap = np.full(u.shape[1], np.inf)
    if prob.anchor_coords.shape[1]:
        d = np.linalg.norm(u[:, :, None, :] - prob.anchor_coords[:, None], axis=-1)
        with np.errstate(divide="ignore"):
            ratio = np.where(prob.anchor_d > 0, d / prob.anchor_d, np.inf)
        cap = np.minimum(cap, ratio.min(axis=(0, 2)))
    if prob.bg_index is not None and prob.bg_dj > 0:
        dj = np.abs(u[..., 0] - prob.anchor_coords[:, prob.bg_index, None, 0])
        cap = np.minimum(cap, (dj / prob.bg_dj).min(axis=0))
    if prob.bounds is not None:
        # The hue-dependent bounds do not scale with the radius.
        inside = prob.bounds.feasible(u[0], prob.space.ucs.K_L)
        cap = np.where(inside, cap, 0.0)
    return cap


def _feasible_candidates(prob, cand):
    """Candidates admissible for at least the smallest radius, their
    coordinates, and their capacities. Raises if some colour has none."""
    u = prob.space.coords(cand)
    cap = _capacity(prob, u)
    for r in np.unique(prob.radii):
        if not np.any(cap >= r):
            raise ValueError(
                f"No admissible colour for radius {r:g}: the anchors "
                f"({', '.join(a.colour for a in prob.anchors)}) with their clearances "
                "exclude every colour on the candidate grid.")
    ok = cap >= (prob.radii.min() if prob.n else 0.0)
    return cand[ok], u[:, ok], cap[ok]


def _nearest_to_set(u_cand, u_set, r_cand, r_set, f=None):
    """Least scaled distance from each candidate to a set: (C,). f holds the
    observer priorities."""
    if u_set.shape[1] == 0:
        return np.full(u_cand.shape[1], np.inf)
    d = np.linalg.norm(u_cand[:, :, None, :] - u_set[:, None, :, :], axis=-1)
    d = d / (r_cand + r_set[None, None, :])
    if f is not None:
        d = d / f[:, None, None]
    return d.min(axis=(0, 2))


def farthest_point(prob, uc, cap):
    """Greedy farthest-point selection; returns candidate indices.

    Colour i may only take candidates whose capacity covers its radius. The
    first colour, when there are no fixed members, is the candidate farthest
    from the anchors relative to their clearances."""
    fr = np.asarray(prob.fixed_radii, float)
    chosen = []
    taken = np.zeros(uc.shape[1], bool)
    for i in range(prob.n):
        r = prob.radii[i]
        u_set = np.concatenate([uc[:, chosen], prob.fixed_coords], axis=1)
        r_set = np.concatenate([prob.radii[:i], fr])
        score = _nearest_to_set(uc, u_set, r, r_set, prob.priority)
        if np.all(np.isinf(score)):
            score = cap.copy()
        score[(cap < r) | taken] = -np.inf
        k = int(np.argmax(score))
        chosen.append(k)
        taken[k] = True
    return np.array(chosen)


def swap_search(prob, uc, cap, idx, sweeps=20):
    """Move each colour in turn to the admissible candidate farthest from
    the rest, until a sweep brings no gain."""
    idx = idx.copy()
    fr = np.asarray(prob.fixed_radii, float)
    for _ in range(sweeps):
        improved = False
        for i in range(prob.n):
            others = np.delete(idx, i)
            u_set = np.concatenate([uc[:, others], prob.fixed_coords], axis=1)
            r_set = np.concatenate([np.delete(prob.radii, i), fr])
            near = _nearest_to_set(uc, u_set, prob.radii[i], r_set, prob.priority)
            near[others] = -np.inf
            near[cap < prob.radii[i]] = -np.inf
            cur = near[idx[i]]
            k = int(np.argmax(near))
            if near[k] > cur * (1 + 1e-9):
                idx[i] = k
                improved = True
        if not improved:
            break
    return idx


def random_start(prob, cap, rng):
    idx = []
    for r in prob.radii:
        pool = np.flatnonzero(cap >= r)
        idx.append(int(rng.choice(pool)))
    return np.array(idx)


# --- stage 2: soft-minimum refinement ----------------------------------------


def refine_softmin(prob, x0, rel_betas=(4.0, 16.0, 64.0), mu=10.0, maxiter=200):
    x = x0.ravel().copy()
    for b in rel_betas:
        s0 = max(prob.score(prob.evaluate(x.reshape(-1, 3), with_jac=False)), 1e-3)
        beta = b / s0

        def f(xf):
            ev = prob.evaluate(xf.reshape(-1, 3))
            sm, w = _softmin(ev.q, beta)
            pv, pg = _penalty(prob, ev, mu)
            return -sm + pv, (-_pair_grad(prob, ev, w) + pg).ravel()

        x = minimize(f, x, jac=True, method="L-BFGS-B", bounds=[(0, 1)] * x.size,
                     options=dict(maxiter=maxiter)).x
    return x.reshape(-1, 3)


# --- linearised constraints --------------------------------------------------


def _linear_rows(prob, ev, pair_mask, anchor_mask, light_mask, bound_mask=None):
    """Sparse rows a such that each constraint value changes by a @ dx."""
    n = prob.n
    rows, cols, vals = [], [], []
    vals_c = []
    r = 0
    o_idx, p_idx = np.nonzero(pair_mask)
    if len(o_idx):
        unit = (ev.diff[o_idx, p_idx] / np.maximum(ev.dist[o_idx, p_idx], 1e-12)[:, None]
                / prob.prrk[o_idx, p_idx][:, None])
        i = prob.pi[p_idx]
        j = prob.pj[p_idx]
        gi = np.einsum("sa,sab->sb", unit, ev.jac[o_idx, i])
        rr = r + np.arange(len(o_idx))
        for b in range(3):
            rows.append(rr); cols.append(3 * i + b); vals.append(gi[:, b])
        free = j < n
        gj = np.einsum("sa,sab->sb", unit[free], ev.jac[o_idx[free], j[free]])
        for b in range(3):
            rows.append(rr[free]); cols.append(3 * j[free] + b); vals.append(-gj[:, b])
        vals_c.append(ev.q[o_idx, p_idx])
        r += len(o_idx)
    n_pair = r
    o_idx, i_idx, m_idx = np.nonzero(anchor_mask)
    if len(o_idx):
        unit = (ev.adiff[o_idx, i_idx, m_idx]
                / np.maximum(ev.adist[o_idx, i_idx, m_idx], 1e-12)[:, None])
        g = np.einsum("sa,sab->sb", unit, ev.jac[o_idx, i_idx])
        rr = r + np.arange(len(o_idx))
        for b in range(3):
            rows.append(rr); cols.append(3 * i_idx + b); vals.append(g[:, b])
        vals_c.append(ev.aslack[o_idx, i_idx, m_idx])
        r += len(o_idx)
    o_idx, i_idx = np.nonzero(light_mask)
    if len(o_idx):
        g = prob.side[i_idx][:, None] * ev.jac[o_idx, i_idx, 0, :]
        rr = r + np.arange(len(o_idx))
        for b in range(3):
            rows.append(rr); cols.append(3 * i_idx + b); vals.append(g[:, b])
        vals_c.append(ev.lslack[o_idx, i_idx])
        r += len(o_idx)
    if bound_mask is not None:
        s_idx, i_idx = np.nonzero(bound_mask)
        if len(s_idx):
            g = np.einsum("sa,sab->sb", ev.bgrad[s_idx, i_idx], ev.jac[0, i_idx])
            rr = r + np.arange(len(s_idx))
            for b in range(3):
                rows.append(rr); cols.append(3 * i_idx + b); vals.append(g[:, b])
            vals_c.append(ev.bslack[s_idx, i_idx])
            r += len(s_idx)
    A = coo_matrix((np.concatenate(vals) if vals else [],
                    (np.concatenate(rows) if rows else [], np.concatenate(cols) if cols else [])),
                   shape=(r, 3 * n)).tocsr()
    c = np.concatenate(vals_c) if vals_c else np.zeros(0)
    return A, c, n_pair


def _masks(prob, ev, q_limit, slack_limit):
    pair = ev.q < q_limit
    anchor = ev.aslack < slack_limit if ev.aslack.size else np.zeros(ev.aslack.shape, bool)
    light = (ev.lslack < slack_limit if prob.bg_index is not None
             else np.zeros(ev.lslack.shape, bool))
    bound = ev.bslack < slack_limit if ev.bslack is not None else None
    return pair, anchor, light, bound


# --- stage 3: exact max-min by sequential linear programming -----------------


def polish_maxmin(prob, rgb, radius=0.05, min_radius=1e-5, max_iter=300, elastic=100.0):
    x = rgb.ravel().copy()
    ev = prob.evaluate(x.reshape(-1, 3))
    merit = prob.score(ev) - elastic * prob.violation(ev)
    for _ in range(max_iter):
        if radius < min_radius:
            break
        s = prob.score(ev)
        jmax = np.abs(ev.jac).max()
        reach = 2 * np.sqrt(3) * jmax * radius  # largest change of a distance
        pm, am, lm, bm = _masks(prob, ev, s + reach / prob.prrk.min(), reach)
        A, c, n_pair = _linear_rows(prob, ev, pm, am, lm, bm)
        n_var = 3 * prob.n
        # Variables: dx (n_var), t, e (elastic violation of anchor/light rows).
        # Pair rows:   q + a dx >= t      ->  -a dx + t       <= q
        # Other rows:  slack + a dx >= -e ->  -a dx - e       <= slack
        A_ub = np.zeros((A.shape[0], n_var + 2))
        A_ub[:, :n_var] = -A.toarray()
        A_ub[:n_pair, n_var] = 1.0
        A_ub[n_pair:, n_var + 1] = -1.0
        lo = np.maximum(-radius, -x)
        hi = np.minimum(radius, 1 - x)
        bounds = list(zip(lo, hi)) + [(None, None), (0, None)]
        cost = np.zeros(n_var + 2)
        cost[n_var] = -1.0
        cost[n_var + 1] = elastic
        res = linprog(cost, A_ub=A_ub, b_ub=c, bounds=bounds, method="highs")
        if res.status != 0:
            radius *= 0.5
            continue
        x_new = np.clip(x + res.x[:n_var], 0, 1)
        ev_new = prob.evaluate(x_new.reshape(-1, 3))
        merit_new = prob.score(ev_new) - elastic * prob.violation(ev_new)
        if merit_new > merit + 1e-10:
            gain = merit_new - merit
            x, ev, merit = x_new, ev_new, merit_new
            radius = min(radius * 1.5, 0.2)
            if gain < 1e-7:
                break
        else:
            radius *= 0.5
    return x.reshape(-1, 3)


# --- stage 4: spreading the colours that are not binding ---------------------


def _spread_objective(prob, ev, beta):
    """Sum over observers and colours of each colour's soft minimum."""
    n = prob.n
    total = 0.0
    coef = np.zeros_like(ev.q)
    for o in range(ev.q.shape[0]):
        q = ev.q[o]
        m = q.min()
        e = np.exp(-beta * (q - m))
        z = np.zeros(n)
        np.add.at(z, prob.pi, e)
        free = prob.pj < n
        np.add.at(z, prob.pj[free], e[free])
        z = np.maximum(z, 1e-300)
        total += np.sum(m - np.log(z) / beta)
        c = e / z[prob.pi]
        c[free] += e[free] / z[prob.pj[free]]
        coef[o] = c
    return total, coef


def spread(prob, rgb, s_star, beta_rel=3.0, radius=0.02, min_radius=1e-5, max_iter=200):
    x = rgb.ravel().copy()
    beta = beta_rel / max(s_star, 1e-6)
    floor = s_star * (1 - 1e-6)
    ev = prob.evaluate(x.reshape(-1, 3))
    obj, coef = _spread_objective(prob, ev, beta)
    for _ in range(max_iter):
        if radius < min_radius:
            break
        jmax = np.abs(ev.jac).max()
        reach = 2 * np.sqrt(3) * jmax * radius
        pm, am, lm, bm = _masks(prob, ev, floor + reach / prob.prrk.min(), reach)
        A, c, n_pair = _linear_rows(prob, ev, pm, am, lm, bm)
        g = _pair_grad(prob, ev, coef).ravel()
        b_ub = c.copy()
        b_ub[:n_pair] -= floor
        lo = np.maximum(-radius, -x)
        hi = np.minimum(radius, 1 - x)
        res = linprog(-g, A_ub=-A.toarray() if A.shape[0] else None,
                      b_ub=b_ub if A.shape[0] else None,
                      bounds=list(zip(lo, hi)), method="highs")
        if res.status != 0:
            radius *= 0.5
            continue
        x_new = np.clip(x + res.x, 0, 1)
        ev_new = prob.evaluate(x_new.reshape(-1, 3))
        obj_new, coef_new = _spread_objective(prob, ev_new, beta)
        ok = prob.score(ev_new) >= floor and prob.violation(ev_new) <= prob.violation(ev) + 1e-9
        if ok and obj_new > obj + 1e-9:
            x, ev, obj, coef = x_new, ev_new, obj_new, coef_new
            radius = min(radius * 1.5, 0.1)
        else:
            radius *= 0.5
    return x.reshape(-1, 3)


# --- driver ------------------------------------------------------------------


def power_mean(q, p):
    """Power mean of the scaled distances with exponent -p, and its
    derivative with respect to q. p = inf gives the minimum."""
    if q.size == 0:
        return np.inf, np.zeros_like(q)
    q = np.maximum(q, 1e-9)
    m = q.min()
    if not np.isfinite(p):
        return m, None
    r = m / q  # in (0, 1]
    a = np.mean(r ** p)
    value = m * a ** (-1.0 / p)
    grad = (a ** (-1.0 / p - 1.0)) * (r ** (p + 1.0)) / q.size
    return value, grad


def refine_power(prob, x0, p, mus=(10.0, 100.0, 1000.0), maxiter=300):
    """L-BFGS-B on the power mean, with penalties raised in turn until the
    anchor, background and bound conditions hold."""
    x = x0.ravel().copy()
    for mu in mus:
        def f(xf):
            ev = prob.evaluate(xf.reshape(-1, 3))
            val, gq = power_mean(ev.q, p)
            pv, pg = _penalty(prob, ev, mu)
            return -val + pv, (-_pair_grad(prob, ev, gq) + pg).ravel()

        x = minimize(f, x, jac=True, method="L-BFGS-B", bounds=[(0, 1)] * x.size,
                     options=dict(maxiter=maxiter)).x
        if prob.violation(prob.evaluate(x.reshape(-1, 3), with_jac=False)) < FEAS_TOL:
            break
    return x.reshape(-1, 3)


def solve_power(prob, p, starts=8, seed=0, grid=24):
    """Maximise the power mean of the scaled distances (exponent -p)."""
    cand, uc, cap = _feasible_candidates(prob, candidate_grid(grid))
    rng = np.random.default_rng(seed)
    swapped = swap_search(prob, uc, cap, farthest_point(prob, uc, cap))
    inits = [("swap", cand[swapped])]
    for k in range(starts - 1):
        inits.append((f"random {k + 1}", cand[random_start(prob, cap, rng)]))
    best = cand[swapped]
    prob.set_sides(best)
    best_side = prob.side.copy()
    ev = prob.evaluate(best, False)
    best_v = power_mean(ev.q, p)[0] if prob.violation(ev) < FEAS_TOL else -np.inf
    log = dict(starts=[])
    for name, x0 in inits:
        prob.set_sides(x0)
        x = refine_power(prob, x0, p)
        ev = prob.evaluate(x, False)
        v = power_mean(ev.q, p)[0] if prob.violation(ev) < FEAS_TOL else -np.inf
        log["starts"].append(dict(start=name, value=v))
        if v > best_v:
            best, best_v, best_side = x, v, prob.side.copy()
    prob.side = best_side
    return best, log


def round_repair(prob, rgb, sweeps=4, p=np.inf):
    """Round to 8-bit values, then move single colours by one step in each
    channel while this reduces the violation or raises the least distance."""
    x = np.round(np.clip(rgb, 0, 1) * 255)
    steps = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)
                      if (a, b, c) != (0, 0, 0)])

    def merit(xx):
        ev = prob.evaluate(xx / 255, with_jac=False)
        v = prob.violation(ev)
        return (-v if v > FEAS_TOL else 0.0, power_mean(ev.q, p)[0])

    cur = merit(x)
    for _ in range(sweeps):
        improved = False
        for i in range(prob.n):
            best_step, best_m = None, cur
            for s in steps:
                y = x.copy()
                y[i] = np.clip(y[i] + s, 0, 255)
                m = merit(y)
                if m > best_m:
                    best_step, best_m = y, m
            if best_step is not None:
                x, cur = best_step, best_m
                improved = True
        if not improved:
            break
    return x / 255


def solve(prob, starts=8, polish_top=3, seed=0, grid=24, do_spread=True):
    """Return the best sRGB array (n, 3) found, and a log of the stages."""
    cand, uc, cap = _feasible_candidates(prob, candidate_grid(grid))
    if len(cand) < prob.n:
        raise ValueError(f"Only {len(cand)} admissible candidates for {prob.n} colours; "
                         "use a finer grid or looser anchors.")
    rng = np.random.default_rng(seed)
    greedy = farthest_point(prob, uc, cap)
    swapped = swap_search(prob, uc, cap, greedy)
    inits = [("swap", cand[swapped])]
    for k in range(starts - 1):
        inits.append((f"random {k + 1}", cand[random_start(prob, cap, rng)]))
    log = dict(greedy=prob.score(prob.evaluate(cand[greedy], False)),
               swap=prob.score(prob.evaluate(cand[swapped], False)), starts=[])
    refined = []
    for name, x0 in inits:
        prob.set_sides(x0)
        x = refine_softmin(prob, x0)
        ev = prob.evaluate(x, False)
        refined.append((prob.score(ev) - 100 * prob.violation(ev), name, x, prob.side.copy()))
    refined.sort(key=lambda r: -r[0])
    # The swap-search start lies on grid points admissible for each colour's
    # radius, so it is a feasible answer to fall back on.
    x_swap = cand[swapped]
    prob.set_sides(x_swap)
    ev = prob.evaluate(x_swap, False)
    best, best_side = x_swap, prob.side.copy()
    best_s = prob.score(ev) if prob.violation(ev) < FEAS_TOL else -np.inf
    for merit, name, x, side in refined[:polish_top]:
        prob.side = side
        x = polish_maxmin(prob, x)
        ev = prob.evaluate(x, False)
        s = prob.score(ev) if prob.violation(ev) < FEAS_TOL else -np.inf
        log["starts"].append(dict(start=name, refined=merit, polished=s))
        if s > best_s:
            best, best_s, best_side = x, s, side
    if not np.isfinite(best_s):
        raise RuntimeError("No start satisfied the anchor and background conditions.")
    prob.side = best_side
    if do_spread and prob.n > 2:
        best = spread(prob, best, best_s)
    log["continuous_scale"] = float(prob.score(prob.evaluate(best, False)))
    return best, log


# --- public interface --------------------------------------------------------


DEFAULT_BACKGROUND = "#ffffff"
FEAS_TOL = 1e-4  # CAM16-UCS units; far below the 8-bit quantisation step


def default_anchors(background=DEFAULT_BACKGROUND, text=None, background_clearance=20.0,
                    background_lightness=25.0, text_clearance=15.0):
    """White (or given) background and a text colour of opposite lightness.

    background_lightness=25 matches the lightest colour of matplotlib's tab10
    on white (contrast ratio about 2:1). WCAG 2.1 asks 3:1 for graphical
    objects, which corresponds to about 37 on white."""
    background = to_hex(background)
    if text is None:
        text = "#000000" if relative_luminance(hex_to_rgb(background))[0] > 0.18 else "#ffffff"
    return [Anchor(background, background_clearance, background_lightness),
            Anchor(to_hex(text), text_clearance)]


@dataclass
class Palette:
    hex: list
    rgb: np.ndarray
    min_distance: float
    scale: float
    diagnostics: dict

    def __len__(self):
        return len(self.hex)

    def __iter__(self):
        return iter(self.hex)


# Default simulated observers of the 'srgb' mode: deuteranopia and protanopia
# guaranteed 0.6 of the common spacing, tritanopia 0.2. At N = 10 this keeps
# about 0.88 of the normal-vision spacing.
SRGB_OBSERVERS = (Observer("deutan", 1.0, 0.6), Observer("protan", 1.0, 0.6),
                  Observer("tritan", 1.0, 0.2))


def make_problem(n, background=DEFAULT_BACKGROUND, anchors=None, radii=None, observers=None,
                 preset="screen", fixed=(), fixed_radii=None, ucs="UCS", lightness_weight=None,
                 mode=None):
    if n < 0:
        raise ValueError("n must be non-negative")
    background = to_hex(background)
    bounds = None
    if mode == "srgb":
        # Calibrated mode: lightness weighted, and lightness bounds by hue in
        # place of the single background lightness condition.
        lightness_weight = 0.77 if lightness_weight is None else lightness_weight
        bounds = "srgb"
        if anchors is None:
            light_bg = relative_luminance(hex_to_rgb(background))[0] > 0.18
            anchors = [Anchor(background, 20.0),
                       Anchor("#000000" if light_bg else "#ffffff", 15.0)]
        if observers is None:
            observers = SRGB_OBSERVERS
    elif mode is not None:
        raise ValueError(f"Unknown mode {mode!r}")
    observers = () if observers is None else observers
    view = viewing(preset, background, ucs=ucs, lightness_weight=lightness_weight)
    obs = (Observer(),) + tuple(Observer(*o) if isinstance(o, tuple) else o for o in observers)
    space = Space(view, obs)
    anchors = default_anchors(background) if anchors is None else anchors
    for a in anchors:
        a.colour = to_hex(a.colour)
        if a.clearance < 0 or (a.lightness is not None and a.lightness < 0):
            raise ValueError("Anchor clearances must be non-negative.")
    radii = np.ones(n) if radii is None else np.asarray(radii, float)
    if radii.shape != (n,) or np.any(radii <= 0):
        raise ValueError("radii must be n positive numbers.")
    fixed = [to_hex(c) for c in fixed]
    fixed_rgb = hex_to_rgb(fixed) if fixed else np.zeros((0, 3))
    fixed_radii = (np.ones(len(fixed)) if fixed_radii is None
                   else np.asarray(fixed_radii, float))
    if fixed_radii.shape != (len(fixed),) or np.any(fixed_radii <= 0):
        raise ValueError("fixed_radii must be positive, one per fixed colour.")
    if bounds == "srgb":
        from .bounds import bounds_for
        j_bg = float(space.ucs(hex_to_rgb(background))[0, 0]) * space.ucs.K_L
        bounds = bounds_for(background, j_bg)
    return Problem(n, space, anchors, radii, fixed_rgb, fixed_radii, bounds)


def palette(n, background=DEFAULT_BACKGROUND, anchors=None, radii=None, observers=None,
            preset="screen", fixed=(), fixed_radii=None, starts=8, seed=0, grid=24,
            order=None, ucs="UCS", lightness_weight=None, mode="auto", power=np.inf,
            use_cache=True):
    """Choose n colours. See the README for the formulation.

    mode: 'srgb' (calibrated lightness bounds by hue, lightness weighted,
    deutan and protan guaranteed 0.6 of the spacing and tritan 0.2),
    'standard' (single background lightness condition, normal vision only
    unless observers are given), or 'auto' (the default, currently 'srgb').
    The hue bounds of 'srgb' are calibrated on white, black and #333333 and
    interpolated in background L* elsewhere; diagnostics['bounds'] says which.

    Colours are returned as 8-bit sRGB, and all diagnostics refer to the
    colours as returned."""
    if mode == "auto":
        mode = "srgb"
    if use_cache:
        cached = _from_cache(n, background, anchors, radii, observers, preset, fixed,
                             fixed_radii, starts, seed, grid, ucs, lightness_weight, mode, power)
        if cached is not None:
            prob = make_problem(n, background, None, None, None, preset, (), None, ucs,
                                lightness_weight, mode)
            rgb = hex_to_rgb(cached)
            if order is not None:
                from .order import order_indices
                rgb = rgb[order_indices(rgb, prob.space, order)]
            prob.set_sides(rgb)
            diag = diagnose(prob, rgb)
            diag["log"] = {"source": "precomputed"}
            return Palette(rgb_to_hex(rgb), rgb, diag["min_distance"], diag["scale"], diag)
    prob = make_problem(n, background, anchors, radii, observers, preset, fixed, fixed_radii,
                        ucs, lightness_weight, None if mode == "standard" else mode)
    if n == 0:
        return Palette([], np.zeros((0, 3)), np.inf, np.inf, {})
    if order is not None and np.ptp(prob.radii) > 0:
        raise ValueError("order= would separate colours from their radii; "
                         "order the series yourself when radii differ.")
    if n == 1 and not len(prob.fixed_rgb):
        cand, uc, cap = _feasible_candidates(prob, candidate_grid(grid))
        rgb, log = cand[farthest_point(prob, uc, cap)], {}
        prob.set_sides(rgb)
    elif np.isfinite(power):
        rgb, log = solve_power(prob, power, starts=starts, seed=seed, grid=grid)
    else:
        rgb, log = solve(prob, starts=starts, seed=seed, grid=grid)
    rgb = round_repair(prob, rgb, p=power)
    if order is not None:
        from .order import order_indices
        rgb = rgb[order_indices(rgb, prob.space, order)]
        prob.set_sides(rgb)
    diag = diagnose(prob, rgb)
    diag["log"] = log
    return Palette(rgb_to_hex(rgb), rgb, diag["min_distance"], diag["scale"], diag)


def diagnose(prob, rgb):
    ev = prob.evaluate(rgb, with_jac=False)
    out = {}
    if ev.q.size:
        s = ev.q.min()
        out["scale"] = float(s)
        out["min_distance"] = float(ev.dist.min())
        bind = np.argwhere(ev.q <= s * (1 + 1e-3))
        out["binding_pairs"] = [(int(prob.pi[p]), int(prob.pj[p]), str(prob.space.observers[o]))
                                for o, p in bind]
        out["scale_by_observer"] = {str(o): float(v)
                                    for o, v in zip(prob.space.observers, ev.q.min(axis=1))}
    else:
        out["scale"] = out["min_distance"] = float("inf")
    if ev.aslack.size:
        out["anchor_distance"] = {a.colour: ev.adist[0, :, m].round(2).tolist()
                                  for m, a in enumerate(prob.anchors)}
    if prob.bg_index is not None:
        jb = prob.anchor_coords[0, prob.bg_index, 0]
        k_l = prob.space.ucs.K_L
        out["background_lightness_difference"] = (k_l * np.abs(ev.u[0, :, 0] - jb)).round(2).tolist()
    if prob.bounds is not None:
        out["bounds"] = prob.bounds.source
    if ev.bslack is not None:
        out["lightness_bound_slack"] = ev.bslack.min(axis=0).round(2).tolist()
    out["max_violation"] = float(prob.violation(ev))
    return out


# --- precomputed palettes ------------------------------------------------------

_CACHE = None


def cache_settings():
    """The default arguments that precomputed palettes assume."""
    return dict(mode="srgb", preset="screen", starts=8, seed=0, grid=24, ucs="UCS",
                lightness_weight=None, power="inf")


def _load_cache():
    global _CACHE
    if _CACHE is None:
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "data", "palettes.json")
        try:
            with open(path) as f:
                _CACHE = json.load(f)
        except FileNotFoundError:
            _CACHE = {}
    return _CACHE


def _from_cache(n, background, anchors, radii, observers, preset, fixed, fixed_radii, starts,
                seed, grid, ucs, lightness_weight, mode, power):
    """Hex colours of a precomputed palette, or None if the arguments are not
    all at the defaults for which palettes were precomputed."""
    from . import __version__
    if (anchors is not None or radii is not None or observers is not None or fixed
            or fixed_radii is not None or preset != "screen" or starts != 8 or seed != 0
            or grid != 24 or ucs != "UCS" or lightness_weight is not None or mode != "srgb"
            or np.isfinite(power)):
        return None
    cache = _load_cache()
    if cache.get("version") != __version__:
        return None
    entry = cache.get("palettes", {}).get(to_hex(background), {}).get(str(n))
    return entry["hex"] if entry else None
