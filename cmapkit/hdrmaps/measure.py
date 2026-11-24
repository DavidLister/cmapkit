"""Measures of a colour map for observers of normal and deficient colour vision.

A map is given as sRGB samples at equal steps of the data. For each
observer the samples are simulated (Machado et al. 2009, at full severity)
and placed in CAM16-UCS under PATH_VIEW, and the following are found.

- Length L, the sum of the colour differences between successive samples.
- Speed, the colour difference per unit of data, averaged over windows of
  1/64 of the range so that the quantisation of a table does not show as
  speed. Its ratios max/min and p95/p5 (the 95th to the 5th percentile)
  measure the uniformity of contrast; a perfectly uniform map has 1.
- Separation, the least colour difference between two parts of the map at
  least 10 % of the data range apart. A map whose separation is near zero
  shows two distinct data values in the same colour.
"""

import numpy as np

from ..space import Observer, Space
from .paths import PATH_VIEW

OBSERVERS = {"normal": Observer(), "protan": Observer("protan"),
             "deutan": Observer("deutan"), "tritan": Observer("tritan")}


def _resample(rgb, m):
    rgb = np.asarray(rgb, float)
    s = np.linspace(0, len(rgb) - 1, m)
    return np.stack([np.interp(s, np.arange(len(rgb)), rgb[:, k]) for k in range(3)], -1)


def _separation(u, apart, chunk=500):
    """Least distance between rows of u more than apart * len(u) apart."""
    m = len(u)
    best = np.inf
    for a in range(0, m, chunk):
        rows = np.arange(a, min(a + chunk, m))
        d = np.linalg.norm(u[rows, None] - u[None], axis=-1)
        far = np.abs(rows[:, None] - np.arange(m)[None]) > apart * m
        if far.any():
            best = min(best, float(d[far].min()))
    return best


def assess(rgb, view=PATH_VIEW, samples=1024, window=1 / 64, apart=0.1, sep_samples=3000):
    """Measures of the map rgb (n, 3) for each observer in OBSERVERS.

    Returns a dict observer -> dict(length, speed_max_min, speed_p95_p5,
    separation)."""
    space = Space(view, tuple(OBSERVERS.values()))
    u = space.coords(_resample(rgb, samples))
    us = space.coords(_resample(rgb, sep_samples))
    w = max(1, int(round(window * (samples - 1))))
    out = {}
    for k, name in enumerate(OBSERVERS):
        d = np.linalg.norm(np.diff(u[k], axis=0), axis=1)
        v = np.convolve(d, np.ones(w) / w, mode="valid") * len(d)
        p5, p95 = np.percentile(v, [5, 95])
        sep = _separation(us[k], apart)
        out[name] = dict(length=float(d.sum()), speed_max_min=float(v.max() / v.min()),
                         speed_p95_p5=float(p95 / p5), separation=float(sep))
    return out
