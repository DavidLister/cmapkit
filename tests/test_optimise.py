import numpy as np
import pytest

import mccp
from mccp import optimise as opt
from mccp.order import distance_matrix, groups, path_order
from mccp.space import Space, viewing

FAST = dict(starts=2, grid=12)


def test_empty_and_single():
    assert len(mccp.palette(0)) == 0
    p = mccp.palette(1, **FAST)
    assert len(p) == 1 and p.diagnostics["max_violation"] <= 1e-6


def test_constraints_hold_and_deterministic():
    a = mccp.palette(5, **FAST)
    b = mccp.palette(5, **FAST)
    assert a.hex == b.hex
    assert a.diagnostics["max_violation"] < 1e-6
    assert min(a.diagnostics["background_lightness_difference"]) >= 25 - 1e-4
    assert min(a.diagnostics["anchor_distance"]["#000000"]) >= 15 - 1e-4


def test_polish_does_not_lose_to_start():
    prob = opt.make_problem(6)
    cand, uc, cap = opt._feasible_candidates(prob, opt.candidate_grid(12))
    idx = opt.swap_search(prob, uc, cap, opt.farthest_point(prob, uc, cap))
    start = prob.score(prob.evaluate(cand[idx], False))
    rgb, _ = opt.solve(prob, starts=1, grid=12)
    assert prob.score(prob.evaluate(rgb, False)) >= start - 1e-9


def test_fixed_members_count_in_spacing():
    fixed = ["#1f77b4", "#ff7f0e"]
    p = mccp.palette(3, fixed=fixed, **FAST)
    assert p.diagnostics["scale"] > 5
    assert not set(p.hex) & set(fixed)


def test_impossible_anchors_raise():
    anchors = [mccp.Anchor("#ffffff", 200.0, 25.0)]
    with pytest.raises(ValueError):
        mccp.palette(3, anchors=anchors, **FAST)


def test_radius_reserves_room():
    p = mccp.palette(4, radii=[2, 1, 1, 1], **FAST)
    u = Space(viewing()).coords(p.rgb)[0]
    d = np.linalg.norm(u[:, None] - u[None], axis=-1)
    s = p.diagnostics["scale"]
    assert d[0, 1:].min() >= 3 * s - 1e-3


def test_orderings():
    rng = np.random.default_rng(0)
    rgb = rng.random((8, 3))
    d = distance_matrix(rgb, Space(viewing()))
    sim, con = path_order(d, "similar"), path_order(d, "contrasting")
    assert sorted(sim) == list(range(8)) and sorted(con) == list(range(8))
    length = lambda o: d[o[:-1], o[1:]].sum()
    assert length(sim) < length(con)
    gs = groups(d, 3)
    assert sorted(i for g in gs for i in g) == list(range(8))
    assert all(len(g) <= 3 for g in gs)


# --- regressions from the red-team review ------------------------------------


def test_unequal_radii_give_feasible_palette():
    for radii in ([1.8, 1.8, 1, 1, 1, 1], [0.5, 1, 1, 1, 1, 1]):
        p = mccp.palette(6, radii=radii, **FAST)
        assert p.diagnostics["max_violation"] <= opt.FEAS_TOL


def test_impossible_radius_raises():
    with pytest.raises(ValueError):
        mccp.palette(4, radii=[3, 1, 1, 1], **FAST)


def test_order_with_unequal_radii_refused():
    with pytest.raises(ValueError):
        mccp.palette(4, radii=[2.5, 1, 1, 1], order="contrasting", **FAST)


def test_returned_colours_are_feasible_after_rounding():
    p = mccp.palette(8, **FAST)
    assert p.diagnostics["max_violation"] <= opt.FEAS_TOL
    assert min(p.diagnostics["background_lightness_difference"]) >= 25 - opt.FEAS_TOL


@pytest.mark.parametrize("bg", ["#fff", "white", (1.0, 1.0, 1.0)])
def test_background_forms(bg):
    assert len(mccp.palette(3, background=bg, **FAST)) == 3


@pytest.mark.parametrize("bad", [dict(radii=[1, 0, 1]), dict(radii=[1, 1]),
                                 dict(anchors=[mccp.Anchor("#ffffff", -1.0)])])
def test_bad_inputs_raise(bad):
    with pytest.raises(ValueError):
        mccp.palette(3, **bad, **FAST)


def test_srgb_mode_respects_hue_bounds():
    from mccp.bounds import SRGB_WHITE
    p = mccp.palette(6, mode="srgb", **FAST)
    assert p.diagnostics["max_violation"] <= opt.FEAS_TOL
    assert min(p.diagnostics["lightness_bound_slack"]) >= -opt.FEAS_TOL
    with pytest.raises(ValueError):
        mccp.palette(3, mode="srgb", background="#202020", **FAST)


def test_hue_bounds_interpolate_and_blend():
    from mccp.bounds import SRGB_WHITE as B
    u = np.array([[0.0, 30.0, 0.0], [0.0, 0.0, 0.0]])  # hue 0 at chroma 30, and grey
    jmin, jmax = B.limits(u)
    assert jmax[0] == pytest.approx(70) and jmin[0] == pytest.approx(35)
    assert jmax[1] == pytest.approx(B.grey_light) and jmin[1] == pytest.approx(B.grey_dark)


def test_observer_priority_trades_normal_for_cvd():
    from mccp.space import Observer
    full = mccp.palette(5, observers=[Observer("deutan", 1.0, 1.0)], **FAST)
    part = mccp.palette(5, observers=[Observer("deutan", 1.0, 0.4)], **FAST)
    n_full = full.diagnostics["scale_by_observer"]["normal"]
    n_part = part.diagnostics["scale_by_observer"]["normal"]
    assert n_part >= n_full - 1e-6


def test_power_objective_runs_and_is_feasible():
    p = mccp.palette(5, power=3.0, **FAST)
    assert p.diagnostics["max_violation"] <= opt.FEAS_TOL
