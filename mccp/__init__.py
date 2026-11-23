"""MCCP: maximum contrast colour picking. Prototype."""

from .optimise import Anchor, Palette, default_anchors, palette
from .space import Observer, Viewing, viewing

__all__ = ["Anchor", "Palette", "Observer", "Viewing", "default_anchors", "palette", "viewing"]
