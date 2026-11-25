"""The colour maps shipped with hdrmaps, and images rendered through them.

Each map is stored as the points of an optimised curve in sRGB
(data/maps.json, made by tools/make_hdrmaps.py), with the measures of
cmapkit.hdrmaps.measure taken when it was made. The map itself is the
polyline through the points, sampled at equal steps of colour difference
in normal vision (paths.PathMap).
"""

import copy
import json
from functools import lru_cache
from importlib.resources import files

import numpy as np

from .noise import blur_for_length, noise_sd, scale
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
    d = {k: v for k, v in _data()["maps"][name].items() if k != "points"}
    return copy.deepcopy(d)


@lru_cache(maxsize=None)
def path_map(name):
    """The shipped map `name` as a PathMap."""
    return PathMap(np.asarray(_data()["maps"][name]["points"], float), "linear")


def colormap(name, n=1024):
    """The shipped map `name` as a matplotlib colormap of n entries."""
    from matplotlib.colors import ListedColormap
    m = path_map(name)
    return ListedColormap(m(np.linspace(0, 1, n)), name=f"cmapkit.hdrmaps.{name}")


def _lut(cmap):
    """sRGB table (n, 3) of a shipped map name, a matplotlib colormap or its
    name, or an array of sRGB values."""
    if isinstance(cmap, str):
        if cmap in _data()["maps"]:
            return path_map(cmap).lut
        import matplotlib
        try:
            cmap = matplotlib.colormaps[cmap]
        except KeyError:
            raise ValueError(f"{cmap!r} is neither a shipped map ({', '.join(names())}) "
                             "nor a matplotlib colormap") from None
    if hasattr(cmap, "N") and callable(cmap):
        return np.asarray(cmap(np.linspace(0, 1, max(cmap.N, 256))), float)[:, :3]
    lut = np.asarray(cmap, float)
    if lut.ndim != 2 or lut.shape[1] not in (3, 4) or len(lut) < 2:
        raise ValueError(f"A colour table must be (n, 3) sRGB values; got shape {lut.shape}")
    return lut[:, :3]


def render(image, cmap="path20", kind="sqrt", blur=0.0, threshold=3.0, low=0.1,
           high=99.9):
    """An image in colour, through a shipped map or a table of sRGB colours.

    image: raw values (H, W). They are clipped at the percentiles low and
        high and scaled to [0, 1] by `kind` (maps.scale); 'sqrt' makes shot
        noise equal at every level, as the noise model assumes.
    cmap: the name of a shipped map, a matplotlib colormap or its name, or
        sRGB values (n, 3) in [0, 1] at equal steps of the data.
    blur: the standard deviation of a Gaussian blur in pixels, 0 (the
        default) for none, or 'matched' for the blur at which the map shows
        the noise at `threshold` colour differences per noise standard
        deviation in normal vision (noise.py, equation (2)). A blur changes
        the image, and in a scientific image the change can be taken for
        structure; without it the eye averages neighbouring pixels, and the
        map still serves when single pixels are not resolved.

    Returns (rgb, details): rgb is (H, W, 3) in [0, 1], and details gives
    the noise sigma0 of the scaled image (nan if it cannot be estimated),
    the blur applied, the map's length L in normal vision, and the colour
    difference per noise standard deviation shown, in normal vision, after
    the blur. Observers for whom the map is longer (path20 for tritan
    vision) see the noise in proportion to their length."""
    from scipy.ndimage import gaussian_filter
    from .noise import kernel_gain, map_length

    image = np.asarray(image, float)
    if image.ndim != 2:
        raise ValueError(f"render needs a grey image (H, W), not shape {image.shape}; "
                         "for an RGB file of a grey image, pass image[..., 0]")
    if not np.isfinite(image).all():
        raise ValueError("The image has values that are not finite; fill or crop them first")
    if np.ptp(image) == 0:
        raise ValueError("The image is constant")
    if isinstance(cmap, str) and cmap in _data()["maps"]:
        m = path_map(cmap)
        lut, length = m.lut, m.length
    else:
        lut = _lut(cmap)
        length = map_length(lut)[0]
    t = scale(image, kind, low, high)
    if isinstance(blur, str):
        if blur != "matched":
            raise ValueError(f"blur must be 'matched' or a number of pixels, not {blur!r}")
        sigma0 = noise_sd(t)
        s = blur_for_length(sigma0, length, threshold)
    else:
        s = float(blur)
        try:
            sigma0 = noise_sd(t)
        except ValueError:      # no noise to measure, and none is needed
            sigma0 = float("nan")
    if s > 0:
        t = gaussian_filter(t, s)
    idx = np.clip(np.round(t * (len(lut) - 1)), 0, len(lut) - 1).astype(int)
    details = dict(sigma0=sigma0, blur=s, length=length,
                   noise_shown=length * sigma0 * kernel_gain(s))
    return lut[idx], details
