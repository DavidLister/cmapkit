"""Matplotlib helpers.

matplotlib is imported only when these functions are called, so the rest of
the package does not depend on it.
"""

from .optimise import palette
from .space import to_hex


def _background(ax):
    import matplotlib.colors as mcolors
    return mcolors.to_hex(ax.get_facecolor(), keep_alpha=False)


def cycler(n, **kwargs):
    """A matplotlib cycler of n MCCP colours. Keyword arguments go to
    mccp.palette (for example background=...)."""
    from cycler import cycler as _cycler
    return _cycler(color=palette(n, **kwargs).hex)


def use(n, ax=None, **kwargs):
    """Set the colour cycle to n MCCP colours: for one set of axes if ax is
    given, otherwise for all later figures. The background is taken from ax
    when it is given and background is not. Returns the palette."""
    import matplotlib as mpl
    if ax is not None and "background" not in kwargs:
        kwargs["background"] = _background(ax)
    pal = palette(n, **kwargs)
    if ax is None:
        mpl.rcParams["axes.prop_cycle"] = mpl.cycler(color=pal.hex)
    else:
        ax.set_prop_cycle(color=pal.hex)
    return pal


SUPPORTED = "lines (plot, step, semilogy, ...) and scatter plots with a single colour"


def series(ax):
    """The artists recolor() would recolour, in the order they were added."""
    from matplotlib.collections import Collection, PathCollection
    from matplotlib.lines import Line2D
    out, unsupported = [], []
    for c in ax.containers:
        unsupported.append(type(c).__name__)
    for a in ax.get_children():
        if isinstance(a, Line2D):
            if a in ax.lines:
                out.append(a)
        elif isinstance(a, PathCollection):
            if a.get_array() is not None:
                unsupported.append("scatter with c= (colour-mapped)")
            else:
                out.append(a)
        elif isinstance(a, Collection) and a in ax.collections:
            unsupported.append(type(a).__name__)
    return out, unsupported


def recolor(ax=None, artists=None, legend=True, strict=True, **kwargs):
    """Recolour the series already drawn on ax with len(series) MCCP colours.

    Series are lines and single-colour scatter plots, in the order they were
    added; pass artists= to choose them yourself. Error bars, bars, filled
    areas, stack plots and colour-mapped scatter plots cannot be matched to
    one colour per series; with strict=True (the default) they raise
    ValueError, otherwise they are left alone. The legend, if present, is
    rebuilt. The background is taken from the axes unless given. Returns the
    palette."""
    import matplotlib.pyplot as plt
    ax = plt.gca() if ax is None else ax
    if artists is None:
        artists, unsupported = series(ax)
        if unsupported and strict:
            raise ValueError("recolor() supports " + SUPPORTED + "; found "
                             + ", ".join(sorted(set(unsupported)))
                             + ". Pass artists=[...] or strict=False.")
    if not artists:
        raise ValueError("No series to recolour.")
    kwargs.setdefault("background", _background(ax))
    pal = palette(len(artists), **kwargs)
    from matplotlib.collections import PathCollection
    for a, c in zip(artists, pal.hex):
        if isinstance(a, PathCollection):
            a.set_facecolor(c)
            a.set_edgecolor(c)
        else:
            a.set_color(c)
    old = ax.get_legend()
    if legend and old is not None:
        title = old.get_title().get_text()
        ax.legend(loc=old._loc, title=title or None)
    return pal


__all__ = ["cycler", "use", "recolor", "series", "to_hex"]
