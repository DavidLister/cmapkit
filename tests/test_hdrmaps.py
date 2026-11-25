import numpy as np
import pytest

from cmapkit.hdrmaps import scale


def test_sqrt_scale_equalises_shot_noise():
    rng = np.random.default_rng(0)
    levels = np.array([400.0, 40000.0])
    img = rng.poisson(np.repeat(levels, 20000)).astype(float)
    t = scale(img, "sqrt", low=0, high=100)
    s = [t[:20000].std(), t[20000:].std()]
    assert s[0] == pytest.approx(s[1], rel=0.1)


def test_image_bounds_are_calibrated_colours_carried_over():
    from cmapkit.bounds import SRGB_WHITE, image_bounds
    from cmapkit.space import viewing
    same = image_bounds(viewing("screen", "#ffffff"))
    # Under the white background's own viewing, the floor is the measured one
    # (to the resolution of the gamut grid used to find the limit colours).
    assert np.allclose(same.floor, SRGB_WHITE.dark, atol=1.5)
    grey = image_bounds(viewing("screen", "#7c7c7c"))
    assert all(f < c for f, c in zip(grey.floor, grey.ceil))


def test_image_mode_palette_respects_limits():
    import cmapkit
    p = cmapkit.palette(6, background="#7c7c7c", mode="image", observers=[], starts=2, grid=12)
    assert p.diagnostics["max_violation"] < 1e-3


def test_path_map_is_uniform_and_curve_optimiser_thickens():
    import cmapkit
    from cmapkit.bounds import image_bounds
    from cmapkit.hdrmaps.curve import CurveProblem, optimise, resample_equal, thickness
    from cmapkit.hdrmaps.paths import PATH_VIEW, from_palette
    from cmapkit.space import viewing
    p = cmapkit.palette(8, background="#7c7c7c", mode="image", observers=[], starts=2, grid=12)
    m = from_palette(p.rgb)
    steps = np.linalg.norm(np.diff(m.u, axis=0), axis=1)
    # Equal arc length; only the samples that straddle a corner of the
    # polyline are shorter, as the chord cuts the corner.
    assert np.mean(np.abs(steps - np.median(steps)) < 1e-6 * np.median(steps)) > 0.95
    b = image_bounds(viewing("screen", "#7c7c7c"))
    x0 = resample_equal(m.lut[::64], 30)
    prob = CurveProblem(30, PATH_VIEW, (), b)
    u0 = prob.coords(x0)[0]
    step = float(np.mean(prob.steps(u0)))
    x, info = optimise(x0, step=step, bounds=b, iters=60, penalty=5.0)
    assert info["rho"] >= thickness(u0) - 1e-6
    assert info["step_dev"] < 0.05 * step
    assert info["bound_violation"] < 0.5


def test_thickness_of_circle_and_line():
    from cmapkit.hdrmaps.curve import thickness
    # A half circle of radius R has thickness 2 R; a straight line is unbounded.
    th = np.linspace(0, np.pi, 400)
    R = 10.0
    circle = np.stack([R * np.cos(th), R * np.sin(th), 0 * th], -1)
    assert abs(thickness(circle) - 2 * R) < 0.05 * R
    line = np.stack([np.linspace(0, 50, 60), 0 * th[:60], 0 * th[:60]], -1)
    assert thickness(line) == np.inf
    # A hairpin between samples has almost none.
    hair = np.array([[0, 0, 0], [5, 0, 0], [0.5, 0.5, 0], [-5, 1, 0.0]])
    assert thickness(hair) < 1.0


def test_noise_estimate_and_blur():
    from scipy.ndimage import gaussian_filter
    from cmapkit.hdrmaps.noise import blur_for_length, kernel_gain, noise_sd
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:400, 0:400] / 400
    t = 0.3 + 0.4 * xx * yy + 0.02 * rng.standard_normal((400, 400))
    assert abs(noise_sd(t) / 0.02 - 1) < 0.05
    for s in [1.0, 2.0]:
        sd = np.std(gaussian_filter(0.02 * rng.standard_normal((400, 400)), s))
        assert abs(sd / (0.02 * kernel_gain(s)) - 1) < 0.05
    s = blur_for_length(0.02, 1000.0, threshold=3.0)
    assert abs(1000.0 * 0.02 * kernel_gain(s) - 3.0) < 1e-3


