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


def _hex(c):
    return mcolors.to_hex(c, keep_alpha=False)


def test_reference_lines_left_alone_and_legend_options_kept():
    fig, ax = plt.subplots()
    for k in range(3):
        ax.plot([0, 1], [k, k + 1], label=f"s{k}")
    ref = ax.axhline(0.5, color="k")
    ax.legend(ncol=3, fontsize=6, frameon=False)
    pal = mccp.recolor(ax, **FAST)
    assert len(pal) == 3 and _hex(ref.get_color()) == "#000000"
    leg = ax.get_legend()
    assert leg._ncols == 3 and not leg.get_frame_on()
    assert [_hex(h.get_color()) for h in leg.legend_handles] == pal.hex
    plt.close(fig)


def test_custom_legend_handles_survive():
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    ax.plot([0, 1], [1, 0], label="b")
    ax.legend(handles=[Line2D([], [], label="a"), Patch(label="region")])
    pal = mccp.recolor(ax, **FAST)
    texts = [t.get_text() for t in ax.get_legend().get_texts()]
    assert texts == ["a", "region"]
    assert _hex(ax.get_legend().legend_handles[0].get_color()) == pal.hex[0]
    plt.close(fig)


def test_twin_axes_pooled_and_background_read_through():
    fig, ax = plt.subplots()
    ax.set_facecolor("black")
    ax2 = ax.twinx()
    l1, = ax.plot([0, 1], [0, 1])
    l2, = ax2.plot([0, 1], [1, 0])
    pal = mccp.recolor([ax, ax2], **FAST)
    assert _hex(l1.get_color()) != _hex(l2.get_color())
    assert "#000000" in pal.diagnostics["anchor_distance"]
    plt.close(fig)


def test_by_label_consistent_across_subplots():
    fig, (a, b) = plt.subplots(1, 2)
    for ax, labels in ((a, ["x", "y", "z"]), (b, ["x", "z"])):
        for k, lab in enumerate(labels):
            ax.plot([0, 1], [k, k], label=lab)
    pal = mccp.recolor(fig, by_label=True, **FAST)
    assert len(pal) == 3
    assert _hex(a.lines[2].get_color()) == _hex(b.lines[1].get_color())
    plt.close(fig)


def test_hollow_scatter_stays_hollow_and_composites_refused():
    fig, ax = plt.subplots()
    sc = ax.scatter([0, 1], [0, 1], facecolors="none", edgecolors="r")
    mccp.recolor(ax, **FAST)
    fc = sc.get_facecolor()
    assert len(fc) == 0 or fc[0][3] == 0
    fig, ax = plt.subplots()
    ax.boxplot([[1, 2, 3], [2, 3, 4]])
    with pytest.raises(ValueError):
        mccp.recolor(ax, **FAST)
    fig, ax = plt.subplots()
    ax.hist([1, 2, 2, 3], histtype="step")
    with pytest.raises(ValueError):
        mccp.recolor(ax, **FAST)
    plt.close("all")


def test_use_follows_dark_style():
    with plt.style.context("dark_background"):
        pal = mccp.use(3, **FAST)
    assert "#000000" in pal.diagnostics["anchor_distance"]
