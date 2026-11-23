# MCCP: Maximum Contrast Colour Picking

MCCP is a Python package, now being designed, for choosing the colours of a
categorical plot. Given the number of data series N, it will choose N colours
so that the two least distinct colours are as distinct as possible. The
colours are to be computed for that N, for the background of the plot, and for
the conditions under which the plot will be viewed. The first target is
matplotlib.

No package code has yet been written; this document describes the design.

"Contrast" in the name means colour difference in general. Contrast in
lightness against the background is treated separately (Section 2.3).

## 1. The problem

A plot of N data series needs N colours that a reader can tell apart. The
usual practice is to take colours from a fixed palette of K entries. If K is
less than N, colours repeat. If K is greater than N, the first N entries are
used. Palettes built one colour at a time, such as the Glasbey palettes
(Glasbey et al. 2007), are ordered so that the early entries are well
separated and the later ones fill the gaps between them. The first N entries
of such a palette are not the best set of N colours.

A reader is most likely to confuse the two series whose colours are closest.
MCCP therefore maximises the least distance between any two of the N colours,
measured in a colour space in which equal distances appear equally different.
The problem is solved afresh for each N.

## 2. Formulation

### 2.1 Colour difference

The appearance of a colour depends on the conditions under which it is seen.
A colour appearance model, CAM16 (Li et al. 2017), predicts appearance from
the measured colour and the viewing conditions of Section 2.6. CAM16-UCS is a
uniform colour space derived from it, in which distances are intended to
match perceived differences. Its coordinates are $J'$, the lightness, and
$a'$ and $b'$, which measure the red–green and yellow–blue content of the
colour. The difference between two colours is the Euclidean distance

```math
\Delta E' = \sqrt{(\Delta J')^2 + (\Delta a')^2 + (\Delta b')^2}. \tag{1}
```

CIELAB, the commonest colour space for this purpose, predicts perceived
differences less well than CAM02-UCS and CAM16-UCS (Luo et al. 2006; Li et
al. 2017). CIEDE2000 fits small differences well but is not a Euclidean
distance, which makes it awkward to use with the gradient methods of
Section 3.

CAM16-UCS has two limitations that bear on this use. The first concerns
scale. Its constants, taken over from the earlier CAM02-UCS, were fitted to
data with mean colour differences of 2 to 14 CIELAB units (Luo et al. 2006).
Palette colours differ by more: the two closest colours of matplotlib's
default palette, tab10, are 28 CIELAB units apart. At that scale equation (1)
may be expected to rank differences correctly but not to measure them
exactly. Luo et al. also gave constants fitted to large differences alone.
These fit large differences better, though their data still lie below the
scale of a palette, and they will be offered as an option.

The second concerns very dark colours. CAM16 compresses the cone signals by a
function whose slope is infinite at zero (Li et al. 2017). Colours that all
look black on a screen are therefore computed to be well separated. Under
the "screen" conditions of Section 2.6, but without flare, #000019 lies 14.0
units from black. Real displays reflect some room light (flare), which lifts
every colour slightly. MCCP adds a fraction f of the white to every colour
before conversion,

```math
XYZ' = \frac{XYZ + f\,XYZ_w}{1 + f},
```

where $XYZ_w$ is the white, by default with f = 1 %. This makes the slope
finite and reduces the distance between #000019 and black to 8.5 units.

The CAM16 equations, transcribed from Li et al. (2017), are given in
[docs/cam16-reference.md](docs/cam16-reference.md).

### 2.2 Admissible colours

A colour is admissible if a standard (sRGB) display can show it. Each colour is
represented by its red, green and blue values, each between 0 and 1, and
converted to CAM16-UCS for every distance calculation. The restriction to
displayable colours is then a set of simple bounds.

### 2.3 Chosen colours and fixed colours

The N colours to be chosen are written $x_1, \dots, x_N$. Each carries a
radius $r_i$, which is 1 by default. The radius states how much room the
colour needs relative to the others. A colour drawn as a thin line is harder
to distinguish from its neighbours than one drawn as a large marker (Szafir
2018), so it may be given a larger radius.

Colours that are fixed in advance and are not data colours are called
anchors, written $c_k$. They are the background, the colour of axes and text,
and other colours such as those of reference lines. Each anchor has a
clearance $d_k$, the least distance a chosen colour may lie from it.

The background needs a further condition, because distance by equation (1)
does not measure how well a colour shows against a background. The usual
measure of that is the contrast ratio of the Web Content Accessibility
Guidelines (W3C 2018), $(Y_1 + 0.05)/(Y_2 + 0.05)$, where $Y_1$ and $Y_2$ are
the relative luminances of the lighter and darker colour. The examples below
use the "screen" conditions of Section 2.6.

| Colour on white | $\Delta E'$ | $\Delta J'$ | Contrast ratio |
|---|---|---|---|
| Yellow #FFFF00 | 40.3 | 3.4 | 1.07 |
| Green #00FF00 | 50.7 | 14.4 | 1.37 |
| Grey #999999 | 36.1 | 36.1 | 2.85 |

