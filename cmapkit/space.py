"""Conversion from sRGB to CAM16-UCS, with flare and simulated colour vision.

The CAM16 equations follow Li et al. (2017); see docs/cam16-reference.md.
All functions are vectorised over a leading axis of colours.
"""

from dataclasses import dataclass

import numpy as np

from ._machado import MACHADO_2009

# Linear sRGB to CIE XYZ (IEC 61966-2-1), D65 white.
M_SRGB = np.array([[0.4124564, 0.3575761, 0.1804375],
                   [0.2126729, 0.7151522, 0.0721750],
                   [0.0193339, 0.1191920, 0.9503041]])
# White of the display, scaled so that Y = 100.
XYZ_WHITE = 100.0 * M_SRGB.sum(axis=1)

M16 = np.array([[0.401288, 0.650173, -0.051461],
                [-0.250268, 1.204414, 0.045854],
                [-0.002079, 0.048952, 0.953127]])

SURROUNDS = {  # F, c, N_c (Li et al. 2017, Table A1)
    "average": (1.0, 0.69, 1.0),
    "dim": (0.9, 0.59, 0.9),
    "dark": (0.8, 0.525, 0.8),
}

UCS_CONSTANTS = {  # K_L, c1, c2 (Luo et al. 2006)
    "UCS": (1.00, 0.007, 0.0228),
    "LCD": (0.77, 0.007, 0.0053),
}


def srgb_to_linear(rgb):
    rgb = np.asarray(rgb, dtype=float)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(lin):
    lin = np.clip(np.asarray(lin, dtype=float), 0.0, 1.0)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)


