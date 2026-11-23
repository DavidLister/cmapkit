import json
import time
from importlib import resources

import pytest

import mccp
from mccp import optimise as opt


def _table():
    with resources.files("mccp").joinpath("data/palettes.json").open() as f:
        return json.load(f)


def test_table_is_packaged_current_and_complete():
    table = _table()
    assert table["fingerprint"] == opt.cache_fingerprint()
    for bg in ("#ffffff", "#000000", "#333333"):
        entries = table["palettes"][bg]
        assert sorted(map(int, entries)) == list(range(1, 51))
        assert all(e["max_violation"] <= opt.FEAS_TOL for e in entries.values())


def test_default_palette_comes_from_table():
    t = time.time()
    p = mccp.palette(12, background="black")
    assert time.time() - t < 2.0
    assert p.diagnostics["log"] == {"source": "precomputed"}
    assert p.hex == _table()["palettes"]["#000000"]["12"]["hex"]
    assert p.diagnostics["max_violation"] <= opt.FEAS_TOL


def test_non_default_arguments_bypass_table():
    p = mccp.palette(3, observers=[], starts=2, grid=12)
    assert p.diagnostics["log"] != {"source": "precomputed"}


def test_stale_table_is_refused(monkeypatch):
    monkeypatch.setattr(opt, "_CACHE", None)
    monkeypatch.setattr(opt, "ALGORITHM_REVISION", opt.ALGORITHM_REVISION + 1000)
    with pytest.warns(UserWarning, match="out of date"):
        assert opt._from_cache(5, "#ffffff", None, None, None, "screen", (), None, 8, 0, 24,
                               "UCS", None, "srgb", float("inf")) is None
    monkeypatch.setattr(opt, "_CACHE", None)


@pytest.mark.slow
def test_recomputed_palette_matches_table():
    """The table was made on one platform; elsewhere results may differ
    slightly, so the least distance is compared rather than the colours."""
    stored = mccp.palette(4)
    fresh = mccp.palette(4, use_cache=False)
    assert fresh.min_distance == pytest.approx(stored.min_distance, rel=0.01)
