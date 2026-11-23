"""Colour maps along a path through a set of colours.

The colours (for example a large MCCP palette) are put in the order of a
short open path, joined by a curve in CAM16-UCS, and the curve is sampled at
equal arc length, so that equal steps in the data give equal colour
differences. Three joins are offered:

- 'linear': straight segments, with a corner at every colour;
- 'spline': the natural cubic spline through the colours, the interpolating
  curve of least bending energy (the integral of the squared second
  derivative);
- 'catmull-rom': the centripetal Catmull-Rom spline, which bends less
  sharply than straight segments but, unlike the natural spline, cannot
  overshoot into loops or cusps.

Samples that fall outside the sRGB gamut are clipped, and reported.
"""

import numpy as np

from dataclasses import replace

from ..space import CAM16UCS, linear_to_srgb
from .maps import IMAGE_VIEW

# Steps are measured with the lightness weight of MCCP's calibrated modes, so
# that the path is uniform in the measure its colours were spaced in.
PATH_VIEW = replace(IMAGE_VIEW, lightness_weight=0.77)


def short_path(d, starts=12):
    """Order of a short open path through points with distance matrix d:
    nearest-neighbour construction from several starts, then 2-opt."""
    from ..mccp.order import _path_length, _two_opt
    n = len(d)
    if n < 3:
        return list(range(n))
    best, best_len = None, np.inf
    for s in np.unique(np.linspace(0, n - 1, min(starts, n)).astype(int)):
        order, left = [int(s)], set(range(n)) - {int(s)}
        while left:
            nxt = min(left, key=lambda k: d[order[-1], k])
            order.append(nxt)
            left.remove(nxt)
        order = _two_opt(d, order, 1.0)
        length = _path_length(d, order)
        if length < best_len:
            best, best_len = order, length
    return best


def _catmull_rom(u, per=32, alpha=0.5):
    """Centripetal Catmull-Rom through the rows of u, `per` samples per span."""
    p = np.vstack([2 * u[0] - u[1], u, 2 * u[-1] - u[-2]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** alpha
        t2 = t1 + np.linalg.norm(p2 - p1) ** alpha
        t3 = t2 + np.linalg.norm(p3 - p2) ** alpha
        t = np.linspace(t1, t2, per, endpoint=False)[:, None]
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(u[-1:])
    return np.vstack(out)


def _dense_curve(u, join, per=32):
    if join == "linear":
        s = np.linspace(0, len(u) - 1, (len(u) - 1) * per + 1)
        return np.stack([np.interp(s, np.arange(len(u)), u[:, k]) for k in range(3)], -1)
    if join == "spline":
        from scipy.interpolate import CubicSpline
        chord = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(u, axis=0), axis=1))])
        cs = CubicSpline(chord, u, bc_type="natural")
        return cs(np.linspace(0, chord[-1], (len(u) - 1) * per + 1))
    if join == "catmull-rom":
        return _catmull_rom(u, per)
    raise ValueError(f"Unknown join {join!r}")


class PathMap:
    """A colour map along a path through `rgb` (n, 3), in the order given.

    join: 'linear', 'spline' or 'catmull-rom'. The map has n_lut entries at
    equal arc length in CAM16-UCS under `view`."""

    def __init__(self, rgb, join="linear", view=PATH_VIEW, n_lut=4096):
        self.ucs = CAM16UCS(view)
        dense = _dense_curve(self.ucs(np.asarray(rgb, float)), join)
        arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
        t = np.linspace(0, arc[-1], n_lut)
        self.u = np.stack([np.interp(t, arc, dense[:, k]) for k in range(3)], -1)
        lin = self.ucs.to_linear(self.u)
        self.out_of_gamut = float(np.mean(np.any((lin < -1e-6) | (lin > 1 + 1e-6), axis=1)))
        self.lut = linear_to_srgb(lin)
        # Length of the colours actually shown, after clipping.
        shown = self.ucs(self.lut)
        self.length = float(np.linalg.norm(np.diff(shown, axis=0), axis=1).sum())
        self.join = join

    def __call__(self, t):
        idx = np.clip(np.round(np.asarray(t, float) * (len(self.lut) - 1)), 0,
                      len(self.lut) - 1).astype(int)
        return self.lut[idx]


def from_palette(rgb, join="linear", view=PATH_VIEW, dark_first=True):
    """PathMap through the colours of a palette, put in the order of a short
    path, starting from the darker end."""
    ucs = CAM16UCS(view)
    u = ucs(np.asarray(rgb, float))
    order = short_path(np.linalg.norm(u[:, None] - u[None], axis=-1))
    if dark_first and u[order[0], 0] > u[order[-1], 0]:
        order = order[::-1]
    return PathMap(np.asarray(rgb, float)[order], join, view)


def turning(u):
    """Angle in degrees between successive steps of a sampled curve u (n, 3):
    large values are corners."""
    d = np.diff(u, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    return np.degrees(np.arccos(np.clip((d[:-1] * d[1:]).sum(1), -1, 1)))


def self_approach(u, window=0.05, stride=8):
    """For each sample of a curve u (n, 3), the least distance to any part of
    the curve more than `window` (a fraction of the data range) away."""
    sub = u[::stride]
    m = len(sub)
    d = np.linalg.norm(sub[:, None] - sub[None], axis=-1)
    idx = np.arange(m)
    far = np.abs(idx[:, None] - idx[None]) > window * m
    return np.where(far, d, np.inf).min(1)
