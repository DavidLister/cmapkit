"""Precompute default palettes for the calibrated backgrounds.

Writes mccp/data/palettes.json. Each entry is the result of
mccp.palette(n, background=bg) with every other argument at its default.

Usage: python3 -m tools.precompute [max_n] [workers]
"""

import json
import os
import sys
import time
from multiprocessing import Pool

BACKGROUNDS = ["#ffffff", "#000000", "#333333"]
OUT = os.path.join(os.path.dirname(__file__), "..", "mccp", "data", "palettes.json")


def job(args):
    bg, n = args
    import mccp
    t = time.time()
    p = mccp.palette(n, background=bg, use_cache=False)
    d = p.diagnostics
    return bg, n, dict(hex=p.hex, scale=d.get("scale"), min_distance=d.get("min_distance"),
                       scale_by_observer=d.get("scale_by_observer", {}),
                       seconds=round(time.time() - t, 1))


def main(max_n=50, workers=18):
    import mccp
    tasks = sorted(((bg, n) for bg in BACKGROUNDS for n in range(1, max_n + 1)),
                   key=lambda t: -t[1])
    out = dict(version=mccp.__version__, settings=mccp.optimise.cache_settings(),
               palettes={bg: {} for bg in BACKGROUNDS})
    done = 0
    with Pool(workers) as pool:
        for bg, n, entry in pool.imap_unordered(job, tasks):
            out["palettes"][bg][str(n)] = entry
            done += 1
            print(f"{done}/{len(tasks)}  {bg} N={n}  {entry['seconds']} s", flush=True)
            if done % 10 == 0 or done == len(tasks):
                with open(OUT + ".partial", "w") as f:
                    json.dump(out, f)
    for bg in out["palettes"]:
        out["palettes"][bg] = dict(sorted(out["palettes"][bg].items(), key=lambda kv: int(kv[0])))
    with open(OUT, "w") as f:
        json.dump(out, f, indent=0)
    os.remove(OUT + ".partial")


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main(*(int(a) for a in sys.argv[1:]))
