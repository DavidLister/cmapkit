"""hdrmaps: colour maps for images of high dynamic range.

The lightness repeats several times over the data range, so that fine detail
is shown in lightness at every level, while a steady turn of hue tells the
cycles apart. Experimental.
"""

from .figures import default_maps, strip_page
from .maps import IMAGE_VIEW, WAVES, OscillatingMap, max_colourfulness, scale

__all__ = ["IMAGE_VIEW", "OscillatingMap", "WAVES", "default_maps", "max_colourfulness",
           "scale", "strip_page"]
