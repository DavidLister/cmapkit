"""Test figures (README, Section 4.4; docs/test-figures.md)."""

import math

import numpy as np

from .order import distance_matrix, path_order
from .space import Observer, Space, hex_to_rgb, linear_to_srgb, rgb_to_hex, srgb_to_linear, viewing


# --- ring layout ---------------------------------------------------------------


def _neighbours(R, N):
    nb = [[[] for _ in range(N)] for _ in range(R)]
    for r in range(R):
        for k in range(N):
            a, b = (r, k), (r, (k + 1) % N)
            nb[a[0]][a[1]].append(b)
            nb[b[0]][b[1]].append(a)
            if r:
                for c in ((r - 1, k), (r - 1, (k + 1) % N)):
                    nb[r][k].append(c)
                    nb[c[0]][c[1]].append((r, k))
    return nb


def _anneal(N, R, fixed, steps, seed, target=2):
    """Simulated annealing over swaps within free rings.

    fixed: dict ring -> sequence of colours. Returns (shortfall, grid)."""
    rng = np.random.default_rng(seed)
    nb = _neighbours(R, N)
    grid = np.array([fixed[r] if r in fixed else rng.permutation(N) for r in range(R)])
    free = [r for r in range(R) if r not in fixed]
    cnt = np.zeros((N, N), int)
    for r in range(R):
        for k in range(N):
            for (m, j) in nb[r][k]:
                if (m, j) > (r, k):
                    x, y = grid[r, k], grid[m, j]
                    cnt[x, y] += 1
                    cnt[y, x] += 1
    iu = np.triu_indices(N, 1)
    short = int(np.maximum(0, target - cnt[iu]).sum())
    if not free:
        return short, grid
    T = 1.0
    for _ in range(steps):
        if short == 0:
            break
        r = free[rng.integers(len(free))]
        k1, k2 = rng.choice(N, 2, replace=False)
        cells = {(r, k1), (r, k2)}

        def touch(sign):
            d = 0
            seen = set()
            for (a, b) in cells:
                for (m, j) in nb[a][b]:
                    e = tuple(sorted([(a, b), (m, j)]))
                    if e in seen:
                        continue
                    seen.add(e)
                    x, y = grid[a, b], grid[m, j]
                    if x == y:
                        continue
                    if sign < 0:
                        cnt[x, y] -= 1
                        cnt[y, x] -= 1
                        if cnt[x, y] < target:
                            d += 1
                    else:
                        if cnt[x, y] < target:
                            d -= 1
                        cnt[x, y] += 1
                        cnt[y, x] += 1
            return d

        d = touch(-1)
        grid[r, k1], grid[r, k2] = grid[r, k2], grid[r, k1]
        d += touch(+1)
        if d <= 0 or rng.random() < math.exp(-d / T):
            short += d
        else:
            touch(-1)
            grid[r, k1], grid[r, k2] = grid[r, k2], grid[r, k1]
            touch(+1)
        T = max(0.02, T * 0.99995)
    return short, grid


def ring_layout(d, steps=150_000, seeds=3, target=2):
    """Ring arrangement for a distance matrix d (N x N).

    Ring 0 is innermost. The outer ring holds the similar ordering; the inner
    ring holds the contrasting ordering where the search allows."""
    N = len(d)
    similar = path_order(d, "similar")
    contrasting = path_order(d, "contrasting")
    R = max(2, math.ceil((N + 1) / 3))
    while True:
        for fixed in ({0: contrasting, R - 1: similar}, {R - 1: similar}):
            for s in range(seeds):
                short, grid = _anneal(N, R, fixed, steps, s, target)
                if short == 0:
                    return grid
        R += 1


# --- simulation ----------------------------------------------------------------


def simulate(hexes, observer):
    """Colours as seen by a simulated observer, clipped to sRGB for display."""
    lin = srgb_to_linear(hex_to_rgb(hexes))
    return rgb_to_hex(linear_to_srgb(lin @ observer.matrix().T))


# --- drawing -------------------------------------------------------------------


