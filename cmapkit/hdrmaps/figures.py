"""Test pages for HDR maps.

The strip page shows, for each map, the map itself, then the same ramp with
a fine fluctuation added, its amplitude falling from top to bottom, then a
row of small raised spots and a row of small pits. Where the fluctuation
fades early the map shows fine detail poorly; where spots look like pits the
map reverses the polarity of detail.
"""

import numpy as np

PAGE = (0.486, 0.486, 0.486)  # mid grey, Y = 0.2, matching IMAGE_VIEW


def _ramp_blocks(width, amp, wavelength, ramp_h, fluct_h, spot_h, spacing):
    x = np.linspace(0, 1, width)
    ramp = np.tile(x, (ramp_h, 1))
    a = amp * np.linspace(1, 0, fluct_h)[:, None]
    fluct = x[None, :] + a * np.sin(2 * np.pi * np.arange(width) / wavelength)[None, :]
    # Spots: Gaussian bumps of height amp, one every `spacing` pixels.
    px = np.arange(width)
    centres = np.arange(spacing // 2, width, spacing)
    yy = np.arange(spot_h) - spot_h / 2
    d2 = (px[None, :, None] - centres[None, None, :]) ** 2 + (yy[:, None, None]) ** 2
    bump = np.exp(-d2 / (2 * (spot_h / 6) ** 2)).sum(-1)
    raised = x[None, :] + amp * bump
    pits = x[None, :] - amp * bump
    return [ramp, fluct, raised, pits]


def strip_page(maps, path=None, width=1280, amp=0.02, wavelength=8, label_w=230):
    """maps: a dict of label -> OscillatingMap (or any callable taking values
    in [0, 1] and returning sRGB). Saves to path if given; returns the
    figure. Shown at 100 % zoom, one image pixel is one screen pixel."""
    import matplotlib.pyplot as plt

    ramp_h, fluct_h, spot_h, gap, sep = 36, 150, 22, 4, 30
    blocks = _ramp_blocks(width, amp, wavelength, ramp_h, fluct_h, spot_h, 32)
    names = ["map", f"fluctuation, amplitude {amp:g} to 0", "raised spots", "pits"]
    rows, labels = [], []
    y = sep
    for title, m in maps.items():
        labels.append((y - 8, title, True))
        for block, name in zip(blocks, names):
            rows.append((y, m(np.clip(block, 0, 1))))
            labels.append((y + block.shape[0] / 2, name, False))
            y += block.shape[0] + gap
        y += sep
    H, W = y, label_w + width + 20
    img = np.ones((H, W, 3)) * np.array(PAGE)
    for y0, rgb in rows:
        img[y0:y0 + rgb.shape[0], label_w:label_w + width] = rgb
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img, interpolation="nearest", aspect="auto")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    for yl, text, bold in labels:
        if bold:
            ax.text(label_w, yl, text, fontsize=11, weight="bold", va="bottom")
        else:
            ax.text(label_w - 10, yl, text, fontsize=8, ha="right", va="center")
    if path:
        fig.savefig(path, dpi=100)
    return fig


def default_maps(cycles=8):
    """The maps compared on the first strip page."""
    from .maps import OscillatingMap
    maps = {
        "grey, monotone (reference)": OscillatingMap(trend=1.0, colourfulness=0.0),
        "hue turn, monotone (reference)": OscillatingMap(trend=1.0),
    }
    for wave in ["sine", "asymmetric sine", "triangle", "sawtooth", "rounded sawtooth"]:
        maps[f"{wave}, {cycles} cycles"] = OscillatingMap(wave, cycles=cycles)
    return maps


def busiest_window(t, size=512, step=128):
    """Top-left corner of the size x size window with the widest spread of t."""
    best, corner = -1.0, (0, 0)
    for y in range(0, t.shape[0] - size + 1, step):
        for x in range(0, t.shape[1] - size + 1, step):
            s = np.percentile(t[y:y + size:4, x:x + size:4], [5, 95])
            if s[1] - s[0] > best:
                best, corner = s[1] - s[0], (y, x)
    return corner


def image_page(panels, path=None, shrink=3, crop=None, crop_size=512, label_h=24):
    """panels: a dict of label -> sRGB image (H, W, 3), all the same size.
    Each row shows the whole image reduced by `shrink` and a crop at full
    size (one image pixel per screen pixel at 100 % zoom)."""
    import matplotlib.pyplot as plt

    first = next(iter(panels.values()))
    h, w = first.shape[:2]
    y0, x0 = crop if crop is not None else (h // 2 - crop_size // 2, w // 2 - crop_size // 2)
    sw, sh = w // shrink, h // shrink
    row_h = max(sh, crop_size) + label_h + 12
    W, H = sw + crop_size + 30, row_h * len(panels) + 10
    img = np.ones((H, W, 3)) * np.array(PAGE)
    labels = []
    for k, (label, rgb) in enumerate(panels.items()):
        top = k * row_h + label_h + 10
        small = rgb[:sh * shrink, :sw * shrink].reshape(sh, shrink, sw, shrink, 3).mean((1, 3))
        img[top:top + sh, 10:10 + sw] = small
        img[top:top + crop_size, 20 + sw:20 + sw + crop_size] = rgb[y0:y0 + crop_size, x0:x0 + crop_size]
        labels.append((top - 4, label))
    # Outline of the crop on each reduced image.
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img, interpolation="nearest", aspect="auto")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    from matplotlib.patches import Rectangle
    for k, (yl, text) in enumerate(labels):
        ax.text(10, yl, text, fontsize=11, weight="bold", va="bottom")
        top = k * row_h + label_h + 10
        ax.add_patch(Rectangle((10 + x0 / shrink, top + y0 / shrink), crop_size / shrink,
                               crop_size / shrink, fill=False, ec="white", lw=1))
    if path:
        fig.savefig(path, dpi=100)
    return fig
