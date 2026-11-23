# Earlier work on maximally distinct colour sets

This note reviews work related to MCCP. The citations were checked on
2026-11-22 against abstracts, publisher listings, package source code, and
the full texts of Li et al. (2017), Szafir (2018), Gramazio et al. (2017) and
Larsson (2025). References not confirmed are marked "unchecked" in the list
at the end.

## 1. Colour sets of maximum separation

The problem of choosing colours that are as distinct as possible is old. Kelly
(1965) gave a hand-chosen list of 22 colours of maximum contrast. Carter and
Carter (1982) computed high-contrast sets in CIELUV for CRT displays, and
maximised the least distance among the colours of the set.

Glasbey et al. (2007) treated the same problem in CIELAB for the display of
categorical images. They gave two methods: one adds colours one at a time,
each as far as possible from those already chosen; the other uses simulated
annealing to choose a set of a given size. The second method is a joint
optimisation for a fixed N.

Several programs now maximise the least distance for any N:

| Program | Method | Metric | Notes |
|---|---|---|---|
| Qualpal (Larsson 2025); C++, command line, R, Python, web | Farthest-point selection over a fixed candidate set, with swaps until no swap raises the minimum (after Schlömer et al. 2011). Deterministic. | CIEDE2000 (default), DIN99d, CIE76 | Background colour, palette extension, colour-deficient observers of several types and severities (Machado et al. 2009). About 0.1 s for 10 colours from 1000 candidates. Python binding: qualpal-py. |
| glasbey (McInnes), Python | Sequential selection on a 64³ RGB grid, followed by refinement that moves one member of the closest pair at a time (on by default) | CAM02-UCS | Bounds on lightness, chroma and hue; extension of a fixed palette; option for colour-deficient observers |
| maxdistcolor, MATLAB (File Exchange 70215) | Greedy start followed by cyclic coordinate descent; deterministic | OKLab (default) | Excludes background and existing colours; lightness and chroma limits. Algorithm description partly unchecked. |

Griffioen and Kiselev (2016) added new lines to a metro map. They chose new
colours to maximise the least distance among themselves and from the colours
already on the map, in CIEDE2000 and CIE76, within a gamut. This is the
problem of MCCP with anchors. They report that adding colours one at a time
did about as well as choosing them jointly. Maji and Dingliana (2022)
maximised the least Euclidean distance in CIELAB for N colours jointly.

## 2. Other palette generators

| Work | Method | Notes |
|---|---|---|
| colorcet glasbey sets | Precomputed lists made by Glasbey's method, starting from black and white | Using the first N entries brings back the problem MCCP is meant to avoid. |
| distinctipy (Roberts et al.) | Sequential: tries the corners, edges and faces of the RGB cube, then 1000 random candidates per colour | Weighted RGB distance (a "redmean" approximation). Optional filter for colour deficiency. |
| iwanthue (Jacomy, médialab) | k-means (default) or force-directed repulsion in CIELAB, within hue, chroma and lightness ranges | k-means spreads colours to cover the region and does not maximise separation directly. Repeated attempts keep the result with the largest minimum distance. |
| Colorgorical (Gramazio et al. 2017) | Sequential randomised selection in quantised CIELAB | See below. |
| Palettailor (Lu et al. 2021); Fang et al. (2017) | Optimisation that takes account of the data | Which series need contrast depends on where they lie on the plot. |
| Petroff (2021) | Minimum-distance and colour-deficiency constraints with a learned preference model | Source of matplotlib's petroff6, petroff8 and petroff10 styles. |
| okpalette | Sequential, in OKLab, accounting for the background | Its documentation states that it is not a global optimiser. |
| Okabe and Ito (2008), and similar palettes | Chosen by hand | Fixed K. |

Colorgorical bears directly on MCCP. It restricts L* to 25 to 85 so that colours
show on black or white, and it excludes or penalises a region of dark yellow.
Each candidate is scored on four measures:

- CIEDE2000 distance
- difference of colour names (after Heer and Stone 2012)
- uniqueness of the colour name, which had no measurable effect
- pair preference