def draw_rings(ax, hexes, grid, background="#ffffff", hole=0.22):
    from matplotlib.patches import Wedge
    R, N = grid.shape
    width = (1 - hole) / R
    for r in range(R):
        # Ring r is turned through r/2 cells, so that cell (r, k) borders
        # cells (r - 1, k) and (r - 1, k + 1), as _neighbours assumes.
        offset = 0.5 * r
        for k in range(N):
            t0 = 360 * (k + offset) / N
            ax.add_patch(Wedge((0, 0), hole + (r + 1) * width, t0, t0 + 360 / N,
                               width=width, facecolor=hexes[grid[r, k]], edgecolor="none"))
    ax.add_patch(Wedge((0, 0), hole, 0, 360, facecolor=background, edgecolor="none"))
    ax.set_xlim(-1.02, 1.02)
    ax.set_ylim(-1.02, 1.02)
    ax.set_aspect("equal")
    ax.set_facecolor(background)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def closest_pairs(hexes, space, k=6):
    d = distance_matrix(hex_to_rgb(hexes), space)
    iu = np.triu_indices(len(hexes), 1)
    order = np.argsort(d[iu])[:k]
    return [(int(iu[0][o]), int(iu[1][o]), float(d[iu][o])) for o in order]


def draw_pairs(ax, hexes, pairs, background="#ffffff"):
    """Each closest pair as touching swatches and as two thin lines."""
    ax.set_facecolor(background)
    x = np.linspace(0, 1, 50)
    for row, (i, j, dist) in enumerate(pairs):
        y = -row
        ax.add_patch(_rect(0.0, y - 0.4, 0.3, 0.8, hexes[i]))
        ax.add_patch(_rect(0.3, y - 0.4, 0.3, 0.8, hexes[j]))
        ax.plot(0.8 + 0.8 * x, y + 0.15 + 0.1 * np.sin(6 * x), color=hexes[i], lw=1.0)
        ax.plot(0.8 + 0.8 * x, y - 0.15 + 0.1 * np.sin(6 * x + 1), color=hexes[j], lw=1.0)
        ax.text(1.7, y, f"{dist:.1f}", va="center", fontsize=7)
    ax.set_xlim(-0.05, 2.0)
    ax.set_ylim(-len(pairs) + 0.4, 0.6)
    ax.axis("off")


def _rect(x, y, w, h, c):
    from matplotlib.patches import Rectangle
    return Rectangle((x, y), w, h, facecolor=c, edgecolor="none")


def draw_plot(ax, hexes, background="#ffffff"):
    """A realistic plot: lines of two widths and markers."""
    ax.set_facecolor(background)
    x = np.linspace(0, 10, 200)
    n = len(hexes)
    for i, c in enumerate(hexes):
        ax.plot(x, np.sin(x + 0.6 * i) + 0.25 * i, color=c, lw=1.0 if i % 2 else 2.2)
        ax.scatter(np.linspace(0.5, 9.5, 6) + 0.1 * i,
                   np.cos(np.linspace(0.5, 9.5, 6) + i) - 1.5 - 0.1 * i, color=c, s=12)
    ax.set_xticks([])
    ax.set_yticks([])


def report_figure(hexes, title, background="#ffffff", preset="screen", ucs="UCS",
                  lightness_weight=None,
                  observers=(Observer("deutan", 1.0), Observer("protan", 1.0),
                             Observer("tritan", 1.0)), path=None):
    """Ring disc, closest pairs and a plot, for normal vision and each observer."""
    import matplotlib.pyplot as plt
    view = viewing(preset, background, ucs=ucs, lightness_weight=lightness_weight)
    rows = [Observer()] + list(observers)
    d = distance_matrix(hex_to_rgb(hexes), Space(view))
    grid = ring_layout(d)
    fig, axes = plt.subplots(len(rows), 3, figsize=(10, 3.2 * len(rows)),
                             gridspec_kw=dict(width_ratios=[1, 1, 1.4]))
    fig.patch.set_facecolor(background)
    for r, obs in enumerate(rows):
        shown = hexes if obs.kind == "normal" else simulate(hexes, obs)
        space = Space(view, (obs,))
        draw_rings(axes[r, 0], shown, grid, background)
        draw_pairs(axes[r, 1], shown, closest_pairs(hexes, space), background)
        draw_plot(axes[r, 2], shown, background)
        axes[r, 0].set_title(str(obs), fontsize=9)
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=110, facecolor=background)
        plt.close(fig)
    return fig
