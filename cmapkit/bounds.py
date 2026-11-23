"""Lightness bounds that depend on hue.

How light or dark a colour may be before it stops working on a given
background depends on its hue, largely because of the shape of the sRGB
gamut: yellows and greens keep their colourfulness at high lightness, blues
and violets at low lightness. The bounds are tabulated against CAM16 hue,
interpolated around the hue circle, and blended towards conservative values
for colours of low chroma, whose hue is weak or undefined.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HueBounds:
    hues: tuple          # CAM16 hue angles of the table, degrees, increasing
    light: tuple         # largest admissible J' at each hue
    dark: tuple          # smallest admissible J' at each hue
    grey_light: float    # largest admissible J' for a colour of zero chroma
    grey_dark: float     # smallest admissible J' for a colour of zero chroma
    chroma_ref: float = 20.0  # chroma at which the hue values apply in full
    source: str = ""

    def _interp(self, h, table):
        hs = np.asarray(self.hues, float)
        vs = np.asarray(table, float)
        hs = np.concatenate([hs - 360, hs, hs + 360])
        vs = np.concatenate([vs, vs, vs])
        return np.interp(h, hs, vs)

    def limits(self, u):
        """(J'_min, J'_max) for CAM16-UCS coordinates u (..., 3), whose first
        coordinate may be scaled by 1/K_L (only a', b' are used)."""
        a, b = u[..., 1], u[..., 2]
        c = np.hypot(a, b)
        h = np.degrees(np.arctan2(b, a)) % 360
        w = np.clip(c / self.chroma_ref, 0.0, 1.0)
        jmax = self.grey_light + w * (self._interp(h, self.light) - self.grey_light)
        jmin = self.grey_dark + w * (self._interp(h, self.dark) - self.grey_dark)
        return jmin, jmax

    def slack(self, u, k_l):
        """Slack of the lower and upper bound, in J' units: (2, ...)."""
        J = k_l * u[..., 0]
        jmin, jmax = self.limits(u)
        return np.stack([J - jmin, jmax - J])

    def slack_grad(self, u, k_l, eps=1e-4):
        """Derivative of the slack with respect to u: (2, ..., 3)."""
        g = np.zeros((2,) + u.shape)
        g[0, ..., 0] = k_l
        g[1, ..., 0] = -k_l
        for ax in (1, 2):
            up = u.copy()
            dn = u.copy()
            up[..., ax] += eps
            dn[..., ax] -= eps
            lo_u, hi_u = self.limits(up)
            lo_d, hi_d = self.limits(dn)
            g[0, ..., ax] = -(lo_u - lo_d) / (2 * eps)
            g[1, ..., ax] = (hi_u - hi_d) / (2 * eps)
        return g


# Judged by eye by one observer on a white background under the "screen"
# preset, at the strongest colourfulness sRGB allows (2026-11-22): first on
# absolute lightness rows, then corrected on rows relative to these bounds.
SRGB_WHITE = HueBounds(
    hues=(0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330),
    light=(70, 75, 80, 85, 90, 90, 90, 90, 80, 70, 70, 70),
    dark=(35, 35, 50, 55, 55, 50, 55, 55, 50, 40, 35, 35),
    grey_light=70.0,
    grey_dark=50.0,
    source="one observer, white background, screen preset, two passes",
)

# Black and dark grey (#333333) backgrounds with white text, judged by the
# same observer in the same way (2026-11-22). The light-side value at hue 300
# on black was missing from the first reading; 80 was filled in and then
# confirmed by the observer.
SRGB_BLACK = HueBounds(
    hues=(0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330),
    light=(85, 80, 85, 90, 95, 95, 95, 95, 85, 80, 80, 85),
    dark=(50, 50, 55, 65, 65, 60, 65, 65, 60, 55, 50, 50),
    grey_light=80.0,
    grey_dark=65.0,
    source="one observer, black background, screen preset",
)

SRGB_GREY33 = HueBounds(
    hues=(0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330),
    light=(85, 85, 85, 90, 95, 95, 95, 95, 85, 80, 80, 85),
    dark=(45, 45, 55, 65, 65, 55, 60, 60, 55, 50, 50, 45),
    grey_light=80.0,
    grey_dark=65.0,
    source="one observer, #333333 background, screen preset",
)

# Backgrounds for which the sRGB mode is calibrated.
SRGB_BOUNDS = {"#ffffff": SRGB_WHITE, "#000000": SRGB_BLACK, "#333333": SRGB_GREY33}


def _lstar(hexcolour):
    from .space import hex_to_rgb, relative_luminance
    y = float(relative_luminance(hex_to_rgb(hexcolour))[0])
    return 116 * np.cbrt(y) - 16 if y > 216 / 24389 else y * 24389 / 27


def _jbg(hexcolour, preset="screen"):
    """Lightness J' of a background in its own viewing conditions."""
    from .space import Space, hex_to_rgb, viewing
    return float(Space(viewing(preset, hexcolour)).coords(hex_to_rgb(hexcolour))[0, 0, 0])