Pure green lies further from white than the grey does, yet it is much harder
to see. The lightness difference $\Delta J'$ orders these colours as the
contrast ratio does. The background is therefore also given a minimum lightness
difference $\Delta J'_b$.

By default the background is white and the axes and text are black. A dark
background is obtained by changing these anchors.

### 2.4 Objective

MCCP maximises a common scale $s$ subject to

```math
\begin{aligned}
\lVert x_i - x_j \rVert &\ge s\,(r_i + r_j) && \text{for every pair of chosen colours,} \\
\lVert x_i - c_k \rVert &\ge d_k\, r_i && \text{for every chosen colour and anchor,} \\
\lvert J'_i - J'_b \rvert &\ge \Delta J'_b\, r_i && \text{for every chosen colour,}
\end{aligned}
\tag{2}
```

with every colour admissible. Here $\lVert\cdot\rVert$ is the distance
$\Delta E'$ of equation (1), $J'_i$ is the lightness of $x_i$, and $J'_b$
that of the background. When all radii equal 1, $s$ is half the distance
between the closest pair. The radius enters all three conditions, so a colour
that needs more room from other colours also stands further from the anchors
and the background.

The value of $s$ is determined by the closest pairs alone, and the other
colours may lie anywhere that does not reduce it. A secondary objective,
applied with $s$ held at its optimum, spreads them apart. It maximises a
smooth approximation to the minimum of all pairwise distances (a soft
minimum), so that every pair, and not only the closest, contributes.

Anchors keep a fixed clearance and do not take part in the maximisation of
$s$. Colours already assigned to data series, as when an existing palette
is extended, are entered instead as fixed members, each with a radius. These
enter the first condition of (2) like chosen colours but are not moved.

### 2.5 Deficient colour vision

About 8 % of men and 0.4 % of women of European descent have a red–green
deficiency of colour vision (Birch 2012). The user may name the deficiencies
to be allowed for. Protanomaly, deuteranomaly and tritanomaly are altered
sensitivities of the long-, medium- and short-wavelength cones respectively,
each stated with a severity from 0 to 1. Severity 1 is the complete loss of
that cone type. Each is simulated by the method of Machado et al. (2009).
Conditions (2) must then hold both for normal vision and for every simulated
deficiency, so the palette is designed for the worst case.

### 2.6 Viewing conditions

CAM16 takes three viewing conditions:

- the adapting luminance $L_A$, the general brightness to which the eye has
  adjusted;
- the relative luminance of the background $Y_b$, on a scale on which white
  is 100;
- the surround, the brightness of the room around the display relative to
  the display: average, dim or dark.

The first two are related by $L_A = L_W Y_b / 100$, where $L_W$ is the
luminance of white in cd/m² (Li et al. 2017).

The user chooses a preset by intended use, and may override any value. The
"screen" preset follows the reference viewing environment of the sRGB
standard (IEC 1999): display white 80 cd/m², ambient illuminance 64 lux and
viewing flare 1 %. The ambient level makes the surround about 5 % of the
display white, which is dim by the classification of Li et al. (2017). Unlike
the standard, which assumes a 20 % grey background, MCCP takes $Y_b$ from the
background anchor, with a lower limit, since the model fails as $Y_b$
approaches zero. Presets for a darkened room and for projection will be
defined in the same way.

## 3. Method

The problem has many local optima. Its discrete form, choosing N colours
from a fixed set of candidates, is NP-hard (Erkut 1990), and MCCP does not
seek a guaranteed global optimum. It works in three stages.

1. Starting sets. The first set is built by farthest-point selection from a
   fixed grid of candidate colours: each new colour is the candidate farthest
   from those already chosen and from the anchors. Further starting sets come
   from random draws with fixed seeds. A palette computed for a nearby N may
   also be supplied as a starting set, after colours are added by
   farthest-point selection or removed from the closest pairs. This keeps the
   colours similar when series are added or removed, and shortens the
   computation.
2. Refinement. Each set is improved continuously by gradient methods. Only
   pairs whose distance is near the current minimum are included in the
   constraints, which keeps large N tractable.
3. Selection. The best refined set is kept and the secondary objective is
   applied.

The same inputs, package version and platform are intended always to give
the same palette.

## 4. Output

### 4.1 Order of the colours

The colours have no natural order, but a plot assigns them to series in the
order given. Two orderings are offered:

- The similar ordering minimises the total distance between consecutive
  colours, so the sequence changes gradually. It suits series that have a
  loose natural order.
- The contrasting ordering maximises that distance, so neighbouring series
  differ as much as possible.

A palette may also be arranged in groups of G colours, each group chosen so
that its own members are as well separated as possible. This suits plots in
which colour is combined with another visual property, for example the first
G series drawn solid, the next G dashed, and so on.

### 4.2 Diagnostics

Each palette is returned with the least distance achieved, and with the
pairs, anchors and colour-vision deficiencies that limit it. It also reports
each colour's distance and lightness difference from each anchor.

### 4.3 Matplotlib

Two helpers are planned. The first sets the colour cycle of a figure. The
second recolours the series already drawn on a set of axes, since N is often
known only after plotting. Legends are rebuilt afterwards, because they hold
copies of the plotted objects.

### 4.4 Test figures

