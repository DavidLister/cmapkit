"""Trial of MCCP at large N (README, Section 6)."""

import json
import sys
import time

import mccp
from bench.compare import score


def main(path, ns=(40, 60, 80, 100)):
    out = []
    for n in ns:
        t = time.time()
        p = mccp.palette(n, starts=4, mode="standard")
        secs = time.time() - t
        out.append(dict(n=n, seconds=secs, colours=p.hex, log=p.diagnostics["log"],
                        scale=p.diagnostics["scale"], continuous_scale=p.diagnostics["log"].get("continuous_scale"), **score(p.hex)))
        print(f"N={n}: {secs:.0f} s, min distance {p.min_distance:.2f}", flush=True)
        with open(path, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "figures/large_n.json")
