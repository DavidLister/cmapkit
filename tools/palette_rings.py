"""Draw docs/img/rings_compare.png: MCCP beside common categorical palettes
(petroff10 needs matplotlib 3.10 or later).

Usage:

    python tools/palette_rings.py [--n N] [--out PATH]

Each palette of N colours (7 by default, the size of Okabe-Ito and Tol
bright; longer palettes give their first N) is drawn as the ring disc of
docs/test-figures.md, in normal vision and in simulated deutan, protan and
tritan vision (Machado et al. 2009, at full severity), on white. Under each
disc is the least colour difference between two colours of the palette for
that observer, in CAM16-UCS with lightness weight 0.77, the measure that
MCCP's sRGB mode maximises. The comparison therefore favours MCCP by
construction; docs/results.md compares the palettes under other measures.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cmapkit  # noqa: E402
from cmapkit.mccp.figures import draw_rings, ring_layout, simulate  # noqa: E402
from cmapkit.space import Observer, Space, hex_to_rgb, viewing  # noqa: E402

BACKGROUND = "#ffffff"
OBSERVERS = [Observer(), Observer("deutan"), Observer("protan"), Observer("tritan")]


def palettes(n):
    import matplotlib
    import matplotlib.style
    from matplotlib.colors import to_hex

    def cmap(name):
        return [to_hex(c) for c in matplotlib.colormaps[name].colors]

    out = {
        "MCCP": cmapkit.palette(n, background=BACKGROUND).hex,
        "tab10\n(matplotlib default)": cmap("tab10"),
        "petroff10\n(matplotlib style)": list(
            matplotlib.style.library["petroff10"]["axes.prop_cycle"].by_key()["color"]),
        "Okabe-Ito": ["#e69f00", "#56b4e9", "#009e73", "#f0e442", "#0072b2", "#d55e00",
                      "#cc79a7"],
        "Tol bright": ["#4477aa", "#ee6677", "#228833", "#ccbb44", "#66ccee", "#aa3377",
                       "#bbbbbb"],
        "ColorBrewer\nSet1": cmap("Set1"),
        "ColorBrewer\nDark2": cmap("Dark2"),
    }
    return {k: [c.lower() for c in v[:n]] for k, v in out.items() if len(v) >= n}


def least_distance(hexes, observer):
    u = Space(viewing("screen", BACKGROUND, lightness_weight=0.77), (observer,)).coords(
        hex_to_rgb(hexes))[0]
    d = np.linalg.norm(u[:, None] - u[None], axis=-1)
    return float(d[np.triu_indices(len(u), 1)].min())


def figure(n, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pals = palettes(n)
    view = Space(viewing("screen", BACKGROUND, lightness_weight=0.77))
    fig, axes = plt.subplots(len(OBSERVERS), len(pals),
                             figsize=(1.45 * len(pals) + 0.7, 1.75 * len(OBSERVERS) + 0.5))
    fig.patch.set_facecolor(BACKGROUND)
    for c, (name, hexes) in enumerate(pals.items()):
        u = view.coords(hex_to_rgb(hexes))[0]
        grid = ring_layout(np.linalg.norm(u[:, None] - u[None], axis=-1))
        axes[0, c].set_title(name, fontsize=10, pad=8)
        for r, obs in enumerate(OBSERVERS):
            ax = axes[r, c]
            draw_rings(ax, hexes if obs.kind == "normal" else simulate(hexes, obs), grid,
                       BACKGROUND)
            ax.set_xlabel(f"{least_distance(hexes, obs):.1f}", fontsize=9, labelpad=2)
            if c == 0:
                ax.set_ylabel(obs.kind, fontsize=10, labelpad=8)
    fig.tight_layout(h_pad=0.6, w_pad=0.4)
    fig.savefig(path, dpi=100, facecolor=BACKGROUND)
    plt.close(fig)
    return pals


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=7)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "docs/img/rings_compare.png"))
    args = ap.parse_args()
    pals = figure(args.n, args.out)
    for name, hexes in pals.items():
        print(name.replace("\n", " "), " ".join(f"{least_distance(hexes, o):5.1f}"
                                                for o in OBSERVERS))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
