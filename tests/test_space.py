"""Check the CAM16 transform against colour-science."""

import colour
import numpy as np
import pytest

from cmapkit.space import CAM16UCS, Observer, Space, Viewing, hex_to_rgb, srgb_to_linear, M_SRGB, XYZ_WHITE


def test_published_vector():
    v = Viewing(white_luminance=318.31 * 5, background_y=20, surround="average", flare=0.0)
    model = CAM16UCS(v)
    # colour-science docstring: XYZ_w differs slightly from ours, so compare with colour directly
    xyz = np.array([[19.01, 20.00, 21.78]])
    J, M, h = model.cam16_from_xyz(xyz)
    ref = colour.XYZ_to_CAM16(xyz[0], XYZ_WHITE, v.adapting_luminance, 20,
                              colour.VIEWING_CONDITIONS_CAM16["Average"])
    assert J[0] == pytest.approx(ref.J, rel=1e-7)
    assert M[0] == pytest.approx(ref.M, rel=1e-6)
    assert h[0] == pytest.approx(ref.h, abs=1e-6)


@pytest.mark.parametrize("surround", ["average", "dim", "dark"])
@pytest.mark.parametrize("y_b", [5.0, 20.0, 100.0])
@pytest.mark.parametrize("l_w", [40.0, 80.0, 300.0])
def test_against_colour_science(surround, y_b, l_w):
    rng = np.random.default_rng(0)
    rgb = rng.random((500, 3))
    v = Viewing(white_luminance=l_w, background_y=y_b, surround=surround, flare=0.0)
    ours = CAM16UCS(v)(rgb)
    xyz = 100 * srgb_to_linear(rgb) @ M_SRGB.T
    cond = colour.VIEWING_CONDITIONS_CAM16[surround.capitalize()]
    spec = colour.XYZ_to_CAM16(xyz, XYZ_WHITE, v.adapting_luminance, y_b, cond)
    ref = colour.JMh_CAM16_to_CAM16UCS(np.stack([spec.J, spec.M, spec.h], -1))
    np.testing.assert_allclose(ours, ref, atol=1e-6)


def test_white_and_black():
    model = CAM16UCS(Viewing())
    white, black = model(np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]))
    assert white[0] == pytest.approx(100.0, rel=1e-6)
    # With incomplete adaptation (D < 1) white keeps a little colourfulness.
    assert np.hypot(white[1], white[2]) < 3.0
    assert black[0] > 0  # flare lifts black


def test_flare_reduces_near_black_inflation():
    rgb = hex_to_rgb(["#000019", "#000000"])
    d0 = np.linalg.norm(np.subtract(*CAM16UCS(Viewing(flare=0.0))(rgb)))
    d1 = np.linalg.norm(np.subtract(*CAM16UCS(Viewing(flare=0.01))(rgb)))
    assert d0 == pytest.approx(14.0, abs=0.05)
    assert d1 == pytest.approx(8.5, abs=0.05)


def test_jacobian_matches_finite_difference():
    space = Space(Viewing(), (Observer(), Observer("deutan", 1.0)))
    rgb = np.random.default_rng(1).uniform(0.05, 0.95, (20, 3))
    _, jac = space.jacobian(rgb)
    d = np.array([1e-4, -2e-4, 1.5e-4])
    lhs = space.coords(rgb + d) - space.coords(rgb - d)
    rhs = 2 * jac @ d
    np.testing.assert_allclose(lhs, rhs, atol=1e-5)


def test_cvd_severity_zero_is_identity():
    np.testing.assert_allclose(Observer("protan", 0.0).matrix(), np.eye(3), atol=1e-6)