Each score is the minimum over the candidate's pairings with colours already
chosen. In tests with 3, 5 and 8 colours, a larger minimum distance gave fewer
errors but lower preference. Name difference predicted discrimination better
than CIEDE2000 distance.

## 3. Colour spaces and colour difference

CIEDE2000 (Luo, Cui and Rigg 2001) is the standard formula for small colour
differences. It is not a Euclidean distance, which makes it awkward to
optimise.

CAM02-UCS (Luo, Cui and Li 2006) is a uniform colour space derived from the
CIECAM02 appearance model, with Euclidean distances. Its constants were fitted
to combined data on small and large differences. Luo et al. also gave LCD and
SCD constant sets, fitted to large and small differences separately. The
viridis colour maps of matplotlib were designed in CAM02-UCS (Smith and van der
Walt 2015).

CAM16 and CAM16-UCS (Li et al. 2017) succeed CIECAM02 and CAM02-UCS.

- CAM16 performs chromatic adaptation in a single space, using a new matrix,
  and avoids several numerical faults of CIECAM02.
- CAM16-UCS uses the same constants as CAM02-UCS (c₁ = 0.007, c₂ = 0.0228), so
  its uniformity rests on the fit of Luo et al. (2006). The data of that fit
  have mean differences of 2.0 (small) and 11.1 (large) CIELAB units, and no
  data set has a mean above 14.3. The closest pair of matplotlib's tab10
  palette is 28 CIELAB units apart, about twice the largest mean.
- The compression function retains an infinite slope at zero (p. 704).
- Li et al. do not define LCD or SCD variants of CAM16-UCS. MCCP offers the
  LCD constants of Luo et al. (2006), applied by analogy, as the experimental
  option `ucs="LCD"`.

The equations are transcribed in [cam16-reference.md](cam16-reference.md).

OKLab (Ottosson 2020) is a simple space with Euclidean distances. It is the
default metric of maxdistcolor.

Stone, Szafir and Setlur (2014) and Szafir (2018) measured how the threshold of
colour difference grows as marks become smaller. Szafir's model scales the
three CIELAB axes separately, so its threshold surface is an ellipsoid, with
separate fits for points, bars and lines.

- The b* (blue–yellow) threshold is the largest at every size.
- For points (0.25° to 2°), the L* threshold depends least on size, and the a*
  and b* thresholds strongly.
- For lines (0.05° to 0.35°), the effect of size is small. L* is the axis most
  sensitive to size, and for the thinnest lines its threshold exceeds that of
  a*.

The model has three limits:

- It was fitted near threshold only.
- Both marks in each comparison had the same size, and the background was
  white.
- Szafir notes that the scaling may not carry over to CIECAM02-type metrics.

## 4. Optimisation

Choosing p of n candidate points to maximise the least distance between them is
the discrete p-dispersion problem (Erkut 1990), which is NP-hard.

- Farthest-point selection is within a factor of two of the optimum when the
  distance obeys the triangle inequality, and no polynomial method does better
  unless P = NP (Ravi, Rosenkrantz and Tayi 1994).
- Gonzalez (1985) proved the same factor for farthest-point selection in the
  related k-centre problem.
- Schlömer, Heck and Deussen (2011) moved each point of a set in turn to the
  place farthest from the others, and so raised the minimum distance. Qualpal
  adopts this method.

With unequal radii, the continuous problem becomes the packing of unequal
spheres in a container.

## References

Entries marked "unchecked" were not confirmed against a primary or
publisher's source. Other documents also cite Birch (2012), confirmed from
its PubMed abstract; IEC (1999), whose reference viewing environment was
confirmed from a secondary summary only; and W3C (2018).

- Carter, R. C., and Carter, E. C. (1982). High-contrast sets of colors.
  Applied Optics 21(16), 2936–2939.
- Erkut, E. (1990). The discrete p-dispersion problem. European Journal of
  Operational Research 46(1), 48–60.
