# The ring figure

This note describes the disc used to inspect palettes. It is drawn by
`mccp.figures.report_figure`.

## 1. Layout

The disc consists of R concentric rings around a central circle. Each ring is
divided into N equal cells, and each ring contains every colour of the palette
once. The central circle is left as background, since cells near the centre
would be too small to judge. Each ring is turned through half a cell relative
to the ring inside it.

With this offset, a cell in an interior ring borders six others: two in its
own ring, two in the ring inside it and two in the ring outside it. Cells of
the innermost and outermost rings border four. The R rings together provide
RN boundaries within rings and 2N(R − 1) between them, a total of (3R − 2)N.

## 2. Number of rings

Every pair of colours should share a boundary at least twice, at different
places on the disc. A single contact could be spoiled by its surroundings,
for example by a third colour nearby that masks the difference. There are
N(N − 1)/2 pairs, so N(N − 1) contacts are needed, and

```math
(3R - 2)N \ge N(N - 1), \qquad R \ge \frac{N + 1}{3}. \tag{1}
```

Equation (1) is a lower bound only. Whether an arrangement exists with that
number of rings has to be found by search.

## 3. Search

An arrangement is found by simulated annealing. Each step swaps two cells
within one ring, which keeps every ring a permutation of the colours. The
quantity minimised is the total shortfall: the sum over all pairs of the
number of contacts by which the pair falls short of two. R is increased from
the bound of equation (1) until a search reaches zero shortfall.
The search uses fixed seeds, so the same palette always gives the same
figure.

The search is `ring_layout` in `mccp/figures.py`. The table gives the
smallest R found in preliminary searches (three seeds of 150 000 steps each,
for each R). These values are not proved minimal.

| N | 6 | 8 | 10 | 12 | 16 | 20 | 30 |
|---|---|---|---|---|---|---|---|
| Bound, eq. (1) | 3 | 3 | 4 | 5 | 6 | 7 | 11 |
| Found | 3 | 4 | 4 | 5 | 7 | 8 | 13 |

## 4. Fixed rings

The outer ring has the largest cells. It is set to the similar ordering of
the palette ([design.md](design.md), Section 7), so that the most alike colours are
compared at the largest size. Where the search allows, the innermost ring is
set to the contrasting ordering. The search then arranges the remaining
rings. The table above was computed without these two constraints, and with
them one more ring may be needed.
