import numpy as np
import pytest

from cmapkit.hdrmaps import WAVES, OscillatingMap, scale


@pytest.mark.parametrize("wave", list(WAVES))
def test_waves_span_zero_to_one(wave):
    w = WAVES[wave](np.linspace(0, 1, 2001, endpoint=False))
    assert w.min() >= -1e-12 and w.max() <= 1 + 1e-12
    assert w.min() < 0.01 and w.max() > 0.99


def test_map_hits_its_lightness_and_stays_in_gamut():
    m = OscillatingMap("sawtooth", cycles=4, lightness=(30, 90))
    t = np.linspace(0, 0.999, 500)
    u = m.coords(t)
    rgb = m.colours(t)
    assert np.all((rgb >= 0) & (rgb <= 1))
    back = m.ucs(rgb)
    assert np.max(np.abs(back[:, 0] - u[:, 0])) < 1e-6
    assert u[:, 0].min() == pytest.approx(30, abs=0.5)
    assert u[:, 0].max() == pytest.approx(90, abs=0.5)


def test_grey_map_is_grey():
    rgb = OscillatingMap(trend=1.0, colourfulness=0.0).colours(np.linspace(0, 1, 50))
    assert np.max(np.ptp(rgb, axis=1)) < 1e-6


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
    w = max(2, int(np.ceil(2 * p.min_distance / step)))
    x, info = optimise(x0, step=step, bounds=b, w=w, iters=60, penalty=5.0)
    assert info["rho"] >= thickness(u0, w) - 1e-6
    assert info["step_dev"] < 0.05 * step
    assert info["bound_violation"] < 0.5
