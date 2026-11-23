import itertools

import numpy as np
import pytest

from mccp.figures import ring_layout


def drawn_contacts(grid):
    """Count contacts between colours from the drawn geometry: ring r, cell k
    spans angles [k + r/2, k + 1 + r/2) in cell units, modulo N."""
    R, N = grid.shape
    cnt = np.zeros((N, N), int)
    for r in range(R):
        for k in range(N):
            a = grid[r, k]
            b = grid[r, (k + 1) % N]
            cnt[a, b] += 1
            cnt[b, a] += 1
            if r:
                lo = k + r / 2
                for j in range(N):
                    lo2 = j + (r - 1) / 2
                    # overlap of [lo, lo+1) and [lo2, lo2+1) on a circle of length N
                    d = (lo - lo2) % N
                    overlap = max(0.0, 1 - min(d, N - d))
                    if overlap > 1e-9:
                        c = grid[r - 1, j]
                        cnt[a, c] += 1
                        cnt[c, a] += 1
    return cnt


@pytest.mark.parametrize("n", [5, 6, 8, 10])
def test_every_pair_touches_twice(n):
    rng = np.random.default_rng(n)
    pts = rng.random((n, 2))
    d = np.linalg.norm(pts[:, None] - pts[None], axis=-1)
    grid = ring_layout(d, steps=60_000)
    cnt = drawn_contacts(grid)
    for i, j in itertools.combinations(range(n), 2):
        assert cnt[i, j] >= 2, (i, j)
