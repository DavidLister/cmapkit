"""Noise of an image, and the length of colour map that it supports.

1. Quantities. Let t in [0, 1] be the image after scaling (the square-root
scale makes shot noise equal at every level), and let sigma(s) be the
standard deviation of the noise in t after a Gaussian blur of s pixels. The
dynamic range in units of the noise is

    D(s) = 1 / sigma(s),                                               (1)

the number of noise standard deviations that fit across the range of the
data. A colour map of length L (colour difference in CAM16-UCS under the
map's viewing conditions) traversed at uniform speed shows a change dt in
the data as a colour difference L dt, and so shows the noise as a colour
fluctuation of standard deviation L sigma(s). We ask that this fluctuation
equal a threshold T (colour difference per noise standard deviation): below
it the map wastes some of the detail in the data, above it the noise grain
is plainly visible. The length the image supports is therefore

    L = T D(s),                                                        (2)

and L / T is the number of noise steps the map shows across its range.
Equation (2) is read in either direction: for an image and a blur it gives
the length; for a map of given length it gives the blur.

2. Estimate of the noise. sigma(0) is found from the image by the method of
Immerkaer (1996): the image is filtered with the 3 x 3 mask that is the outer
product of (1, -2, 1) with itself, which removes planes and nearly removes
smooth signal, and the median absolute response gives the noise robustly
against edges. For white noise, sigma(s) = sigma(0) |k_s|, where |k_s| is the
root sum of squares of the blur kernel. The noise of the test images is close
to white; it is slightly correlated along the scan line, which this
estimate does not account for.

3. Length available. A curve that keeps a distance rho between its distant
parts (curve.thickness) is a tube of diameter rho. In a volume V large in
every direction compared with rho, the length of such a tube is about
c V / rho^2. Within the lightness limits of an image the volume is a shell
whose thickness h in lightness is comparable with the rho of interest, and
the tube then lies in it as a curve in a surface, so that

    L rho = K,                                                         (3)

with K about V / h. For the limits of bounds.image_bounds and the curves of
curve.optimise, K is about 13 600 for rho from 7 to 27 (N from 20 to 200).
Equations (2) and (3) together give the thickness that a map of the
required length can have, rho = K / (T D), and the largest D for which a
chosen least thickness can be kept.

Reference: J. Immerkaer, Fast noise variance estimation, Computer Vision and
Image Understanding 64 (1996) 300-302.
"""

import numpy as np

from .paths import PATH_VIEW


def noise_sd(t):
    """Standard deviation of white noise in an image t, by the method of
    Immerkaer (1996) with a median in place of the mean."""
    from scipy.ndimage import convolve
    l = np.array([1.0, -2.0, 1.0])
    r = convolve(np.asarray(t, float), np.outer(l, l))[2:-2, 2:-2]
    # The mask's root sum of squares is 6; median |x| = 0.6745 sd for a normal.
    return float(np.median(np.abs(r)) / (0.6745 * 6.0))


def kernel_gain(s):
    """|k_s|: factor by which a Gaussian blur of s pixels (scipy's
    gaussian_filter) reduces the standard deviation of white noise."""
    if s <= 0:
        return 1.0
    from scipy.ndimage import gaussian_filter
    n = 2 * int(np.ceil(4 * s)) + 1
    d = np.zeros((n, n))
    d[n // 2, n // 2] = 1.0
    return float(np.sqrt((gaussian_filter(d, s) ** 2).sum()))


def noise_range(t, blur=0.0, sigma0=None):
    """D(s), equation (1): the range of t in units of its noise after a blur
    of `blur` pixels."""
    sigma0 = noise_sd(t) if sigma0 is None else sigma0
    return 1.0 / (sigma0 * kernel_gain(blur))


def required_length(D, threshold=3.0):
    """L = T D, equation (2)."""
    return threshold * D


def blur_for_length(sigma0, length, threshold=3.0, top=20.0):
    """Blur s (pixels) at which a map of the given length shows the noise at
    the threshold. Zero if the map is short enough without blur."""
    if length * sigma0 <= threshold:
        return 0.0
    lo, hi = 0.0, top
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if length * sigma0 * kernel_gain(mid) > threshold:
            lo = mid
        else:
            hi = mid
    return hi


def map_length(rgb, view=PATH_VIEW, smooth=1 / 64):
    """Length and speed of a colour map given as sRGB samples (n, 3) at equal
    steps of the data. Returns (L, v): L the total length, v the speed (colour
    difference per unit of data) averaged over windows of `smooth` of the
    range, so that the quantisation of a table does not show as speed."""
    from ..space import CAM16UCS
    u = CAM16UCS(view)(np.asarray(rgb, float))
    d = np.linalg.norm(np.diff(u, axis=0), axis=1)
    L = float(d.sum())
    w = max(1, int(round(smooth * len(d))))
    v = np.convolve(d, np.ones(w) / w, mode="valid") * len(d)
    return L, v


def volume(bounds=None, view=PATH_VIEW, n=200_000, seed=0):
    """Volume of the sRGB gamut in CAM16-UCS under `view`, within `bounds`
    (a BandBounds, as from bounds.image_bounds) if given; by Monte Carlo
    over the cube, weighting each sample by the Jacobian determinant."""
    from ..space import Observer, Space
    rng = np.random.default_rng(seed)
    x = rng.random((n, 3))
    space = Space(view, (Observer(),))
    u, jac = space.jacobian(x)
    det = np.abs(np.linalg.det(jac[0]))
    keep = np.ones(n, bool)
    if bounds is not None:
        keep = (bounds.slack(u[0], space.ucs.K_L, np.ones(n)) >= 0).all(0)
    return float((det * keep).mean())
