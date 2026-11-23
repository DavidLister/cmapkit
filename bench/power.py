"""Power-mean objective and observer priorities, compared in sRGB mode.

Usage: python3 -m bench.power figures/power.json
"""

import json
import sys
import time

import numpy as np

import cmapkit
from cmapkit.space import Observer, Space, hex_to_rgb, viewing

REPORT = Space(viewing(lightness_weight=0.77),
               (Observer(), Observer("deutan", 1.0), Observer("protan", 1.0)))


def profile(hexes):
    u = REPORT.coords(hex_to_rgb(hexes))
    iu = np.triu_indices(len(hexes), 1)
    out = {}
    for o, name in zip(range(3), ["normal", "deutan", "protan"]):
        d = np.sort(np.linalg.norm(u[o][:, None] - u[o][None], axis=-1)[iu])
        nn = np.linalg.norm(u[o][:, None] - u[o][None], axis=-1)
        np.fill_diagonal(nn, np.inf)
        out[name] = dict(smallest=d[:5].round(1).tolist(), p10=float(np.percentile(d, 10)),
                         mean_nn=float(nn.min(axis=1).mean()))
    return out


CONFIGS = []
for n in (10, 16):
    for p in (3.0, 6.0, 12.0, np.inf):
        CONFIGS.append((f"normal N={n} p={p:g}", n, p, ()))
for f in (1.0, 0.6):
    for p in (3.0, np.inf):
        CONFIGS.append((f"cvd f={f:g} N=10 p={p:g}", 10, p,
                        (Observer("deutan", 1.0, f), Observer("protan", 1.0, f))))


def main(path):
    out = []
    for name, n, p, obs in CONFIGS:
        t = time.time()
        pal = cmapkit.palette(n, mode="srgb", observers=obs, power=p, order="similar")
        out.append(dict(name=name, n=n, p=p if np.isfinite(p) else "inf", colours=pal.hex,
                        seconds=time.time() - t, **profile(pal.hex)))
        r = out[-1]
        print(f"{name:24s} {r['seconds']:5.0f}s  normal {r['normal']['smallest']} "
              f"mean-nn {r['normal']['mean_nn']:.1f} | deutan {r['deutan']['smallest'][:3]} "
              f"| protan {r['protan']['smallest'][:3]}", flush=True)
        with open(path, "w") as fh:
            json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "figures/power.json")
