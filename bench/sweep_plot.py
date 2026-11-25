"""The default palettes of the sRGB mode, and least separation against N
with and without the colour-vision observers. Reads bench/compare.py output.

Usage: python3 -m bench.sweep_plot figures/bench.json figures
"""

import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from cmapkit.mccp.order import distance_matrix, path_order  # noqa: E402
from cmapkit.space import Space, hex_to_rgb, viewing  # noqa: E402

SPACE = Space(viewing(lightness_weight=0.77))
SOURCES = [("mccp-srgb-cvd", "sRGB mode, default (deutan, protan 0.6; tritan 0.2)"),
           ("mccp-srgb", "sRGB mode, normal vision only")]


def rows_for(data, source):
    return sorted((r for r in data if r["source"] == source), key=lambda r: r["n"])


def ordered(hexes):
    d = distance_matrix(hex_to_rgb(hexes), SPACE)
    return [hexes[i] for i in path_order(d, "similar")]


def plot_palettes(data, path):
    """The default palettes (deutan, protan 0.6; tritan 0.2), one row per N."""
    rows = rows_for(data, SOURCES[0][0])
    nmax = max(r["n"] for r in rows)
    fig, ax = plt.subplots(figsize=(9, 9))
    for k, r in enumerate(rows):
        y = -k
        for i, c in enumerate(ordered(r["colours"])):
            ax.add_patch(Rectangle((i, y), 0.92, 0.85, facecolor=c, edgecolor="none"))
        ax.text(-0.4, y + 0.42, f"N = {r['n']}", ha="right", va="center", fontsize=8)
    ax.set_xlim(-2.2, nmax + 0.2)
    ax.set_ylim(-len(rows) + 0.8, 1.1)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_separation(data, path):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    styles = {"normal": "-", "deutan 1": "--", "protan 1": "-.", "tritan 1": ":"}
    colours = {"mccp-srgb-cvd": "#9467bd", "mccp-srgb": "#ff7f0e", "tab10": "#7f7f7f"}
    for src, label in [("mccp-srgb-cvd", "default"), ("mccp-srgb", "normal only")]:
        rows = rows_for(data, src)
        n = [r["n"] for r in rows]
        for obs, ls in styles.items():
            axes[0].plot(n, [r[f"cam16w {obs}"] for r in rows], ls=ls, color=colours[src],
                         lw=1.8 if obs == "normal" else 1.2, label=f"{label}: {obs}")
    tab = rows_for(data, "tab10")
    axes[0].plot([r["n"] for r in tab], [r["cam16w normal"] for r in tab], color="#7f7f7f",
                 lw=1.2, label="tab10 prefix: normal")
    axes[0].plot([r["n"] for r in tab], [r["cam16w deutan 1"] for r in tab], color="#7f7f7f",
                 lw=1.0, ls="--", label="tab10 prefix: deutan 1")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("N")
    axes[0].set_ylabel("least pairwise distance (lightness-weighted CAM16-UCS)")
    axes[0].set_title("Least separation by observer", fontsize=10)
    axes[0].grid(alpha=0.3)
    axes[0].legend(fontsize=6, ncol=2)

    cvd = {r["n"]: r for r in rows_for(data, "mccp-srgb-cvd")}
    nrm = {r["n"]: r for r in rows_for(data, "mccp-srgb")}
    ns = sorted(set(cvd) & set(nrm))
    axes[1].plot(ns, [cvd[n]["cam16w normal"] / nrm[n]["cam16w normal"] for n in ns],
                 marker="o", color="#9467bd", label="normal vision: default / normal-only")
    worst = lambda r: min(r["cam16w deutan 1"], r["cam16w protan 1"])  # noqa: E731
    axes[1].plot(ns, [worst(cvd[n]) / worst(nrm[n]) for n in ns], marker="s",
                 color="#2ca02c", label="worst of deutan, protan: default / normal-only")
    axes[1].axhline(1, color="#888888", lw=0.8)
    axes[1].set_yscale("log")
    axes[1].set_xlabel("N")
    axes[1].set_title("What the colour-vision observers cost and buy", fontsize=10)
    axes[1].grid(alpha=0.3)
    axes[1].legend(fontsize=7)

    axes[2].plot(ns, [worst(cvd[n]) / cvd[n]["cam16w normal"] for n in ns], marker="o",
                 color="#9467bd", label="default")
    axes[2].plot(ns, [worst(nrm[n]) / nrm[n]["cam16w normal"] for n in ns], marker="o",
                 color="#ff7f0e", label="normal only")
    axes[2].axhline(0.6, color="#888888", lw=0.8, ls="--")
    axes[2].text(ns[-1], 0.61, "priority 0.6", ha="right", fontsize=7, color="#666666")
    axes[2].set_xlabel("N")
    axes[2].set_title("Worst of deutan, protan relative to normal", fontsize=10)
    axes[2].grid(alpha=0.3)
    axes[2].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main(src, outdir):
    with open(src) as f:
        data = json.load(f)
    plot_palettes(data, f"{outdir}/srgb_palettes.png")
    plot_separation(data, f"{outdir}/srgb_vs_n.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
