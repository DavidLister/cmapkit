"""hdrmaps: colour maps for images of high dynamic range.

The lightness repeats several times over the data range, so that fine detail
is shown in lightness at every level, while a steady turn of hue tells the
cycles apart. Experimental.
"""

from .figures import default_maps, strip_page
from .maps import IMAGE_VIEW, WAVES, OscillatingMap, max_colourfulness, scale
from .noise import blur_for_length, map_length, noise_range, noise_sd, required_length

__all__ = ["IMAGE_VIEW", "OscillatingMap", "WAVES", "blur_for_length", "default_maps",
           "map_length", "max_colourfulness", "noise_range", "noise_sd", "required_length",
           "scale", "strip_page"]
