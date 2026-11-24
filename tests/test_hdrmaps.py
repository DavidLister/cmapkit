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
