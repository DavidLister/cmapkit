"""Re-score benchmark palettes under other CAM16 settings.

Tests whether MCCP's lead in CAM16-UCS depends on its own viewing
conditions. Usage: python3 -m bench.robustness figures/bench.json
"""

import json
import sys
from collections import defaultdict

import numpy as np

from mccp.space import CAM16UCS, Viewing, hex_to_rgb

SETTINGS = {
    "screen (MCCP default)": Viewing(80, 100, "dim", 0.01),
    "no flare": Viewing(80, 100, "dim", 0.0),
    "Yb 20, average, no flare": Viewing(80 * 0.2 / 1.0, 20, "average", 0.0),
    "LCD constants": Viewing(80, 100, "dim", 0.01, "LCD"),
    "bright room 5% flare": Viewing(200, 100, "average", 0.05),
}
SOURCES = ["mccp", "mccp-srgb", "mccp-swap", "glasbey", "glasbey-matched", "qualpal", "qualpal-matched"]


def least(model, hexes):
    u = model(hex_to_rgb(hexes))
    d = np.linalg.norm(u[:, None] - u[None], axis=-1)
    return d[np.triu_indices(len(u), 1)].min()


def main(path):
    rows = [r for r in json.load(open(path)) if r["source"] in SOURCES]
    for name, view in SETTINGS.items():
        model = CAM16UCS(view)
        best = defaultdict(int)
        ratio = defaultdict(list)
        ns = sorted({r["n"] for r in rows})
        for n in ns:
            vals = {r["source"]: least(model, r["colours"]) for r in rows if r["n"] == n}
            best[max(vals, key=vals.get)] += 1
            for s in SOURCES:
                if s != "mccp" and s in vals:
                    ratio[s].append(vals["mccp"] / vals[s])
        print(f"\n{name}: winner counts over {len(ns)} values of N: {dict(best)}")
        for s, r in ratio.items():
            print(f"   mccp / {s:16s} min {min(r):.2f}  median {np.median(r):.2f}  max {max(r):.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "figures/bench.json")