def hex_to_rgb(colours):
    """Convert '#rrggbb' strings to an (n, 3) array of sRGB values in [0, 1]."""
    if isinstance(colours, str):
        colours = [colours]
    out = []
    for c in colours:
        c = c.lstrip("#")
        out.append([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return np.array(out)


def to_hex(colour):
    """Normalise a colour ('#rgb', '#rrggbb', a matplotlib name, or an RGB
    triple in [0, 1]) to '#rrggbb'."""
    if isinstance(colour, str):
        c = colour.strip().lower()
        if c.startswith("#") and len(c) == 4:
            return "#" + "".join(ch * 2 for ch in c[1:])
        if c.startswith("#") and len(c) == 7:
            return c
        try:
            from matplotlib.colors import to_hex as _mpl_to_hex
        except ImportError as exc:
            raise ValueError(f"Cannot parse colour {colour!r}") from exc
        return _mpl_to_hex(colour)
    return rgb_to_hex(np.asarray(colour, dtype=float))[0]


def rgb_to_hex(rgb):
    rgb = np.clip(np.round(np.atleast_2d(rgb) * 255), 0, 255).astype(int)
    return ["#{:02x}{:02x}{:02x}".format(*row) for row in rgb]


def relative_luminance(rgb):
    """Relative luminance on a 0-1 scale, as used by WCAG."""
    return srgb_to_linear(rgb) @ M_SRGB[1]


def contrast_ratio(rgb1, rgb2):
    """WCAG 2.1 contrast ratio between colours."""
    y1, y2 = relative_luminance(rgb1), relative_luminance(rgb2)
    hi, lo = np.maximum(y1, y2), np.minimum(y1, y2)
    return (hi + 0.05) / (lo + 0.05)


@dataclass(frozen=True)
class Viewing:
    """Viewing conditions.

    white_luminance: luminance of the display white, cd/m^2.
    background_y: relative luminance of the background, white = 100.
    surround: 'average', 'dim' or 'dark'.
    flare: fraction of the white added to every colour.
    ucs: 'UCS' or 'LCD' constant set.
    """

    white_luminance: float = 80.0
    background_y: float = 100.0
    surround: str = "dim"
    flare: float = 0.01
    ucs: str = "UCS"
    min_background_y: float = 2.0
    # Override of K_L: weight of lightness against the chromatic axes.
    # K_L < 1 makes lightness differences count for more (an ellipsoidal
    # metric); None takes K_L from the constant set.
    lightness_weight: float | None = None

    @property
    def adapting_luminance(self):
        return self.white_luminance * self.y_b / 100.0

    @property
    def y_b(self):
        return max(self.background_y, self.min_background_y)


PRESETS = {
    # sRGB reference viewing environment: 80 cd/m^2 white, 64 lux ambient
    # (dim surround), 1 % viewing flare.
    "screen": dict(white_luminance=80.0, surround="dim", flare=0.01),
    # Provisional values, to be derived properly.
    "screen-dark-room": dict(white_luminance=80.0, surround="dark", flare=0.002),
    "projector": dict(white_luminance=50.0, surround="dark", flare=0.03),
}


def viewing(preset="screen", background="#ffffff", **overrides):
    """Viewing conditions for a named preset and background colour."""
    if preset != "screen":
        import warnings
        warnings.warn(f"The '{preset}' viewing preset has provisional values and is "
                      "experimental; only 'screen' has been calibrated.", stacklevel=2)
    params = dict(PRESETS[preset])
    y = float(relative_luminance(hex_to_rgb(to_hex(background)))[0]) * 100.0
    params["background_y"] = y
    params.update(overrides)
    return Viewing(**params)


class CAM16UCS:
    """Forward transform from sRGB to CAM16-UCS under fixed viewing conditions."""

    def __init__(self, view=None):
        self.view = view or Viewing()
        v = self.view
        F, c, Nc = SURROUNDS[v.surround]
        L_A = v.adapting_luminance
        Yb = v.y_b
        xyz_w = XYZ_WHITE
        Yw = xyz_w[1]
        rgb_w = M16 @ xyz_w
        D = np.clip(F * (1 - (1 / 3.6) * np.exp((-L_A - 42) / 92)), 0, 1)
        self.D_rgb = D * Yw / rgb_w + 1 - D
        k = 1 / (5 * L_A + 1)
        self.F_L = 0.2 * k ** 4 * (5 * L_A) + 0.1 * (1 - k ** 4) ** 2 * (5 * L_A) ** (1 / 3)
        self.n = Yb / Yw
        self.z = 1.48 + np.sqrt(self.n)
        self.N_bb = 0.725 * (1 / self.n) ** 0.2
        self.c, self.N_c = c, Nc
        rgb_aw = self._compress(self.D_rgb * rgb_w)
        self.A_w = (2 * rgb_aw[0] + rgb_aw[1] + rgb_aw[2] / 20 - 0.305) * self.N_bb
        self.K_L, self.c1, self.c2 = UCS_CONSTANTS[v.ucs]
        if v.lightness_weight is not None:
            self.K_L = v.lightness_weight

    def _compress(self, x):
        t = (self.F_L * np.abs(x) / 100) ** 0.42
        return np.sign(x) * 400 * t / (t + 27.13) + 0.1

    def cam16_from_xyz(self, xyz):
        """Return J, M, h (degrees) for XYZ with white Y = 100."""
        rgb = np.asarray(xyz, dtype=float) @ M16.T
        ra = self._compress(rgb * self.D_rgb)
        R, G, B = ra[..., 0], ra[..., 1], ra[..., 2]
        a = R - 12 * G / 11 + B / 11
        b = (R + G - 2 * B) / 9
        h = np.degrees(np.arctan2(b, a)) % 360
        e_t = 0.25 * (np.cos(np.radians(h) + 2) + 3.8)
        A = (2 * R + G + B / 20 - 0.305) * self.N_bb
        J = 100 * np.clip(A / self.A_w, 0, None) ** (self.c * self.z)
        t = (50000 / 13 * self.N_c * self.N_bb * e_t * np.hypot(a, b)
             / (R + G + 21 * B / 20))
        C = t ** 0.9 * np.sqrt(J / 100) * (1.64 - 0.29 ** self.n) ** 0.73
        M = C * self.F_L ** 0.25
        return J, M, h

    def from_linear(self, lin):
        """Linear sRGB (n, 3) to CAM16-UCS (n, 3): J', a', b'."""
        xyz = 100.0 * np.asarray(lin, dtype=float) @ M_SRGB.T
        f = self.view.flare
        xyz = (xyz + f * XYZ_WHITE) / (1 + f)
        J, M, h = self.cam16_from_xyz(xyz)
        Jp = (1 + 100 * self.c1) * J / (1 + self.c1 * J) / self.K_L
        Mp = np.log1p(self.c2 * M) / self.c2
        hr = np.radians(h)
        return np.stack([Jp, Mp * np.cos(hr), Mp * np.sin(hr)], axis=-1)

    def __call__(self, rgb):
        """sRGB (n, 3) in [0, 1] to CAM16-UCS (n, 3)."""
        return self.from_linear(srgb_to_linear(rgb))


@dataclass(frozen=True)
class Observer:
    """An observer: normal vision, or a simulated deficiency at a severity."""

    kind: str = "normal"  # 'normal', 'protan', 'deutan' or 'tritan'
    severity: float = 1.0
    # Fraction of the common spacing this observer is guaranteed (max-min) or
    # aimed at (power mean). 1 treats the observer like normal vision.
    priority: float = 1.0

    def matrix(self):
        if self.kind == "normal":
            return np.eye(3)
        table = MACHADO_2009[self.kind]
        x = np.clip(self.severity, 0, 1) * 10
        i = int(min(np.floor(x), 9))
        return table[i] + (x - i) * (table[i + 1] - table[i])

    def __str__(self):
        s = "normal" if self.kind == "normal" else f"{self.kind} {self.severity:g}"
        return s if self.priority == 1.0 else f"{s} (priority {self.priority:g})"


class Space:
    """CAM16-UCS coordinates of sRGB colours for one or more observers."""

    def __init__(self, view=None, observers=(Observer(),)):
        self.ucs = CAM16UCS(view)
        self.observers = tuple(observers)
        self._mats = [o.matrix() for o in self.observers]

    def coords(self, rgb):
        """Return an array (n_observers, n, 3)."""
        lin = srgb_to_linear(np.atleast_2d(rgb))
        out = []
        for m in self._mats:
            # Simulated colours may fall outside the sRGB cube. They are not
            # clipped: the cone signals of CAM16 stay positive for every
            # observer over the whole cube, so the transform remains smooth.
            out.append(self.ucs.from_linear(lin @ m.T))
        return np.stack(out)

    def jacobian(self, rgb, h=1e-6):
        """Coordinates and their derivatives with respect to sRGB.

        Returns (coords, jac) with shapes (k, n, 3) and (k, n, 3, 3), where
        jac[o, i, p, q] = d coord_p / d rgb_q, by central differences
        (one-sided at the bounds of the cube).
        """
        rgb = np.atleast_2d(np.asarray(rgb, dtype=float))
        base = self.coords(rgb)
        jac = np.empty(base.shape + (3,))
        for q in range(3):
            up = rgb.copy()
            dn = rgb.copy()
            up[:, q] = np.minimum(rgb[:, q] + h, 1.0)
            dn[:, q] = np.maximum(rgb[:, q] - h, 0.0)
            step = (up[:, q] - dn[:, q])[None, :, None]
            jac[..., q] = (self.coords(up) - self.coords(dn)) / step
        return base, jac
