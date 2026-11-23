# Design of MCCP

This note gives the formulation and the method of MCCP as implemented in
version 0.1. The README gives a summary; [results.md](results.md) reports
comparisons, and [calibration.md](calibration.md) the measurement of the
lightness limits.

## 1. The problem

A plot of N data series needs N colours that a reader can tell apart. A
reader is most likely to confuse the two series whose colours are closest.
MCCP therefore maximises the least distance between any two of the N
colours, measured in a colour space in which equal distances appear equally
different, and solves the problem afresh for each N.

## 2. Colour difference

The appearance of a colour depends on the conditions under which it is seen.
A colour appearance model, CAM16 (Li et al. 2017), predicts appearance from
the measured colour and the viewing conditions. CAM16-UCS is a uniform colour
space derived from it. Its coordinates are J', the lightness, and a' and b',
which measure the red–green and yellow–blue content of the colour. MCCP
measures the difference between two colours as

```math
\Delta E = \sqrt{(\Delta J' / K_L)^2 + (\Delta a')^2 + (\Delta b')^2}, \tag{1}
```

with $K_L = 0.77$. The standard space has $K_L = 1$. With the smaller value,
lightness differences count for more. Viewed in the ring figures of
[test-figures.md](test-figures.md), pairs separated mainly in lightness
looked more distinct, and pale pairs of equal lightness less distinct, than
the standard space predicts. The weighting corrected both. The constants of
Luo et al. (2006) for large differences, which also reduce the compression of
colourfulness, did not.

CAM16-UCS has two limitations that bear on this use. Its constants were
fitted to data with mean colour differences of 2 to 14 CIELAB units (Luo et
al. 2006). Palette colours differ by more; the two closest colours of tab10
are 28 CIELAB units apart. At that scale equation (1) may be expected to rank
differences correctly but not to measure them exactly. Second, CAM16
compresses the cone signals by a function whose slope is infinite at zero, so
colours that all look black are computed to be well separated. Real displays
reflect some room light (flare), which lifts every colour slightly. MCCP adds
a fraction f = 1 % of the white to every colour before conversion,

```math
XYZ' = \frac{XYZ + f\,XYZ_w}{1 + f},
```

which makes the slope finite. The CAM16 equations are transcribed in
[cam16-reference.md](cam16-reference.md).

The viewing conditions, called the `screen` preset, are those of the sRGB
reference environment (IEC 1999): display white 80 cd/m², a dim surround, and 1 % flare. The relative
luminance of the background $Y_b$ is taken from the background colour, with
a lower limit of 2, and the adapting luminance is $L_A = 80\,Y_b/100$
cd/m².

## 3. Admissible colours

A colour is admissible if an sRGB display can show it. Each colour is
represented by its red, green and blue values between 0 and 1, so that this
condition is a set of simple bounds.

A colour must also show well against the background. Each colour lies either
darker or lighter than the background, its side. On the darker side its
lightness must lie between a floor $F(h)$, below which it reads as black, and
$J'_b - M(h)$. On the lighter side it must lie between $J'_b + M(h)$ and a
ceiling $C(h)$, above which it reads as white:

```math
F(h_i) \le J'_i \le J'_b - M(h_i) \quad \text{or} \quad
J'_b + M(h_i) \le J'_i \le C(h_i). \tag{2}
```

Here $J'_b$ is the lightness of the background and $h$ the CAM16 hue. The
margin $M(h)$ is the least lightness difference from the background. All
three quantities depend on hue, because the range of colourfulness an sRGB
display can show at a given lightness depends strongly on hue: yellows and
greens can be light and still colourful, blues and violets dark. They are
tabulated at twelve hues, interpolated around the hue circle, and blended
towards values for grey as the colourfulness $M'$ (the distance from the
neutral axis in CAM16-UCS) falls below 20, where hue is weak. The values for
grey were chosen, not measured. Each is the most restrictive of the measured
values for that background and side, except the lowest value on white, which
is 50 rather than 55.

The tables were measured by eye on white, black and #333333 backgrounds
([calibration.md](calibration.md)). The floor comes from the dark side on
white, the ceiling from the light side on the dark backgrounds, and the
margin from the background side of each. On those three backgrounds,
condition (2) reproduces the measured limits exactly. On other backgrounds,
the margin is interpolated linearly in the CIE L* of the background, and the
ceiling between black and #333333.

The side of each colour is fixed by its starting position (Section 6).
Different starts explore different assignments.

The standard mode replaces condition (2) by a single condition on lightness,
$|J'_i - J'_b| \ge \Delta J'_b$, with $\Delta J'_b = 25$, the value of the
lightest colour of tab10 on white.

## 4. Chosen colours, anchors and fixed members

The N colours to be chosen are written $x_1, \dots, x_N$. Each carries a
radius $r_i$, 1 by default, which states how much room the colour needs
relative to the others. A colour drawn as a thin line is harder to
distinguish than one drawn as a large marker (Szafir 2018), so it may be
given a larger radius.

Anchors $c_k$ are fixed colours that are not data colours: the background,
the colour of text and axes, reference lines. Each has a clearance $d_k$, the
least distance a chosen colour may lie from it. By default the anchors are
the background (clearance 20) and black or white text (clearance 15).

Fixed members are colours already assigned to data series, as when a palette
is extended. They take part in the spacing condition (Section 5) like chosen
colours but are not moved.

## 5. Observers and the objective