def _interp_hue(h, hues, table):
    hs = np.asarray(hues, float)
    vs = np.asarray(table, float)
    return np.interp(h, np.concatenate([hs - 360, hs, hs + 360]), np.concatenate([vs, vs, vs]))


@dataclass(frozen=True)
class BandBounds:
    """Two-sided lightness bounds for one background.

    A colour lies either darker or lighter than the background (its side).
    On the darker side it must lie between the floor, below which it reads as
    black, and j_bg - margin; on the lighter side, between j_bg + margin and
    the ceiling, above which it reads as white. Floor, ceiling and margin
    depend on hue and are blended towards their grey values at low chroma.
    """

    hues: tuple
    floor: tuple
    ceil: tuple
    margin: tuple
    grey_floor: float
    grey_ceil: float
    grey_margin: float
    j_bg: float
    chroma_ref: float = 20.0
    source: str = ""

    def _values(self, u):
        a, b = u[..., 1], u[..., 2]
        w = np.clip(np.hypot(a, b) / self.chroma_ref, 0.0, 1.0)
        h = np.degrees(np.arctan2(b, a)) % 360
        blend = lambda grey, tab: grey + w * (_interp_hue(h, self.hues, tab) - grey)  # noqa: E731
        return (blend(self.grey_floor, self.floor), blend(self.grey_ceil, self.ceil),
                blend(self.grey_margin, self.margin))

    def side_of(self, u, k_l):
        return np.where(k_l * u[..., 0] >= self.j_bg, 1.0, -1.0)

    def slack(self, u, k_l, side):
        """Slack of the two conditions on the colour's side, J' units: (2, n)."""
        J = k_l * u[..., 0]
        f, c, m = self._values(u)
        lower = np.where(side > 0, J - (self.j_bg + m), J - f)
        upper = np.where(side > 0, c - J, (self.j_bg - m) - J)
        return np.stack([lower, upper])

    def slack_grad(self, u, k_l, side, eps=1e-4):
        g = np.zeros((2,) + u.shape)
        g[0, ..., 0] = k_l
        g[1, ..., 0] = -k_l
        for ax in (1, 2):
            up, dn = u.copy(), u.copy()
            up[..., ax] += eps
            dn[..., ax] -= eps
            fu, cu, mu = self._values(up)
            fd, cd, md = self._values(dn)
            df, dc, dm = (fu - fd) / (2 * eps), (cu - cd) / (2 * eps), (mu - md) / (2 * eps)
            g[0, ..., ax] = np.where(side > 0, -dm, -df)
            g[1, ..., ax] = np.where(side > 0, dc, -dm)
        return g

    def feasible(self, u, k_l):
        """True where a colour satisfies the conditions on either side."""
        ok = [self.slack(u, k_l, np.full(u.shape[:-1], s)).min(axis=0) >= 0 for s in (-1, 1)]
        return ok[0] | ok[1]


def bounds_for(background, j_bg=None):
    """Two-sided bounds for a background given as '#rrggbb'.

    floor: where colours read as black, from the dark side on white.
    ceil: where colours read as white, from the light side on black and on
        #333333, interpolated between them in background L* and held beyond.
    margin: the least lightness difference from the background, from the
        background side of each calibration (white: 100 - light; black and
        #333333: dark - J' of the background), interpolated in background L*.
    On the three calibrated backgrounds this reproduces the measured tables.
    Elsewhere it is an educated guess, and its source says so."""
    cal = {k: (_lstar(k), _jbg(k), v) for k, v in SRGB_BOUNDS.items()}
    Lw, Jw, W = cal["#ffffff"]
    Lk, Jk, K = cal["#000000"]
    Lg, Jg, G = cal["#333333"]
    L = _lstar(background)
    j_bg = _jbg(background) if j_bg is None else j_bg
    margins = [(Lk, np.subtract(K.dark, Jk), K.grey_dark - Jk),
               (Lg, np.subtract(G.dark, Jg), G.grey_dark - Jg),
               (Lw, np.subtract(100.0, W.light), 100.0 - W.grey_light)]
    xs = [m[0] for m in margins]
    margin = tuple(float(np.interp(L, xs, [m[1][i] for m in margins]))
                   for i in range(len(W.hues)))
    grey_margin = float(np.interp(L, xs, [m[2] for m in margins]))
    ceil = tuple(float(np.interp(L, [Lk, Lg], [k, g])) for k, g in zip(K.light, G.light))
    grey_ceil = float(np.interp(L, [Lk, Lg], [K.grey_light, G.grey_light]))
    calibrated = background in SRGB_BOUNDS
    src = (SRGB_BOUNDS[background].source if calibrated else
           f"interpolated for {background} (L* {L:.1f}) from the calibrations on "
           "#000000, #333333 and #ffffff")
    return BandBounds(hues=W.hues, floor=W.dark, ceil=ceil, margin=margin,
                      grey_floor=W.grey_dark, grey_ceil=grey_ceil, grey_margin=grey_margin,
                      j_bg=j_bg, source=src)
