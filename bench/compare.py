"""Compare MCCP with established palettes and generators.

Protocol (fixed before running):
  - background white; MCCP "screen" viewing preset;
  - N in NS; fixed palettes are scored on their first N entries;
  - every palette is scored under several metrics. A palette's own
    objective is flagged in the output so that circular wins are visible:
      MCCP -> cam16, glasbey -> cam02, qualpal -> de2000;
    OKLab is a referee that none of the generators optimises;
  - simulated deficiencies use Machado et al. (2009) at severity 1;
  - costs are reported where MCCP may lose: contrast against the
    background, lightness spread, chroma, and violations of MCCP's defaults.

Usage: python3 -m bench.compare [outfile]
"""

import json
import sys
import time

import colour
import colorspacious
import matplotlib
import matplotlib.style
import numpy as np

import glasbey
import qualpal

import mccp
from mccp import optimise as opt
from mccp.space import (CAM16UCS, Observer, Space, contrast_ratio, hex_to_rgb, rgb_to_hex,
                        srgb_to_linear, viewing)

NS = [3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 20, 25, 30]
BG = "#ffffff"
VIEW = viewing("screen", BG)


def _hex(cs):
    return [matplotlib.colors.to_hex(c) for c in cs]


FIXED = {
    "tab10": _hex(matplotlib.colormaps["tab10"].colors),
    "tab20": _hex(matplotlib.colormaps["tab20"].colors),
    "okabe-ito": ["#e69f00", "#56b4e9", "#009e73", "#f0e442", "#0072b2", "#d55e00", "#cc79a7"],
    "tol-bright": ["#4477aa", "#ee6677", "#228833", "#ccbb44", "#66ccee", "#aa3377", "#bbbbbb"],
    "petroff10": [c.lower() for c in
                  matplotlib.style.library["petroff10"]["axes.prop_cycle"].by_key()["color"]],
    "set1": _hex(matplotlib.colormaps["Set1"].colors),
    "dark2": _hex(matplotlib.colormaps["Dark2"].colors),
}

OBSERVERS = [Observer("deutan", 1.0), Observer("protan", 1.0), Observer("tritan", 1.0)]


def _pairwise_min(x):
    d = np.linalg.norm(x[:, None] - x[None], axis=-1)
    iu = np.triu_indices(len(x), 1)
    return np.sort(d[iu])


