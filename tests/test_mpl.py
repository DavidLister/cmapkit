import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import mccp  # noqa: E402

FAST = dict(starts=2, grid=12)


def test_recolor_lines_scatter_and_legend():
    fig, ax = plt.subplots()
    x = np.arange(5)
    for k in range(3):
        ax.plot(x, x + k, label=f"line {k}")
    ax.scatter(x, x * 0, label="points")
    ax.legend()
    pal = mccp.recolor(ax, **FAST)
    assert len(pal) == 4
    got = [mcolors.to_hex(line.get_color()) for line in ax.lines]
    assert got == pal.hex[:3]
    assert mcolors.to_hex(ax.collections[0].get_facecolor()[0]) == pal.hex[3]
    handles = ax.get_legend().legend_handles
    assert mcolors.to_hex(handles[0].get_color()) == pal.hex[0]
    plt.close(fig)


def test_recolor_refuses_errorbars_and_colormapped_scatter():
    fig, ax = plt.subplots()
    ax.errorbar([0, 1], [0, 1], yerr=[0.1, 0.1])
    with pytest.raises(ValueError):
        mccp.recolor(ax, **FAST)
    fig, ax = plt.subplots()
    ax.scatter([0, 1], [0, 1], c=[0, 1])
    ax.plot([0, 1], [1, 0])
    with pytest.raises(ValueError):
        mccp.recolor(ax, **FAST)
    pal = mccp.recolor(ax, strict=False, **FAST)
    assert len(pal) == 1
    plt.close("all")


def test_use_sets_cycle_and_takes_background():
    fig, ax = plt.subplots()
    ax.set_facecolor("black")
    pal = mccp.use(3, ax=ax, **FAST)
    lines = [ax.plot([0, 1], [k, k])[0] for k in range(3)]
    assert [mcolors.to_hex(line.get_color()) for line in lines] == pal.hex
    assert "#000000" in pal.diagnostics["anchor_distance"]
    plt.close(fig)
