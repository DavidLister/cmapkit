"""MCCP: maximum contrast colour picking, for categorical palettes."""

from . import optimise
from .optimise import Anchor, Palette, default_anchors, palette

__all__ = ["Anchor", "Palette", "default_anchors", "optimise", "palette"]
