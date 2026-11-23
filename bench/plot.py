"""Plots and tables from bench/compare.py output.

Usage: python3 -m bench.plot figures/bench.json figures/
"""

import json
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

METRICS = [
    ("cam16 normal", "CAM16-UCS (MCCP standard mode's own)"),
    ("cam16w normal", "CAM16-UCS lightness-weighted (sRGB mode's own)"),
    ("cam02", "CAM02-UCS (glasbey's own)"),
    ("de2000", "CIEDE2000 (Qualpal's own)"),
    ("oklab", "OKLab ×100 (referee)"),
    ("cam16w deutan 1", "lightness-weighted, deutan 1"),
]

GEN_STYLE = {
    "mccp": dict(color="#000000", lw=2.2),
    "mccp-cvd": dict(color="#000000", lw=1.4, ls="--"),
    "mccp-srgb": dict(color="#9467bd", lw=2.2),
    "mccp-srgb-cvd": dict(color="#9467bd", lw=1.6, ls="--"),
    "mccp-swap": dict(color="#777777", lw=1.0, ls=":"),
    "mccp-greedy": dict(color="#aaaaaa", lw=1.0, ls=":"),
    "glasbey": dict(color="#1f77b4", lw=1.6),
    "glasbey-matched": dict(color="#1f77b4", lw=1.0, ls="--"),
    "glasbey-cvd-deuter": dict(color="#17becf", lw=1.2, ls="-."),
    "glasbey-cvd-protan": dict(color="#17becf", lw=1.2, ls=":"),
    "qualpal": dict(color="#d62728", lw=1.6),
    "qualpal-matched": dict(color="#d62728", lw=1.0, ls="--"),
}


def load(path):
    with open(path) as f:
        return json.load(f)


def series(rows, kind):
    out = defaultdict(list)
    for r in rows:
        if r["kind"] == kind and ":" not in r["source"]:
            out[r["source"]].append(r)
    for v in out.values():
        v.sort(key=lambda r: r["n"])
    return out


def plot_metrics(rows, path):
    gen = series(rows, "generated")
    fix = series(rows, "fixed")
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=True)
    for ax, (key, label) in zip(axes.ravel(), METRICS):
        for name, rs in gen.items():
            ax.plot([r["n"] for r in rs], [r[key] for r in rs], label=name,
                    **GEN_STYLE.get(name, {}))
        for name, rs in fix.items():
            ax.plot([r["n"] for r in rs], [r[key] for r in rs], color="#2ca02c", lw=0.8,
                    alpha=0.6)
            ax.annotate(name, (rs[-1]["n"], rs[-1][key]), fontsize=6, color="#2ca02c")
        ax.set_title(label, fontsize=10)
        ax.set_yscale("log")
        ax.grid(alpha=0.3)
        ax.set_xlabel("N")
        ax.set_ylabel("least pairwise distance")
    axes[0, 0].legend(fontsize=7)
    fig.suptitle("Least pairwise distance against N (fixed palettes in green, as first-N prefixes)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


COLS = ["cam16 normal", "cam16w normal", "cam16w deutan 1", "cam02", "de2000", "oklab", "cam16 deutan 1", "cam16 2nd", "cam16 p5",
        "bg dJ min", "bg contrast min", "J spread", "max chroma", "violations",
        "srgb bound violations"]
OWN = {"mccp": "cam16 normal", "mccp-cvd": "cam16 normal", "mccp-srgb": "cam16w normal",
       "mccp-srgb-cvd": "cam16w normal", "glasbey": "cam02",
       "glasbey-matched": "cam02", "qualpal": "de2000", "qualpal-matched": "de2000"}


def table(rows, n):
    sel = [r for r in rows if r["n"] == n]
    head = "| source | " + " | ".join(COLS) + " |"
    lines = [head, "|" + "---|" * (len(COLS) + 1)]
    for r in sorted(sel, key=lambda r: -r["cam16 normal"]):
        cells = []
        for c in COLS:
            v = r[c]
            s = f"{v:.0f}" if "violations" in c else f"{v:.1f}"
            if OWN.get(r["source"].split(":")[0]) == c:
                s += "*"
            cells.append(s)
        lines.append(f"| {r['source']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(path, outdir):
    rows = load(path)
    plot_metrics(rows, f"{outdir}/bench_metrics.png")
    with open(f"{outdir}/bench_tables.md", "w") as f:
        for n in (7, 8, 10, 20):
            f.write(f"\n## N = {n}\n\n* marks the metric the generator optimises.\n\n")
            f.write(table(rows, n) + "\n")
        env = [r for r in rows if r["source"].startswith("mccp-envelope")]
        if env:
            f.write("\n## MCCP within each fixed palette's own lightness envelope\n\n")
            f.write("| palette | N | envelope dJ | palette cam16 | MCCP cam16 | palette oklab"
                    " | MCCP oklab |\n|---|---|---|---|---|---|---|\n")
            for e in env:
                name = e["source"].split(":")[1]
                full = [r for r in rows if r["source"] == name and r.get("full")][0]
                f.write(f"| {name} | {e['n']} | {e['envelope']:.1f} | {full['cam16 normal']:.1f}"
                        f" | {e['cam16 normal']:.1f} | {full['oklab']:.1f} | {e['oklab']:.1f} |\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
