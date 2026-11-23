"""Ordering and grouping of a palette (README, Section 4.1)."""

import numpy as np


def distance_matrix(rgb, space):
    """Least distance over observers between each pair of colours."""
    u = space.coords(rgb)
    d = np.linalg.norm(u[:, :, None] - u[:, None, :], axis=-1)
    return d.min(axis=0)


def _path_length(d, order):
    return d[order[:-1], order[1:]].sum()


def _two_opt(d, order, sign):
    """Improve an open path; sign=+1 minimises length, -1 maximises it."""
    order = list(order)
    n = len(order)
    improved = True
    while improved:
        improved = False
        for i in range(n - 2):
            for j in range(i + 2, n):
                a, b = order[i], order[i + 1]
                c = order[j]
                e = order[j + 1] if j + 1 < n else None
                old = d[a, b] + (d[c, e] if e is not None else 0.0)
                new = d[a, c] + (d[b, e] if e is not None else 0.0)
                if sign * (new - old) < -1e-12:
                    order[i + 1:j + 1] = order[i + 1:j + 1][::-1]
                    improved = True
    return order


def path_order(d, kind="similar"):
    """Open path through all colours, shortest ('similar') or longest
    ('contrasting'). Nearest-neighbour construction from every start,
    followed by 2-opt; deterministic."""
    n = len(d)
    if n < 3:
        return list(range(n))
    sign = 1.0 if kind == "similar" else -1.0
    best, best_len = None, None
    for start in range(n):
        order = [start]
        left = set(range(n)) - {start}
        while left:
            last = order[-1]
            nxt = min(left, key=lambda k: sign * d[last, k])
            order.append(nxt)
            left.remove(nxt)
        order = _two_opt(d, order, sign)
        length = sign * _path_length(d, order)
        if best is None or length < best_len - 1e-12:
            best, best_len = order, length
    return best


def cycle_order(d, kind="similar"):
    """Closed cycle (for the rings of the test figure)."""
    order = path_order(d, kind)
    return order


def groups(d, size):
    """Partition colours into groups of at most `size`, maximising the least
    distance within any group. Returns a list of index lists, best first."""
    n = len(d)
    k = int(np.ceil(n / size))
    # Round-robin over the similar ordering puts alike colours in different groups.
    order = path_order(d, "similar")
    assign = np.empty(n, int)
    for pos, i in enumerate(order):
        assign[i] = pos % k

    def group_min(a):
        mins = []
        for g in range(k):
            m = np.flatnonzero(a == g)
            if len(m) < 2:
                mins.append(np.inf)
            else:
                sub = d[np.ix_(m, m)]
                mins.append(sub[np.triu_indices(len(m), 1)].min())
        return np.array(mins)

    def key(a):
        m = np.sort(group_min(a))
        return tuple(m)

    cur = key(assign)
    improved = True
    while improved:
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                if assign[i] == assign[j]:
                    continue
                assign[i], assign[j] = assign[j], assign[i]
                new = key(assign)
                if new > cur:
                    cur = new
                    improved = True
                else:
                    assign[i], assign[j] = assign[j], assign[i]
    mins = group_min(assign)
    out = []
    for g in np.argsort(-mins):
        members = list(np.flatnonzero(assign == g))
        sub = d[np.ix_(members, members)]
        inner = path_order(sub, "contrasting")
        out.append([members[i] for i in inner])
    return out


def order_indices(rgb, space, kind):
    """Indices that reorder a palette. kind is 'similar', 'contrasting', or
    an integer group size."""
    d = distance_matrix(rgb, space)
    if isinstance(kind, int):
        return [i for g in groups(d, kind) for i in g]
    return path_order(d, kind)
