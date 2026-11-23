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
