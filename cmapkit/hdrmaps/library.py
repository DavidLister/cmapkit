"""The colour maps shipped with hdrmaps, and images rendered through them.

Each map is stored as the points of an optimised curve in sRGB
(data/maps.json, made by tools/make_hdrmaps.py), with the measures of
cmapkit.hdrmaps.measure taken when it was made. The map itself is the
polyline through the points, sampled at equal steps of colour difference
in normal vision (paths.PathMap).
"""

import json
from functools import lru_cache
from importlib.resources import files

import numpy as np

from .maps import scale
from .noise import blur_for_length, noise_sd
from .paths import PathMap


@lru_cache(maxsize=1)
def _data():
    return json.loads(files(__package__).joinpath("data/maps.json").read_text())


def names():
    """Names of the shipped maps, shortest first."""
    return list(_data()["maps"])


def info(name):
    """What is recorded of a shipped map: its measures for each observer
    (length, speed ratios and separation), its thickness and sharpest turn
    in normal vision, the palette and observers it was made with, and the
    settings of its construction."""
    d = dict(_data()["maps"][name])
    d.pop("points")
    return d


@lru_cache(maxsize=None)
def path_map(name):
    """The shipped map `name` as a PathMap."""
    return PathMap(np.asarray(_data()["maps"][name]["points"], float), "linear")


def colormap(name, n=1024):
    """The shipped map `name` as a matplotlib colormap of n entries."""
    from matplotlib.colors import ListedColormap
    m = path_map(name)
    return ListedColormap(m(np.linspace(0, 1, n)), name=f"cmapkit.hdrmaps.{name}")


def render(image, cmap="path20", kind="sqrt", blur="matched", threshold=3.0, low=0.1,
           high=99.9):
    """An image in colour, through a shipped map or a table of sRGB colours.

    image: raw values (H, W). They are clipped at the percentiles low and
        high and scaled to [0, 1] by `kind` (maps.scale); 'sqrt' makes shot
        noise equal at every level, as the noise model assumes.
    cmap: the name of a shipped map, or sRGB values (n, 3) in [0, 1] at
        equal steps of the data.
    blur: 'matched' for the Gaussian blur (in pixels) at which the map shows
        the noise at `threshold` colour differences per noise standard
        deviation (noise.py, equation (2)), or a number of pixels, or 0.

    Returns (rgb, details): rgb is (H, W, 3) in [0, 1], and details gives
    the noise sigma0 of the scaled image, the blur applied, the map's length
    L in normal vision, and the colour difference per noise standard
    deviation shown after the blur."""
    from scipy.ndimage import gaussian_filter
    from .noise import kernel_gain

    if isinstance(cmap, str):
        m = path_map(cmap)
        lut, length = m.lut, m.length
    else:
        from .noise import map_length
        lut = np.asarray(cmap, float)[:, :3]
        length = map_length(lut)[0]
    t = scale(image, kind, low, high)
    sigma0 = noise_sd(t)
    s = blur_for_length(sigma0, length, threshold) if blur == "matched" else float(blur)
    if s > 0:
        t = gaussian_filter(t, s)
    idx = np.clip(np.round(t * (len(lut) - 1)), 0, len(lut) - 1).astype(int)
    details = dict(sigma0=sigma0, blur=s, length=length,
                   noise_shown=length * sigma0 * kernel_gain(s))
    return lut[idx], details