def score(hexes):
    rgb = hex_to_rgb(hexes)
    out = {}
    sp = Space(VIEW, [Observer()] + OBSERVERS)
    u = sp.coords(rgb)
    for o, name in enumerate(["normal"] + [str(x) for x in OBSERVERS]):
        d = _pairwise_min(u[o])
        out[f"cam16 {name}"] = float(d[0])
    d = _pairwise_min(u[0])
    out["cam16 2nd"] = float(d[1]) if len(d) > 1 else float("nan")
    out["cam16 p5"] = float(np.percentile(d, 5))
    # CAM02-UCS as computed by colorspacious with its default sRGB conditions.
    c02 = colorspacious.cspace_convert(rgb, "sRGB1", "CAM02-UCS")
    out["cam02"] = float(_pairwise_min(c02)[0])
    xyz = colour.sRGB_to_XYZ(rgb)
    lab = colour.XYZ_to_Lab(xyz, colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"])
    de = colour.delta_E(lab[:, None], lab[None], method="CIE 2000")
    out["de2000"] = float(de[np.triu_indices(len(rgb), 1)].min())
    ok = colour.XYZ_to_Oklab(xyz) * 100
    out["oklab"] = float(_pairwise_min(ok)[0])
    # Costs.
    jw = CAM16UCS(VIEW)(hex_to_rgb(BG))[0, 0]
    dj = jw - u[0, :, 0]
    out["bg dJ min"] = float(dj.min())
    out["bg contrast min"] = float(contrast_ratio(rgb, hex_to_rgb(BG)).min())
    out["J spread"] = float(u[0, :, 0].std())
    out["max chroma"] = float(np.hypot(u[0, :, 1], u[0, :, 2]).max())
    jb = CAM16UCS(VIEW)(hex_to_rgb("#000000"))[0]
    # Tolerance of 0.25 units: colours on a constraint boundary may cross it
    # by a little after rounding to 8-bit values.
    out["violations"] = int(np.sum(dj < 25 - 0.25)
                            + np.sum(np.linalg.norm(u[0] - jb, axis=1) < 15 - 0.25))
    return out


def mccp_stage(n, stage, observers=()):
    """MCCP restricted to its first stages, as internal baselines."""
    prob = opt.make_problem(n, BG, observers=observers)
    cand, uc, cap = opt._feasible_candidates(prob, opt.candidate_grid(24))
    greedy = opt.farthest_point(prob, uc, cap)
    if stage == "greedy":
        return rgb_to_hex(cand[greedy])
    return rgb_to_hex(cand[opt.swap_search(prob, uc, cap, greedy)])


def matched_candidates():
    prob = opt.make_problem(2, BG)
    cand, _, _ = opt._feasible_candidates(prob, opt.candidate_grid(16))
    return rgb_to_hex(cand)


def generators(n, cand_hex):
    out = {}
    t = time.time()
    p = mccp.palette(n, background=BG)
    out["mccp"] = (p.hex, time.time() - t)
    if n <= 12:
        t = time.time()
        p = mccp.palette(n, background=BG, observers=[("deutan", 1.0), ("protan", 1.0)])
        out["mccp-cvd"] = (p.hex, time.time() - t)
    for stage in ("greedy", "swap"):
        t = time.time()
        out[f"mccp-{stage}"] = (mccp_stage(n, stage), time.time() - t)
    t = time.time()
    out["glasbey"] = (list(glasbey.create_palette(n)), time.time() - t)
    t = time.time()
    # Approximate match only: glasbey bounds lightness in CAM02-UCS J and has
    # no background condition, so this does not reproduce MCCP's constraints.
    out["glasbey-matched"] = (list(glasbey.create_palette(n, lightness_bounds=(15, 75))),
                              time.time() - t)
    t = time.time()
    out["qualpal"] = (list(qualpal.Qualpal().generate(n).hex()), time.time() - t)
    t = time.time()
    out["qualpal-matched"] = (list(qualpal.Qualpal(colors=cand_hex, background=BG)
                                   .generate(n).hex()), time.time() - t)
    if n <= 12:
        # Colour-blind competitors for mccp-cvd. glasbey takes one deficiency
        # at a time. (qualpal-py 1.1.0 returned identical palettes with and
        # without its cvd option in our tests, so it is not used here.)
        for kind in ("deuteranomaly", "protanomaly"):
            t = time.time()
            out[f"glasbey-cvd-{kind[:6]}"] = (
                list(glasbey.create_palette(n, lightness_bounds=(15, 75), colorblind_safe=True,
                                            cvd_type=kind, cvd_severity=100)),
                time.time() - t)
    return out


def main(path):
    results = []
    for name, pal in FIXED.items():
        for n in range(3, len(pal) + 1):
            results.append(dict(source=name, kind="fixed", n=n, colours=pal[:n],
                                full=(n == len(pal)), **score(pal[:n])))
    cand_hex = matched_candidates()
    for n in NS:
        for name, (hexes, secs) in generators(n, cand_hex).items():
            results.append(dict(source=name, kind="generated", n=n, colours=hexes,
                                seconds=secs, **score(hexes)))
        print(f"N={n} done", flush=True)
        with open(path, "w") as f:
            json.dump(results, f, indent=1)
    # MCCP within each fixed palette's own lightness envelope, at its full size.
    for name, pal in FIXED.items():
        env = score(pal)["bg dJ min"]
        anchors = mccp.default_anchors(BG, background_lightness=max(env, 0.0))
        p = mccp.palette(len(pal), background=BG, anchors=anchors)
        results.append(dict(source=f"mccp-envelope:{name}", kind="generated", n=len(pal),
                            colours=p.hex, envelope=env, **score(p.hex)))
    with open(path, "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "figures/bench.json")