def test_least_step_for_a_deficient_observer():
    import cmapkit
    from cmapkit.bounds import image_bounds
    from cmapkit.hdrmaps.curve import CurveProblem, optimise, resample_equal
    from cmapkit.hdrmaps.paths import PATH_VIEW, from_palette
    from cmapkit.space import Observer, viewing
    p = cmapkit.palette(8, background="#7c7c7c", mode="image", observers=[], starts=2, grid=12)
    b = image_bounds(viewing("screen", "#7c7c7c"))
    x0 = resample_equal(from_palette(p.rgb).lut[::64], 30)
    de = Observer("deutan", 1.0, 0.6)
    prob = CurveProblem(30, PATH_VIEW, (de,), b)
    u0 = prob.coords(x0)
    step = float(np.mean(prob.steps(u0[0])))
    assert prob.steps(u0[1]).min() < 0.3 * step
    x, info = optimise(x0, step=step, observers=(de,), bounds=b, iters=60, penalty=5.0,
                       least_step=0.5)
    u = prob.coords(x)
    assert prob.steps(u[1]).min() > 0.48 * step
    assert info["step_dev"] < 0.01 * step


def test_band_on_other_observers_steps():
    import cmapkit
    from cmapkit.bounds import image_bounds
    from cmapkit.hdrmaps.curve import CurveProblem, optimise, resample_equal
    from cmapkit.hdrmaps.paths import PATH_VIEW, from_palette
    from cmapkit.space import Observer, viewing
    p = cmapkit.palette(8, background="#7c7c7c", mode="image", observers=[], starts=2, grid=12)
    b = image_bounds(viewing("screen", "#7c7c7c"))
    x0 = resample_equal(from_palette(p.rgb).lut[::64], 30)
    de = Observer("deutan", 1.0, 0.6)
    prob = CurveProblem(30, PATH_VIEW, (de,), b)
    step = float(np.mean(prob.steps(prob.coords(x0)[0])))
    x, info = optimise(x0, step=step, observers=(de,), bounds=b, iters=100, penalty=20.0,
                       least_step=0.5, band=0.2)
    s = prob.steps(prob.coords(x)[1])
    # Steps within +-20 % of a common l_o allow a ratio of 1.5.
    assert s.max() / s.min() < 1.5 * 1.02
    assert s.min() > 0.5 * 0.8 * step * 0.98
    assert info["step_dev"] < 0.02 * step


@pytest.mark.parametrize("name", ["path10", "path20"])
def test_shipped_maps_are_uniform_and_separated_for_every_observer(name):
    from cmapkit.hdrmaps import assess, info, path_map
    got = assess(path_map(name).lut)
    rec = info(name)["measures"]
    for obs, v in got.items():
        assert v["speed_p95_p5"] <= 1.7
        assert v["separation"] >= 3.0
        assert v["length"] > 250
        # The data file records what the map is.
        assert v["length"] == pytest.approx(rec[obs]["length"], rel=1e-3)
    # Conditions (3) and (5) of docs/hdrmaps.md hold at the points.
    from cmapkit.hdrmaps.curve import CurveProblem
    from cmapkit.hdrmaps.library import _data
    from cmapkit.hdrmaps.paths import PATH_VIEW
    from cmapkit.space import Observer
    band = info(name)["recipe"]["stages"][-1]["band"]
    x = np.asarray(_data()["maps"][name]["points"])
    obs = (Observer("protan"), Observer("deutan"), Observer("tritan"))
    u = CurveProblem(len(x), PATH_VIEW, obs).coords(x)
    st = [np.linalg.norm(np.diff(c, axis=0), axis=1) for c in u]
    assert np.ptp(st[0]) < 1e-3 * st[0].mean()
    for s in st[1:]:
        assert s.max() / s.min() <= (1 + band) / (1 - band) * 1.001


