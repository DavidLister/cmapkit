"""cmapkit: colour maps designed in CAM16-UCS.

The shared modules give the colour space and simulated observers (space), the
lightness limits for each background (bounds) and the calibration charts
(calibrate). The subpackage mccp chooses categorical palettes (maximum
contrast colour picking); its main functions are available here.
"""

__version__ = "0.1.0.dev0"

from . import mccp
from .mccp import Anchor, Palette, default_anchors, palette
from .space import Observer, Viewing, viewing
from .mpl import cycler, recolor, use

__all__ = ["Anchor", "Palette", "Observer", "Viewing", "cycler", "default_anchors", "mccp",
           "palette", "recolor", "use", "viewing"]
