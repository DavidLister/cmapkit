"""Build the colour maps shipped in cmapkit/hdrmaps/data/maps.json.

Usage:

    python tools/make_hdrmaps.py [--out PATH]

Each map is made in four stages (docs/hdrmaps.md, section 5):

1. an MCCP palette of N colours in image mode, with the default observers;
2. the order of a short path through the palette;
3. a curve of M points through the palette in that order, at equal steps;
4. rounds of the curve optimiser, first with a least step for the
   colour-deficient observers, then with their steps held in a band.

The optimiser stops each round when it can no longer improve, and a stage
ends when a round makes no progress. The result is a local optimum, and
depends on every setting below, so that the maps may not be reproduced on
another platform or with another version of scipy. The script checks each
map against TARGETS and writes nothing if one misses them. The run takes
about two minutes.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cmapkit  # noqa: E402
from cmapkit.bounds import image_bounds  # noqa: E402
from cmapkit.hdrmaps.curve import CurveProblem, optimise, resample_equal, thickness  # noqa: E402
from cmapkit.hdrmaps.measure import assess  # noqa: E402
from cmapkit.hdrmaps.paths import PATH_VIEW, PathMap, short_path, turning  # noqa: E402
from cmapkit.space import Observer, Space, viewing  # noqa: E402

BACKGROUND = "#7c7c7c"   # sets the viewing conditions of image mode (mid grey)


def observers(tritan=0.2, red_green=0.6):
    """The colour-deficient observers of the curve optimiser, with the
    priorities given: protan and deutan (0.6 in MCCP), and tritan (0.2)."""
    return (Observer("protan", 1.0, red_green), Observer("deutan", 1.0, red_green),
            Observer("tritan", 1.0, tritan))

# name: palette size, curve points, path order, the priorities of the
# colour-deficient observers in the curve optimiser if not those of MCCP
# (red_green for protan and deutan, 0.6; tritan, 0.2), then the optimiser
# stages. The first stage asks only for a least step for those observers;
# the later ones hold their steps in a band, narrowed in steps for path10,
# since a narrow band asked of a curve far from it folds the curve. path20
# is first held at a thickness of 9, then lengthened in step mode within
# the band. Its higher priorities keep its separation above 3 for every
# observer; at MCCP's, tritan would be guaranteed only 0.2 of the thickness.
RECIPES = {
    "path10": dict(n=10, m=40, order="normal", stages=[
        dict(least_step=0.55, penalty=5.0, rounds=10),
        *[dict(least_step=0.55, band=b, penalty=100.0, rounds=15) for b in (0.3, 0.2, 0.15, 0.1)],
    ]),
    "path20": dict(n=20, m=70, order="protan-deutan", red_green=0.7, tritan=0.6, stages=[
        dict(least_step=0.70, penalty=5.0, rounds=10),
        dict(least_step=0.55, band=0.15, rho=9.0, penalty=100.0, rounds=15),
        dict(least_step=0.55, band=0.20, penalty=100.0, rounds=15),
    ]),
}


def path_order(rgb, kind):
    """Order of a short path through the colours, by distance in normal vision
    or by the larger of the protan and deutan distances, starting at the darker
    end. A path that is short in a plane does not cross itself, and the
    protan and deutan views are nearly planes; ordering by their distances
    gives a start that those observers do not see cross."""
    space = Space(PATH_VIEW, (Observer(), Observer("protan"), Observer("deutan")))
    u = space.coords(rgb)
    dist = [np.linalg.norm(x[:, None] - x[None], axis=-1) for x in u]
    d = dist[0] if kind == "normal" else np.maximum(dist[1], dist[2])
    order = short_path(d, starts=20 if kind != "normal" else 12)
    if u[0][order[0], 0] > u[0][order[-1], 0]:
        order = order[::-1]
    return np.asarray(order)


def build(recipe, log=print):
    bounds = image_bounds(viewing("screen", BACKGROUND))
    t0 = time.time()
    pal = cmapkit.palette(recipe["n"], background=BACKGROUND, mode="image", starts=4,
                          use_cache=False)
    rgb = pal.rgb[path_order(pal.rgb, recipe["order"])]
    x = resample_equal(PathMap(rgb, "linear").lut[::8], recipe["m"])
    obs = observers(recipe.get("tritan", 0.2), recipe.get("red_green", 0.6))
    prob = CurveProblem(recipe["m"], PATH_VIEW, obs, bounds)
    for stage in recipe["stages"]:
        stage = dict(stage)
        rounds = stage.pop("rounds")
        rho = stage.pop("rho", None)
        step = None if rho is not None else float(np.mean(prob.steps(prob.coords(x)[0])))
        for r in range(rounds):
            x, info = optimise(x, step=step, rho=rho, observers=obs, bounds=bounds,
                               iters=300, active_margin=6.0, **stage)
            log(f"  {stage} round {r}: thickness {info['rho']:.2f}, length {info['length']:.0f}, "
                f"step deviation {info['step_dev']:.3f}, band shortfall {info['slow']:.3f}")
            if len(info["history"]) <= 2:
                break
    u = prob.coords(x)
    steps = [prob.steps(v) for v in u]
    arc = np.concatenate([[0], np.cumsum(steps[0])])
    lut = PathMap(x, "linear").lut
    return dict(
        points=np.round(x, 8).tolist(),
        palette=pal.hex,
        observers=[str(o) for o in obs],
        thickness=float(min(thickness(u[o], prob.prio[o], arc) for o in range(len(u)))),
        sharpest_turn=float(turning(u[0]).max()),
        # Conditions (3) and (5) of docs/hdrmaps.md at the points: the spread
        # of the normal steps relative to their mean, and each other
        # observer's ratio of greatest to least step.
        step_spread=float(np.ptp(steps[0]) / steps[0].mean()),
        step_ratios={str(o): float(s.max() / s.min()) for o, s in zip(obs, steps[1:])},
        measures=assess(lut),
        recipe=recipe,
    ), time.time() - t0


# A map is shipped only if its points meet conditions (3) and (5) of
# docs/hdrmaps.md, with the band of its last stage, and if, for every
# observer, the speed ratio p95/p5 and the separation
# (cmapkit.hdrmaps.measure) are within these limits.
TARGETS = dict(speed_p95_p5=1.7, separation=3.0)


def failures(measures, built=None, band=None):
    out = []
    if built is not None:
        if built["step_spread"] > 1e-3:
            out.append(f"normal steps unequal by {built['step_spread']:.4f}")
        allowed = (1 + band) / (1 - band) * (1 + 1e-3)
        for o, r in built["step_ratios"].items():
            if r > allowed:
                out.append(f"{o} step ratio {r:.3f} outside the band ({allowed:.3f})")
    for o, v in measures.items():
        if v["speed_p95_p5"] > TARGETS["speed_p95_p5"]:
            out.append(f"{o} speed p95/p5 {v['speed_p95_p5']:.2f}")
        if v["separation"] < TARGETS["separation"]:
            out.append(f"{o} separation {v['separation']:.1f}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1]
                                         / "cmapkit/hdrmaps/data/maps.json"))
    args = ap.parse_args()
    maps = {}
    for name, recipe in RECIPES.items():
        print(name, flush=True)
        maps[name], seconds = build(recipe, log=lambda s: print(s, flush=True))
        print(f"  {seconds:.0f} s", flush=True)
        m = maps[name]["measures"]
        print("  " + ", ".join(f"{o} L {v['length']:.0f} p95/p5 {v['speed_p95_p5']:.2f} "
                               f"sep {v['separation']:.1f}" for o, v in m.items()), flush=True)
        bad = failures(m, maps[name], recipe["stages"][-1]["band"])
        if bad:
            sys.exit(f"{name} misses its targets ({', '.join(bad)}); nothing written. "
                     "The optimum is local and depends on the platform's linear "
                     "programming solver; see docs/hdrmaps.md, section 7.")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    meta = dict(cmapkit_version=cmapkit.__version__, background=BACKGROUND,
                view="cmapkit.hdrmaps.paths.PATH_VIEW", targets=TARGETS)
    Path(args.out).write_text(json.dumps(dict(meta=meta, maps=maps), indent=1) + "\n")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