- Fang, H., et al. (2017). Categorical colormap optimization with
  visualization case studies. IEEE TVCG 23(1), 871–880.
- Glasbey, C., van der Heijden, G., Toh, V. F. K., and Gray, A. (2007). Colour
  displays for categorical images. Color Research and Application 32(4),
  304–309.
- Gonzalez, T. F. (1985). Clustering to minimize the maximum intercluster
  distance. Theoretical Computer Science 38, 293–306. Pages checked; title
  unchecked.
- Gramazio, C. C., Laidlaw, D. H., and Schloss, K. B. (2017). Colorgorical:
  creating discriminable and preferable color palettes for information
  visualization. IEEE TVCG 23(1), 521–530.
- Griffioen, S., and Kiselev, A. (2016). Painting new lines: maximizing
  color difference in metro maps. Mathematical Intelligencer 38, 25–31.
  arXiv:1504.00140.
- Heer, J., and Stone, M. (2012). Color naming models for color selection,
  image editing and palette design. Proc. CHI 2012. Unchecked.
- Kelly, K. L. (1965). Twenty-two colors of maximum contrast. Color
  Engineering 3(6). Unchecked.
- Larsson, J. (2025). Qualpal: qualitative color palettes for everyone.
  Journal of Open Source Software 10(114), 8936.
- Li, C., Li, Z., Wang, Z., Xu, Y., Luo, M. R., Cui, G., Melgosa, M., Brill,
  M. H., and Pointer, M. (2017). Comprehensive color solutions: CAM16, CAT16,
  and CAM16-UCS. Color Research and Application 42(6), 703–718.
- Lu, K., Feng, M., Chen, X., Sedlmair, M., Deussen, O., Lischinski, D.,
  Cheng, Z., and Wang, Y. (2021). Palettailor: discriminable colorization for
  categorical data. IEEE TVCG 27(2), 475–484.
- Luo, M. R., Cui, G., and Li, C. (2006). Uniform colour spaces based on
  CIECAM02 colour appearance model. Color Research and Application 31(4),
  320–330.
- Luo, M. R., Cui, G., and Rigg, B. (2001). The development of the CIE 2000
  colour-difference formula: CIEDE2000. Color Research and Application 26(5),
  340–350. Unchecked.
- Machado, G. M., Oliveira, M. M., and Fernandes, L. A. F. (2009). A
  physiologically-based model for simulation of color vision deficiency.
  IEEE TVCG 15(6), 1291–1298.
- Maji, S., and Dingliana, J. (2022). Perceptually optimized color selection
  for visualization. arXiv:2205.14472.
- Okabe, M., and Ito, K. (2008). Color universal design (CUD): how to make
  figures and presentations that are friendly to colorblind people. Web
  document.
- Ottosson, B. (2020). A perceptual color space for image processing. Web
  article. Unchecked.
- Petroff, M. A. (2021). Accessible color sequences for data visualization.
  arXiv:2107.02270. Title unchecked.
- Ravi, S. S., Rosenkrantz, D. J., and Tayi, G. K. (1994). Heuristic and
  special case algorithms for dispersion problems. Operations Research 42(2),
  299–310.
- Schlömer, T., Heck, D., and Deussen, O. (2011). Farthest-point optimized
  point sets with maximized minimum distance. Proc. ACM SIGGRAPH Symposium on
  High Performance Graphics, 135–142.
- Smith, N. J., and van der Walt, S. (2015). A better default colormap for
  matplotlib. Talk, SciPy 2015. Unchecked.
- Stone, M., Szafir, D. A., and Setlur, V. (2014). An engineering model for
  color difference as a function of size. Proc. 22nd IS&T Color and Imaging
  Conference, 253–258.
- Szafir, D. A. (2018). Modeling color difference for visualization design.
  IEEE TVCG 24(1), 392–401.

Software: glasbey (L. McInnes), colorcet (HoloViz), distinctipy (J. Roberts et
al.), iwanthue (médialab, Sciences Po), maxdistcolor (MATLAB File Exchange
70215), okpalette.
