"""MCCP: maximum contrast colour picking."""

__version__ = "0.1.0.dev0"

from . import optimise
from .optimise import Anchor, Palette, default_anchors, palette
from .space import Observer, Viewing, viewing
from .mpl import cycler, recolor, use

__all__ = ["Anchor", "Palette", "Observer", "Viewing", "cycler", "default_anchors", "palette",
           "recolor", "use", "viewing"]