def test_assess_of_a_grey_map_is_the_same_for_every_observer():
    from cmapkit.hdrmaps import assess
    g = np.repeat(np.linspace(0, 1, 256)[:, None], 3, axis=1)
    m = assess(g)
    lengths = [v["length"] for v in m.values()]
    assert max(lengths) - min(lengths) < 1e-6 * max(lengths)


def test_render_matches_the_blur_to_the_noise():
    from scipy.ndimage import gaussian_filter
    from cmapkit.hdrmaps import render, scale
    rng = np.random.default_rng(2)
    # Left half a ramp, right half a constant level, all with shot noise; the
    # noise shown is measured on the constant half, independently of the
    # model by which render chose the blur.
    mean = np.concatenate([np.tile(np.linspace(100, 10000, 300), (400, 1)),
                           np.full((400, 300), 3000.0)], axis=1)
    img = rng.poisson(mean).astype(float)
    assert render(img, "path20")[1]["blur"] == 0      # no blur unless asked
    rgb, d = render(img, "path20", blur="matched", threshold=3.0)
    assert rgb.shape == (400, 600, 3) and rgb.min() >= 0 and rgb.max() <= 1
    t = gaussian_filter(scale(img, "sqrt"), d["blur"])
    measured = d["length"] * t[20:-20, 340:-20].std()
    assert d["blur"] > 0 and measured == pytest.approx(3.0, rel=0.1)
    grey = np.repeat(np.linspace(0, 1, 256)[:, None], 3, axis=1)
    _, d0 = render(img, grey, blur=0)
    assert d0["blur"] == 0 and d0["length"] < d["length"]


def test_render_rejects_what_it_cannot_show():
    from cmapkit.hdrmaps import render
    img = np.random.default_rng(3).poisson(np.full((60, 60), 500.0)).astype(float)
    for bad in [np.full((60, 60), 3.0), np.dstack([img] * 3),
                np.where(img > 520, np.nan, img)]:
        with pytest.raises(ValueError):
            render(bad)
    with pytest.raises(ValueError):
        render(img, "no such map")
    assert render(img, "viridis")[1]["length"] == pytest.approx(132, abs=2)


def test_noise_estimate_ignores_flat_and_clipped_regions():
    from cmapkit.hdrmaps import noise_sd, scale
    rng = np.random.default_rng(4)
    base = np.tile(np.linspace(400, 10000, 600), (500, 1))
    est = []
    for frac in [0.1, 0.6]:
        img = rng.poisson(base).astype(float)
        img[:, :int(frac * 600)] = 0          # a black bar, clipped after scaling
        img[:50, -100:] = 5000.0               # and a flat patch
        est.append(noise_sd(scale(img, "sqrt")))
    assert est[1] == pytest.approx(est[0], rel=0.05)
    with pytest.raises(ValueError):
        noise_sd(np.zeros((40, 40)))


def test_fixed_thickness_with_three_deficient_observers():
    import cmapkit
    from cmapkit.bounds import image_bounds
    from cmapkit.hdrmaps.curve import CurveProblem, optimise, resample_equal, thickness
    from cmapkit.hdrmaps.paths import PATH_VIEW, from_palette
    from cmapkit.space import Observer, viewing
    p = cmapkit.palette(8, background="#7c7c7c", mode="image", observers=[], starts=2, grid=12)
    b = image_bounds(viewing("screen", "#7c7c7c"))
    x0 = resample_equal(from_palette(p.rgb).lut[::64], 30)
    obs = (Observer("protan", 1.0, 0.6), Observer("deutan", 1.0, 0.6),
           Observer("tritan", 1.0, 0.3))
    x, info = optimise(x0, rho=6.0, observers=obs, bounds=b, iters=150, penalty=100.0,
                       least_step=0.5, band=0.3)
    prob = CurveProblem(30, PATH_VIEW, obs, b)
    u = prob.coords(x)
    arc = np.concatenate([[0], np.cumsum(prob.steps(u[0]))])
    rho = min(thickness(u[o], prob.prio[o], arc) for o in range(4))
    assert rho >= 6.0 * 0.98
    st = prob.steps(u[0])
    assert np.ptp(st) < 0.02 * st.mean()
    for o in range(1, 4):
        s = prob.steps(u[o])
        assert s.max() / s.min() < 1.3 / 0.7 * 1.02
