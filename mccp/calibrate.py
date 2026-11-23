"""Calibration pages for judging limits by eye.

Each page shows rows of colours at a series of lightness values J'. Within a
row, colours span a ring of hues at the strongest colourfulness sRGB allows
at that lightness and hue, and again at half of it. The reader picks the row
at which the colours stop being satisfactory.
"""

import numpy as np

from .space import Space, hex_to_rgb, rgb_to_hex, viewing

HUES = np.arange(0, 360, 30)  # twelve hues


def _gamut(view, steps=64):
    g = np.linspace(0, 1, steps)
    rgb = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3)
    u = Space(view).coords(rgb)[0]
    J = u[:, 0]
    C = np.hypot(u[:, 1], u[:, 2])
    h = np.degrees(np.arctan2(u[:, 2], u[:, 1])) % 360
    return rgb, J, C, h


def ring_at_lightness(J_target, view, frac=1.0, tol=1.0, hue_tol=6.0, gamut=None):
    """One colour per hue at lightness J_target, with chroma frac times the
    largest available at that lightness and hue. None where no colour fits."""
    rgb, J, C, h = gamut if gamut is not None else _gamut(view)
    out = []
    for hue in HUES:
        dh = np.abs((h - hue + 180) % 360 - 180)
        m = (np.abs(J - J_target) < tol) & (dh < hue_tol)
        if not m.any():
            out.append(None)
            continue
        cmax = C[m].max()
        idx = np.flatnonzero(m)
        k = idx[np.argmin(np.abs(C[idx] - frac * cmax) + 0.2 * dh[idx])]
        out.append(rgb_to_hex(rgb[k])[0])
    return out