Palettes are inspected on a disc of concentric rings, each divided into N
cells, with every colour once in each ring. The colours are arranged so that
every pair shares a boundary at least twice, at different places on the disc,
so that no single placement decides the comparison. Touching patches are the
easiest comparison a reader can make, and so the disc tends to flatter a
palette. It is accompanied by figures of the closest pairs drawn as thin lines
on the background, of a realistic plot with lines and markers, and of each of
these as seen with each simulated colour-vision deficiency. The arrangement
of the disc is described in [docs/test-figures.md](docs/test-figures.md).

## 5. Relation to other work

The problem is old. Carter and Carter (1982) chose high-contrast sets of
colours for CRT displays. Glasbey et al. (2007) chose sets of a given size,
either one colour at a time or all together by simulated annealing.

Several programs now maximise the least distance for any N. Among them are
Qualpal (Larsson 2025), the glasbey package for Python (McInnes), and
maxdistcolor for MATLAB. Qualpal is the closest to MCCP. It is deterministic,
allows for the background and for deficient colour vision, and can extend an
existing palette. It is available from Python (qualpal-py). It selects from a
fixed set of candidate colours and measures distance by CIEDE2000 by default.

MCCP is designed to differ from these programs in the following respects:

- it will work directly with matplotlib;
- it will use CAM16-UCS, with a flare correction and viewing conditions
  chosen by intended use;
- it will refine colours continuously rather than select them from a fixed
  set;
- each colour may have its own radius;
- the background will have a separate lightness condition;
- it will offer ordered and grouped output, and report diagnostics.

Whether MCCP achieves larger separations than Qualpal or glasbey will be
measured and reported. A fuller review is given in
[docs/prior-work.md](docs/prior-work.md).

## 6. Plans

The first version is to include everything described above, together with:

- a comparison with Qualpal and glasbey for N from 3 to 30, using the same
  distance measure and anchors;
- a trial at N up to 100, to find where the method or the palettes become
  unsatisfactory;
- measurements of how far the palette depends on the viewing conditions and
  on the grid of candidate colours.

The package will depend on numpy and scipy. The tests will use pytest, and
the colour-science package as an independent check of the CAM16 transform.

Later versions may take account of colour preference, for example by
excluding regions of colour that observers tend to dislike, as Colorgorical
does with dark yellow (Gramazio et al. 2017). They may also support print and
wide-gamut displays.

## 7. Use of AI

The design and documentation of this project were produced by an AI system
(Claude, from Anthropic), as were the reviews of the literature. Code, when
written, will be produced in the same way. The author directed the work,
setting its aims, making the design decisions, selecting the sources, and
reviewing the results. Statements of fact have been checked against the
sources cited where these were available.
[docs/prior-work.md](docs/prior-work.md) records which references were
checked and how.

## References

- Birch, J. (2012). Worldwide prevalence of red-green color deficiency.
  Journal of the Optical Society of America A 29(3), 313–320.
- Carter, R. C., and Carter, E. C. (1982). High-contrast sets of colors.
  Applied Optics 21(16), 2936–2939.
- Erkut, E. (1990). The discrete p-dispersion problem. European Journal of
  Operational Research 46(1), 48–60.
- Glasbey, C., van der Heijden, G., Toh, V. F. K., and Gray, A. (2007). Colour
  displays for categorical images. Color Research and Application 32(4),
  304–309.
- Gramazio, C. C., Laidlaw, D. H., and Schloss, K. B. (2017). Colorgorical:
  creating discriminable and preferable color palettes for information
  visualization. IEEE Transactions on Visualization and Computer Graphics
  23(1), 521–530.
- IEC (1999). IEC 61966-2-1: Multimedia systems and equipment. Colour
  measurement and management. Part 2-1: Colour management. Default RGB colour
  space, sRGB.
- Larsson, J. (2025). Qualpal: qualitative color palettes for everyone.
  Journal of Open Source Software 10(114), 8936.
- Li, C., Li, Z., Wang, Z., Xu, Y., Luo, M. R., Cui, G., Melgosa, M., Brill,
  M. H., and Pointer, M. (2017). Comprehensive color solutions: CAM16, CAT16,
  and CAM16-UCS. Color Research and Application 42(6), 703–718.
- Luo, M. R., Cui, G., and Li, C. (2006). Uniform colour spaces based on
  CIECAM02 colour appearance model. Color Research and Application 31(4),
  320–330.
- Machado, G. M., Oliveira, M. M., and Fernandes, L. A. F. (2009). A
  physiologically-based model for simulation of color vision deficiency.
  IEEE Transactions on Visualization and Computer Graphics 15(6), 1291–1298.
- Szafir, D. A. (2018). Modeling color difference for visualization design.
  IEEE Transactions on Visualization and Computer Graphics 24(1), 392–401.
- W3C (2018). Web Content Accessibility Guidelines (WCAG) 2.1.

Software: glasbey, L. McInnes, https://github.com/lmcinnes/glasbey.
maxdistcolor, MATLAB Central File Exchange no. 70215. Qualpal,
https://qualpal.cc.

## Licence

MIT. See [LICENSE](LICENSE).
