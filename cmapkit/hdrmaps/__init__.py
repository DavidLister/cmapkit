"""hdrmaps: colour maps for images of high dynamic range.

A map for such an image must be long (a large total colour difference from
one end to the other), so that small differences in the data show at every
level, and uniform, so that equal differences look equal. The maps of this
subpackage are paths through the colours of a large MCCP palette, made
smooth and kept from coming near themselves by a curve optimiser, and
uniform for observers of normal and deficient colour vision. Their length
is matched to the noise of the image by a Gaussian blur. The method and its
limits are given in docs/hdrmaps.md.

The main functions:

- names, info, path_map, colormap: the shipped maps (library.py);
- render: an image in colour through a map, with the blur matched to its
  noise (library.py);
- assess: the length, uniformity and separation of any map for each
  observer (measure.py);
- noise_sd, noise_range, required_length, blur_for_length, map_length: the
  noise model (noise.py).

The modules paths and curve make new maps (tools/make_hdrmaps.py shows
how). The module maps holds an earlier approach, maps whose lightness
repeats over the range (OscillatingMap); it is kept for comparison, and
these maps fold back on themselves (docs/hdrmaps.md, section 2).
"""

from .figures import default_maps, strip_page
from .library import colormap, info, names, path_map, render
from .maps import IMAGE_VIEW, WAVES, OscillatingMap, max_colourfulness, scale
from .measure import assess
from .noise import blur_for_length, map_length, noise_range, noise_sd, required_length

__all__ = ["IMAGE_VIEW", "OscillatingMap", "WAVES", "assess", "blur_for_length", "colormap",
           "default_maps", "info", "map_length", "max_colourfulness", "names", "noise_range",
           "noise_sd", "path_map", "render", "required_length", "scale", "strip_page"]
