"""Print the table of docs/hdrmaps.md, section 6.

Usage:

    python tools/hdrmaps_table.py [--tables DIR]

The matplotlib maps and the shipped maps are measured directly. batlow
(Crameri) and CET-L20 (Kovesi) are not distributed with cmapkit; give a
directory holding their published tables as crameri_batlow.npy and
cet_L20_gouldian.npy (sRGB values, n x 3, in [0, 1]) to include them.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cmapkit.hdrmaps import OscillatingMap, assess, names, path_map  # noqa: E402
from cmapkit.hdrmaps.paths import PATH_VIEW  # noqa: E402
from cmapkit.space import CAM16UCS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tables", default=None)
    args = ap.parse_args()
    import matplotlib
    maps = {}
    for k, label in [("gray", "grey"), ("cividis", "cividis"), ("viridis", "viridis")]:
        maps[label] = matplotlib.colormaps[k](np.linspace(0, 1, 1024))[:, :3]
    if args.tables:
        for f, label in [("crameri_batlow", "batlow"), ("cet_L20_gouldian", "CET-L20")]:
            p = Path(args.tables) / f"{f}.npy"
            if p.exists():
                maps[label] = np.load(p)[:, :3]
    maps["turbo"] = matplotlib.colormaps["turbo"](np.linspace(0, 1, 1024))[:, :3]
    maps["rounded sawtooth, 4 cycles"] = OscillatingMap("rounded sawtooth", cycles=4).lut()
    for n in names():
        maps[n] = path_map(n).lut
    ucs = CAM16UCS(PATH_VIEW)
    print("| Map | L normal | L protan | L deutan | L tritan | worst p95/p5 | worst max/min "
          "| least separation | J' |")
    print("|---|---|---|---|---|---|---|---|---|")
    for label, lut in maps.items():
        m = assess(lut)
        # The first coordinate is J' / K_L; J' itself is that times K_L.
        J = ucs(np.asarray(lut, float))[:, 0] * PATH_VIEW.lightness_weight
        print(f"| {label} | " + " | ".join(f"{v['length']:.0f}" for v in m.values())
              + f" | {max(v['speed_p95_p5'] for v in m.values()):.2f}"
              + f" | {max(v['speed_max_min'] for v in m.values()):.2f}"
              + f" | {min(v['separation'] for v in m.values()):.1f}"
              + f" | {J.min():.0f} to {J.max():.0f} |")


if __name__ == "__main__":
    main()
