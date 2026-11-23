"""Precompute default palettes for the calibrated backgrounds.

Writes mccp/data/palettes.json. Each entry is the result of
mccp.palette(n, background=bg) with every other argument at its default.
The file carries a fingerprint of everything that determines the palettes;
mccp ignores it if the fingerprint no longer matches.

The run can be interrupted and resumed: finished entries are kept in
palettes.json.partial. Entries from a run with fewer rounding-repair sweeps
are completed by continuing the (deterministic) repair, which gives the same
result as recomputing them.

Usage: python3 -m tools.precompute [max_n] [workers]
"""

import json
import os
import sys
import time
from multiprocessing import Pool

BACKGROUNDS = ["#ffffff", "#000000", "#333333"]
OUT = os.path.join(os.path.dirname(__file__), "..", "mccp", "data", "palettes.json")


def _entry(p, seconds):
    d = p.diagnostics
    return dict(hex=p.hex, scale=d.get("scale"), scale_by_observer=d.get("scale_by_observer", {}),
                max_violation=d.get("max_violation"), seconds=round(seconds, 1))


def compute(args):
    bg, n = args
    import mccp
    t = time.time()
    p = mccp.palette(n, background=bg, use_cache=False)
    return bg, n, _entry(p, time.time() - t)


def repair(args):
    bg, n, hexes = args
    import mccp
    from mccp import optimise as opt
    from mccp.space import hex_to_rgb, rgb_to_hex
    t = time.time()
    prob = opt.make_problem(n, bg, mode="srgb")
    rgb = hex_to_rgb(hexes)
    prob.set_sides(rgb)
    if n > 1:
        rgb = opt.round_repair(prob, rgb)
    diag = opt.diagnose(prob, rgb)
    p = mccp.Palette(rgb_to_hex(rgb), rgb, diag["min_distance"], diag["scale"], diag)
    return bg, n, _entry(p, time.time() - t)


def main(max_n=50, workers=4):
    import mccp
    from mccp.optimise import cache_fingerprint, cache_settings
    fp = cache_fingerprint()
    out = dict(version=mccp.__version__, fingerprint=fp, settings=cache_settings(),
               palettes={bg: {} for bg in BACKGROUNDS})
    old = {}
    if os.path.exists(OUT + ".partial"):
        with open(OUT + ".partial") as f:
            old = json.load(f)
    to_repair, to_compute = [], []
    for bg in BACKGROUNDS:
        for n in range(1, max_n + 1):
            e = old.get("palettes", {}).get(bg, {}).get(str(n))
            if e and old.get("fingerprint") == fp:
                out["palettes"][bg][str(n)] = e
            elif e:
                to_repair.append((bg, n, e["hex"]))
            else:
                to_compute.append((bg, n))
    to_compute.sort(key=lambda t: -t[1])
    total = len(to_repair) + len(to_compute)
    print(f"kept {sum(len(v) for v in out['palettes'].values())}, repairing {len(to_repair)}, "
          f"computing {len(to_compute)}", flush=True)
    done = 0
    with Pool(workers) as pool:
        for func, tasks in ((repair, to_repair), (compute, to_compute)):
            for bg, n, entry in pool.imap_unordered(func, tasks):
                out["palettes"][bg][str(n)] = entry
                done += 1
                print(f"{done}/{total}  {func.__name__} {bg} N={n}  {entry['seconds']} s  "
                      f"violation {entry['max_violation']:.2g}", flush=True)
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