Deficient colour vision is simulated by the matrices of Machado et al.
(2009), applied to linear sRGB values. Each observer o has a type (normal,
deutan, protan or tritan), a severity from 0 to 1, and a priority $p_o$ in
(0, 1]. The priority is the fraction of the common spacing that observer is
guaranteed. Normal vision has priority 1.

MCCP maximises the scale s subject to

```math
\begin{aligned}
\lVert x_i - x_j \rVert_o &\ge p_o\, s\,(r_i + r_j) && \text{for every pair and observer,} \\
\lVert x_i - c_k \rVert_o &\ge d_k\, r_i && \text{for every colour, anchor and observer,}
\end{aligned}
\tag{3}
```

together with condition (2) for normal vision and the bounds of the sRGB
cube. $\lVert\cdot\rVert_o$ is the distance (1) as seen by observer o. When
all radii are 1 and the normal-vision condition binds, s is half the least
distance for normal vision; when a simulated observer binds, it is half that
observer's least distance divided by its priority.

The default observers are deutan and protan at severity 1 and priority 0.6,
and tritan at severity 1 and priority 0.2. Requiring every observer to see
every pair at the full spacing ($p_o = 1$) confines the palette to the
directions all observers share, essentially lightness and blue–yellow. A
priority of 0.6 keeps most of the normal-vision separation while
guaranteeing a large share to the simulated observers.

The value of s is set by the closest pairs alone. With s held at its
optimum, a secondary objective spreads the remaining colours. It maximises
the sum, over observers and colours, of each colour's soft minimum distance
to the others. A soft minimum is a smooth approximation of the minimum,
$-\beta^{-1}\log\sum_j e^{-\beta d_j}$, which approaches the least $d_j$
as $\beta$ grows.

## 6. Method

The problem has many local optima. Its discrete form, choosing N colours from
a fixed set of candidates, is NP-hard (Erkut 1990), and MCCP does not seek a
guaranteed global optimum. It works in four stages.

1. Starting sets. A grid of 24³ candidate colours is reduced to those
   admissible for each colour's radius. The first set is built by
   farthest-point selection, and each colour is then moved in turn to the
   candidate farthest from the rest, until no move helps (after Schlömer et
   al. 2011). Seven further starting sets are random draws with fixed seeds.
2. Refinement. Each set is improved by L-BFGS-B, a standard gradient method
   for problems with bounds, on a soft minimum of the scaled distances, with penalties for the anchor and lightness conditions,
   at increasing sharpness.
3. Polish. The best three sets are polished by sequential linear
   programming, which maximises the exact minimum within a trust region.
   Only pairs whose distance is near the minimum enter each linear
   programme.
4. Spreading. The best feasible set is spread by the secondary objective of
   Section 5, again by sequential linear programming.

Finally the colours are rounded to 8-bit values. Single colours are then
moved by one step in each channel while this raises the least distance or
removes a violation caused by rounding.

For the same inputs, package version and platform, the result is the same.
Palettes with default settings for N from 1 to 50 on the calibrated
backgrounds are precomputed and stored with the package.

## 7. Output

The colours have no natural order, but a plot assigns them to series in the
order given. Two orderings are offered. The similar ordering approximately
minimises the total distance between consecutive colours, so the sequence
changes gradually. The contrasting ordering approximately maximises it. Both
use nearest-neighbour construction followed by exchange of segments. A palette may also be
arranged in groups of G colours, each group as well separated as possible
within itself, for example to pair the first G series with solid lines and
the next G with dashed.

Each palette carries diagnostics: the scale achieved for each observer, the
binding pairs, the distance of each colour from each anchor, the slack in
condition (2), and the source of the lightness limits.

The matplotlib helpers `use` and `cycler` set the colour cycle. `recolor`
recolours the lines and single-colour scatter plots already drawn on a set of
axes, and rebuilds the legend.

## 8. Experimental options

Three options are available but not yet established. The power mean of the
scaled distances with exponent −p (`power=p`) is an alternative to max-min.
In trials at N = 10 and 16 it gave no better distribution of the smallest
distances than max-min. The constants for large differences (`ucs="LCD"`)
are a second option. Viewing presets other than "screen" have provisional
values.

## References

- Erkut, E. (1990). The discrete p-dispersion problem. European Journal of
  Operational Research 46(1), 48–60.
- IEC (1999). IEC 61966-2-1: Multimedia systems and equipment. Colour
  measurement and management. Part 2-1: Colour management. Default RGB colour
  space, sRGB.
- Li, C., et al. (2017). Comprehensive color solutions: CAM16, CAT16, and
  CAM16-UCS. Color Research and Application 42(6), 703–718.
- Luo, M. R., Cui, G., and Li, C. (2006). Uniform colour spaces based on
  CIECAM02 colour appearance model. Color Research and Application 31(4),
  320–330.
- Machado, G. M., Oliveira, M. M., and Fernandes, L. A. F. (2009). A
  physiologically-based model for simulation of color vision deficiency.
  IEEE Transactions on Visualization and Computer Graphics 15(6), 1291–1298.
- Schlömer, T., Heck, D., and Deussen, O. (2011). Farthest-point optimized
  point sets with maximized minimum distance. Proc. ACM SIGGRAPH Symposium on
  High Performance Graphics, 135–142.
- Szafir, D. A. (2018). Modeling color difference for visualization design.
  IEEE Transactions on Visualization and Computer Graphics 24(1), 392–401.
