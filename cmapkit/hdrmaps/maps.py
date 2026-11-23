"""Colour maps whose lightness repeats over the data range.

A value t in [0, 1] is shown with lightness

    J'(t) = J_lo + (J_hi - J_lo) * (g t + (1 - g) w(phi)),   phi = frac(K t),

where w is a waveform on [0, 1), K the number of cycles and g the share of
the lightness range given to an overall rise (the trend). The hue turns
steadily with t, so that the cycles differ in colour; the colourfulness is
held at a target M', measured from the display's
neutral axis, where the sRGB gamut allows it and reduced where it does
not.
"""

import numpy as np

from ..space import PRESETS, CAM16UCS, Viewing, linear_to_srgb


def _sine(phi):
    return 0.5 - 0.5 * np.cos(2 * np.pi * phi)


def _triangle(phi):
    return 1 - np.abs(2 * phi - 1)


def _sawtooth(phi):
    return phi


def _asymmetric_sine(phi, fall=0.2):
    rise = 1 - fall
    return np.where(phi < rise, 0.5 - 0.5 * np.cos(np.pi * phi / rise),
                    0.5 + 0.5 * np.cos(np.pi * (phi - rise) / fall))


def _rounded_sawtooth(phi, fall=0.2):
    rise = 1 - fall
    return np.where(phi < rise, phi / rise,
                    0.5 + 0.5 * np.cos(np.pi * (phi - rise) / fall))


WAVES = {
    "sine": _sine,
    "triangle": _triangle,
    "sawtooth": _sawtooth,
    "asymmetric sine": _asymmetric_sine,
    "rounded sawtooth": _rounded_sawtooth,
}

# An image fills most of the screen, so the adapting field is taken as a
# mid grey (Y_b = 20) rather than a plot background.
IMAGE_VIEW = Viewing(background_y=20.0, **PRESETS["screen"])


def neutral_axis(ucs, n=1024):
    """a' and b' of the display's greys as functions of J'. With incomplete
    adaptation CAM16 does not place the display white exactly at a' = b' = 0,
    so hue and colourfulness are measured from this axis instead."""
    g = np.linspace(0, 1, n)
    u = ucs.from_linear(np.repeat(g[:, None], 3, axis=1))
    J, a, b = u[:, 0], u[:, 1], u[:, 2]
    return lambda j: np.stack([np.interp(j, J, a), np.interp(j, J, b)], -1)


def _ucs_coords(neutral, J, M, h):
    hr = np.radians(h)
    off = neutral(J)
    return np.stack([J, off[..., 0] + M * np.cos(hr), off[..., 1] + M * np.sin(hr)], -1)


def max_colourfulness(ucs, J, h, neutral=None, top=80.0, steps=24):
    """Largest M' (from the neutral axis) in the sRGB gamut at lightness J'
    and hue h (degrees), by bisection. J and h are arrays of the same shape."""
    neutral = neutral or neutral_axis(ucs)
    J, h = np.broadcast_arrays(np.asarray(J, float), np.asarray(h, float))
    lo, hi = np.zeros(J.shape), np.full(J.shape, top)
    for _ in range(steps):
        mid = 0.5 * (lo + hi)
        lin = ucs.to_linear(_ucs_coords(neutral, J, mid, h))
        ok = np.all((lin >= -1e-9) & (lin <= 1 + 1e-9), axis=-1)
        lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
    return lo


class OscillatingMap:
    """A colour map with K lightness cycles and a steady turn of hue.

    wave: a name in WAVES, or a function of phase in [0, 1) with values in
        [0, 1].
    cycles: K. trend: g, the share of the lightness range given to an overall
        rise; 1 gives an ordinary monotone map.
    lightness: (J_lo, J_hi). hue: (start, turn) in degrees of CAM16 hue.
    colourfulness: target M'; 0 gives a grey map.
    """

    def __init__(self, wave="sawtooth", cycles=8, trend=0.0, lightness=(30.0, 90.0),
                 hue=(250.0, 300.0), colourfulness=30.0, view=IMAGE_VIEW, n=4096):
        self.wave = WAVES[wave] if isinstance(wave, str) else wave
        self.name = wave if isinstance(wave, str) else getattr(wave, "__name__", "wave")
        self.cycles, self.trend = cycles, trend
        self.lightness, self.hue, self.colourfulness = lightness, hue, colourfulness
        self.ucs = CAM16UCS(view)
        self.neutral = neutral_axis(self.ucs)
        self.n = n
        self._lut = None

    def coords(self, t):
        """CAM16-UCS coordinates (J', a', b') of the colours for values t."""
        t = np.clip(np.asarray(t, float), 0, 1)
        phi = np.mod(self.cycles * t, 1.0)
        lo, hi = self.lightness
        J = lo + (hi - lo) * (self.trend * t + (1 - self.trend) * self.wave(phi))
        h = self.hue[0] + self.hue[1] * t
        M = np.minimum(self.colourfulness, max_colourfulness(self.ucs, J, h, self.neutral))
        return _ucs_coords(self.neutral, J, M, h)

    def colours(self, t):
        """sRGB values in [0, 1] for values t."""
        return linear_to_srgb(self.ucs.to_linear(self.coords(t)))

    def lut(self):
        if self._lut is None:
            self._lut = self.colours(np.linspace(0, 1, self.n))
        return self._lut

    def __call__(self, t):
        """sRGB image (..., 3) for an array of values t in [0, 1]."""
        idx = np.clip(np.round(np.asarray(t, float) * (self.n - 1)), 0, self.n - 1).astype(int)
        return self.lut()[idx]

    def cmap(self):
        """The map as a matplotlib colormap."""
        from matplotlib.colors import ListedColormap
        return ListedColormap(self.lut(), name=f"hdr-{self.name}")


def scale(image, kind="log", low=0.1, high=99.9):
    """Values in [0, 1] from a raw image: clipped at the given percentiles,
    then scaled linearly, by square root, or logarithmically. The square root
    makes shot noise (variance proportional to the signal) equal at every
    level."""
    v = np.asarray(image, float)
    lo, hi = np.percentile(v, [low, high])
    v = np.clip(v, lo, hi)
    if kind == "sqrt":
        lo, v, hi = (np.sqrt(np.maximum(x, 0)) for x in (lo, v, hi))
        return (v - lo) / (hi - lo)
    if kind == "log":
        off = 1.0 - min(lo, 0.0)
        return (np.log(v + off) - np.log(lo + off)) / (np.log(hi + off) - np.log(lo + off))
    if kind == "linear":
        return (v - lo) / (hi - lo)
    raise ValueError(f"Unknown scale {kind!r}")
