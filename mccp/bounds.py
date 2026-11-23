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
