"""Matplotlib helpers.

matplotlib is imported only when these functions are called, so the rest of
the package does not depend on it.
"""

from .mccp.optimise import palette


def _opaque_hex(colour):
    """'#rrggbb' of a colour, or None if it is fully transparent."""
    import matplotlib.colors as mcolors
    if isinstance(colour, str) and colour.lower() == "none":
        return None
    rgba = mcolors.to_rgba(colour)
    return None if rgba[3] == 0 else mcolors.to_hex(rgba, keep_alpha=False)


def _background(ax=None):
    """The colour behind the data of ax: its own face colour, or, if that is
    transparent or hidden (as for twin axes), that of an axes in the same
    place, then the figure's. Without ax, the current style's defaults."""
    import matplotlib as mpl
    if ax is None:
        return (_opaque_hex(mpl.rcParams["axes.facecolor"])
                or _opaque_hex(mpl.rcParams["figure.facecolor"]) or "#ffffff")
    candidates = [ax]
    if not ax.patch.get_visible() or _opaque_hex(ax.get_facecolor()) is None:
        box = ax.get_position().bounds
        candidates += [o for o in ax.figure.axes
                       if o is not ax and o.get_position().bounds == box]
    for a in candidates:
        if a.patch.get_visible():
            c = _opaque_hex(a.get_facecolor())
            if c:
                return c
    return _opaque_hex(ax.figure.get_facecolor()) or "#ffffff"


def cycler(n, **kwargs):
    """A matplotlib cycler of n MCCP colours. Keyword arguments go to
    cmapkit.palette; the background defaults to the current style's axes
    colour."""
    from cycler import cycler as _cycler
    kwargs.setdefault("background", _background())
    return _cycler(color=palette(n, **kwargs).hex)


def use(n, ax=None, **kwargs):
    """Set the colour cycle to n MCCP colours: for one set of axes if ax is
    given, otherwise for all later figures. The background is taken from ax,
    or from the current style, unless given. Returns the palette."""
    import matplotlib as mpl
    kwargs.setdefault("background", _background(ax))
    pal = palette(n, **kwargs)
    if ax is None:
        mpl.rcParams["axes.prop_cycle"] = mpl.cycler(color=pal.hex)
    else:
        ax.set_prop_cycle(color=pal.hex)
    return pal


SUPPORTED = "lines drawn in data coordinates (plot, step, semilogy, ...) and single-colour scatter plots"


def series(ax):
    """The artists recolor() would recolour on ax, in the order they were
    added, and a list of the kinds of artist it cannot handle."""
    from matplotlib.collections import Collection, PathCollection
    from matplotlib.lines import Line2D
    out, unsupported = [], []
    for c in ax.containers:
        unsupported.append(type(c).__name__)
    for p in ax.patches:
        unsupported.append(type(p).__name__)
    for a in ax.get_children():
        if isinstance(a, Line2D) and a in ax.lines:
            if a.get_transform() != ax.transData:
                continue  # axhline, axvline and other reference lines
            if a.get_label() == "_nolegend_":
                unsupported.append("box plot or other composite plot")
                continue
            out.append(a)
        elif isinstance(a, PathCollection):
            if a.get_array() is not None:
                unsupported.append("scatter with c= (colour-mapped)")
            else:
                out.append(a)
        elif isinstance(a, Collection) and a in ax.collections:
            unsupported.append(type(a).__name__)
    return out, unsupported


def _axes_of(target):
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    if target is None:
        return [plt.gca()]
    if isinstance(target, Figure):
        return list(target.axes)
    if isinstance(target, (list, tuple)):
        return list(target)
    return [target]


def _set_colour(artist, colour):
    from matplotlib.collections import Collection
    from matplotlib.patches import Patch
    if isinstance(artist, Collection):
        fc = artist.get_facecolor()
        if len(fc) and fc[0][3] > 0:
            artist.set_facecolor(colour)
        artist.set_edgecolor(colour)
    elif isinstance(artist, Patch):
        artist.set_facecolor(colour)
        artist.set_edgecolor(colour)
    else:
        artist.set_color(colour)


def recolor(target=None, artists=None, legend=True, strict=True, by_label=False, **kwargs):
    """Recolour the series already drawn with MCCP colours.

    target is a set of axes (default: the current one), a list of axes, or a
    figure; series on all of them are coloured together, so that no two share
    a colour. Series are lines drawn in data coordinates and single-colour
    scatter plots, in the order they were added. Reference lines (axhline,
    axvline) are left alone. The series may instead be named with artists=.

    Error bars, bars, histograms, filled areas, box plots and colour-mapped
    scatter plots cannot be matched to one colour per series. With strict=True
    (the default) they raise ValueError; otherwise they are left alone.

    With by_label=True, series with the same label (for example the same
    quantity in several panels) share a colour, and the palette has one
    colour per distinct label.

    Legends on the axes and the figure are updated in place. The background
    is taken from the first axes unless given. Returns the palette."""
    axes = _axes_of(target)
    if artists is None:
        artists, unsupported = [], []
        for ax in axes:
            a, u = series(ax)
            artists += a
            unsupported += u
        if unsupported and strict:
            raise ValueError("recolor() supports " + SUPPORTED + "; found "
                             + ", ".join(sorted(set(unsupported)))
                             + ". Pass artists=[...] or strict=False.")
    if not artists:
        raise ValueError("No series to recolour.")
    kwargs.setdefault("background", _background(axes[0]))
    keys = []
    for a in artists:
        label = a.get_label()
        keys.append(label if by_label and label and not label.startswith("_") else id(a))
    distinct = list(dict.fromkeys(keys))
    pal = palette(len(distinct), **kwargs)
    colour_of = dict(zip(distinct, pal.hex))
    by_text = {}
    for a, k in zip(artists, keys):
        _set_colour(a, colour_of[k])
        label = a.get_label()
        if label and not label.startswith("_"):
            by_text.setdefault(label, colour_of[k])
    if legend:
        legends = [ax.get_legend() for ax in axes]
        legends += list(axes[0].figure.legends)
        for leg in legends:
            if leg is None:
                continue
            for text, handle in zip(leg.get_texts(), leg.legend_handles):
                c = by_text.get(text.get_text())
                if c is not None and handle is not None:
                    _set_colour(handle, c)
    return pal


__all__ = ["cycler", "use", "recolor", "series"]