def lightness_page(side="high", background="#ffffff", text="#000000", levels=None,
                   path=None, preset="screen"):
    """Rows of colours at increasing (side='high') or decreasing ('low')
    lightness. Each row: thin lines, thick lines, markers and patches, at full
    and half colourfulness."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    view = viewing(preset, background)
    gamut = _gamut(view)
    jb = Space(view).coords(hex_to_rgb(background))[0, 0, 0]
    if levels is None:
        levels = np.arange(55, 100, 5) if side == "high" else np.arange(40, 0, -5)
    rows = len(levels)
    fig, ax = plt.subplots(figsize=(13, 0.85 * rows * 2 + 1))
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    x = np.linspace(0, 1, 40)
    y = 0.0
    for J in levels:
        for frac, tag in ((1.0, "full"), (0.5, "half")):
            cols = ring_at_lightness(J, view, frac, gamut=gamut)
            for k, c in enumerate(cols):
                if c is None:
                    continue
                x0 = k * 1.0
                ax.plot(x0 + 0.05 + 0.4 * x, y + 0.15 + 0.08 * np.sin(8 * x), color=c, lw=0.8)
                ax.plot(x0 + 0.05 + 0.4 * x, y - 0.05 + 0.08 * np.sin(8 * x), color=c, lw=2.0)
                ax.scatter(x0 + np.array([0.55, 0.62, 0.69]), [y + 0.12, y - 0.02, y + 0.12],
                           s=8, color=c, linewidths=0)
                ax.add_patch(Rectangle((x0 + 0.76, y - 0.2), 0.2, 0.42, facecolor=c,
                                       edgecolor="none"))
            if side == "low":
                ax.plot(len(HUES) + 0.05 + 0.4 * x, y + 0.05 + 0.08 * np.sin(8 * x),
                        color=text, lw=2.0)
            label = f"J' {J:g}  (ΔJ' {abs(jb - J):.0f})  {tag}"
            ax.text(-0.15, y, label, ha="right", va="center", fontsize=8, color=text)
            y -= 0.6
        y -= 0.25
    ax.set_xlim(-2.6, len(HUES) + (0.6 if side == "low" else 0))
    ax.set_ylim(y + 0.3, 0.5)
    ax.axis("off")
    title = ("Light side: lightest row where every colour is still clearly visible"
             if side == "high" else
             "Dark side: darkest row where colours still read as colours (black line at right)")
    ax.set_title(title, fontsize=10, color=text)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=120, facecolor=background)
        plt.close(fig)
    return fig


def colour_at(J_target, hue, view=None, frac=1.0, tol=1.0, hue_tol=6.0, gamut=None):
    """The colour at lightness J_target and the given hue with chroma frac
    times the largest available; None if none fits."""
    rgb, J, C, h = gamut if gamut is not None else _gamut(view)
    dh = np.abs((h - hue + 180) % 360 - 180)
    m = (np.abs(J - J_target) < tol) & (dh < hue_tol)
    if not m.any():
        return None
    idx = np.flatnonzero(m)
    cmax = C[idx].max()
    k = idx[np.argmin(np.abs(C[idx] - frac * cmax) + 0.2 * dh[idx])]
    return rgb_to_hex(rgb[k])[0]


def bounds_page(bounds, side="high", offsets=None, background="#ffffff", text="#000000",
                path=None, preset="screen"):
    """Rows at a fixed offset from each hue's own bound. If the bounds are
    right, the boundary between acceptable and unacceptable is the row at
    offset 0 in every column."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    view = viewing(preset, background)
    gamut = _gamut(view)
    hues = np.asarray(bounds.hues, float)
    base = np.asarray(bounds.light if side == "high" else bounds.dark, float)
    if offsets is None:
        offsets = (np.arange(-15, 15, 5) if side == "high" else np.arange(15, -15, -5))
    # Light side: rows go from darker (safe) to lighter. Dark side: from
    # lighter (safe) to darker.
    rows = list(offsets) if side == "high" else list(offsets)
    fig, ax = plt.subplots(figsize=(13, 0.62 * len(rows) + 1.4))
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    x = np.linspace(0, 1, 40)
    for r, off in enumerate(rows):
        y = -0.7 * r
        for k, (hue, b) in enumerate(zip(hues, base)):
            c = colour_at(b + off, hue, frac=1.0, gamut=gamut)
            if c is None:
                continue
            ax.plot(k + 0.05 + 0.4 * x, y + 0.15 + 0.08 * np.sin(8 * x), color=c, lw=0.8)
            ax.plot(k + 0.05 + 0.4 * x, y - 0.05 + 0.08 * np.sin(8 * x), color=c, lw=2.0)
            ax.scatter(k + np.array([0.55, 0.62, 0.69]), [y + 0.12, y - 0.02, y + 0.12], s=8,
                       color=c, linewidths=0)
            ax.add_patch(Rectangle((k + 0.76, y - 0.2), 0.2, 0.42, facecolor=c,
                                   edgecolor="none"))
            ax.text(k + 0.5, y - 0.3, f"{b + off:g}", fontsize=6, ha="center", color="#888888")
        if side == "low":
            ax.plot(len(hues) + 0.05 + 0.4 * x, y + 0.05 + 0.08 * np.sin(8 * x), color=text,
                    lw=2.0)
        mark = "  <- your bound" if off == 0 else ""
        ax.text(-0.15, y, f"bound {off:+g}{mark}", ha="right", va="center", fontsize=8,
                color=text)
    for k, hue in enumerate(hues):
        ax.text(k + 0.5, 0.45, f"h {hue:g}", ha="center", fontsize=7, color=text)
    ax.set_xlim(-2.4, len(hues) + (0.6 if side == "low" else 0))
    ax.set_ylim(-0.7 * len(rows) + 0.2, 0.65)
    ax.axis("off")
    title = ("Light side, relative to each hue's bound (grey numbers: J')" if side == "high"
             else "Dark side, relative to each hue's bound (grey numbers: J'; 45 is provisional)")
    ax.set_title(title, fontsize=10, color=text)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=120, facecolor=background)
        plt.close(fig)
    return fig
