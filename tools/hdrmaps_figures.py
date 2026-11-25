"""Draw the figures of hdrmaps in docs/img.

Usage:

    python tools/hdrmaps_figures.py [--out DIR]

hdrmaps.png shows the shipped maps and three references as colour bars,
for normal vision and for simulated protan, deutan and tritan vision
(Machado et al. 2009, at full severity).

hdrmaps_ripple.png shows, for each map, a band in which the data rise
steadily from left to right and carry a sine of constant amplitude, 0.01
of the range. The band is divided into five strips in which the period of
the sine is 64, 32, 16, 8 and 4 pixels, from the top. In the lower half of
each strip but the last, the sine of the next strip is added, its
amplitude rising from 0 at the middle of the strip to 0.01 at the bottom,
so that one strip passes into the next. The colour difference by which the map shows the sine at a point is its speed
there times the amplitude (docs/hdrmaps.md, section 4), so a uniform map
shows the sine equally plainly across the band, and the strength of the
sine at one place against another is the ratio of the map's speeds there.
A long map shows the sine more plainly than a short one throughout. In the
rows of highest frequency the eye averages the sine away when the image is
seen at a distance, as it averages noise. The figure is drawn one image
pixel to one screen pixel and should be viewed at full size.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cmapkit.hdrmaps import path_map  # noqa: E402
from cmapkit.space import Observer, linear_to_srgb, srgb_to_linear  # noqa: E402

MAPS = ["path10", "path20", "grey", "cividis", "viridis", "turbo"]
OBSERVERS = ["normal", "protan", "deutan", "tritan"]

AMPLITUDE = 0.01              # of the data range, so that one sine spans 0.02
PERIODS = (64, 32, 16, 8, 4)  # pixels, one strip of each from the top of a band


def lut(name, n=1024):
    if name in ("path10", "path20"):
        return path_map(name)(np.linspace(0, 1, n))
    import matplotlib
    return matplotlib.colormaps["gray" if name == "grey" else name](np.linspace(0, 1, n))[:, :3]


def simulate(rgb, kind):
    if kind == "normal":
        return rgb
    lin = srgb_to_linear(np.clip(rgb, 0, 1)) @ Observer(kind).matrix().T
    return linear_to_srgb(np.clip(lin, 0, 1))


def ripple_data(width, height, amplitude=AMPLITUDE, periods=PERIODS):
    """Data in [0, 1]: a ramp across the width with a sine of constant
    amplitude along it, in strips of shorter period down the height. In the
    lower half of each strip but the last, the sine of the next strip is
    added, its amplitude rising linearly from 0 at the middle of the strip
    to `amplitude` at its bottom row."""
    x = np.arange(width)[None]
    ramp = 2 * amplitude + (1 - 4 * amplitude) * x / (width - 1)
    rows = np.arange(height)
    k = rows * len(periods) // height                  # strip of each row
    start = -(-np.arange(len(periods)) * height // len(periods))  # first row of each
    end = np.append(start[1:], height)
    h = (end - start)[k]
    pos = (rows - start[k] + 1) / h                    # (0, 1] down the strip
    rise = np.clip(2 * pos - 1, 0, 1)
    rise[k == len(periods) - 1] = 0
    p = np.asarray(periods, float)
    nxt = p[np.minimum(k + 1, len(p) - 1)]
    sine = np.sin(2 * np.pi * x / p[k][:, None])
    added = rise[:, None] * np.sin(2 * np.pi * x / nxt[:, None])
    return ramp + amplitude * (sine + added)


def _pixel_figure(width, height):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("white")
    return fig


def _axes(fig, x, y, w, h, W, H):
    """Axes at pixel position (x, y from the top left), size (w, h)."""
    ax = fig.add_axes([x / W, 1 - (y + h) / H, w / W, h / H])
    ax.set_axis_off()
    return ax


def ripple_figure(path, width=720, band=100, gap=14, label=90):
    W = label + width + 10
    H = gap + len(MAPS) * (band + gap)
    fig = _pixel_figure(W, H)
    t = ripple_data(width, band)
    for k, name in enumerate(MAPS):
        table = lut(name)
        idx = np.clip(np.round(t * (len(table) - 1)), 0, len(table) - 1).astype(int)
        y = gap + k * (band + gap)
        ax = _axes(fig, label, y, width, band, W, H)
        ax.imshow(table[idx], interpolation="nearest", aspect="auto")
        fig.text((label - 10) / W, 1 - (y + band / 2) / H, name, ha="right", va="center",
                 fontsize=11)
    fig.savefig(path, dpi=100)


def bars_figure(path, width=400, height=78, gap=20, label=140, top=50):
    names = [m for m in MAPS if m != "grey"]
    W = label + len(OBSERVERS) * (width + 15)
    H = top + len(names) * (height + gap)
    fig = _pixel_figure(W, H)
    for c, kind in enumerate(OBSERVERS):
        x = label + c * (width + 15)
        fig.text((x + width / 2) / W, 1 - top / 2 / H, kind, ha="center", va="center",
                 fontsize=13)
        for r, name in enumerate(names):
            y = top + r * (height + gap)
            ax = _axes(fig, x, y, width, height, W, H)
            ax.imshow(simulate(lut(name, width), kind)[None], interpolation="nearest",
                      aspect="auto")
            if c == 0:
                fig.text((label - 8) / W, 1 - (y + height / 2) / H, name, ha="right",
                         va="center", fontsize=13)
    fig.savefig(path, dpi=100)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "docs/img"))
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    out = Path(args.out)
    bars_figure(out / "hdrmaps.png")
    ripple_figure(out / "hdrmaps_ripple.png")
    print("wrote", out / "hdrmaps.png", "and", out / "hdrmaps_ripple.png")


if __name__ == "__main__":
    main()
