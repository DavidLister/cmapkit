# CAM16 / CAM16-UCS forward model: implementation reference

Transcribed from Li et al. (2017), *Comprehensive color solutions: CAM16,
CAT16, and CAM16-UCS*, Color Res. Appl. 42(6):703–718, Appendix A Part 1 and
Appendix B. The transcription was made by an AI system (see the README,
Section 9) from the published paper. An implementation written from it
reproduces the test vector at the end of this note to every printed digit.
Check it against the paper before relying on any constant.

## Inputs

- Sample X, Y, Z (Y of white = 100)
- Adopted white X_w, Y_w, Z_w
- Background luminance factor Y_b
- Adapting luminance L_A in cd/m². Coupled to Y_b by
  L_A = L_W · Y_b / Y_w (Eq. A1), where L_W is the luminance of white.
- Surround: F, c, N_c (table below)

## Surround parameters (Table A1)

| Surround | F | c | N_c |
|---|---|---|---|
| Average | 1.0 | 0.69 | 1.0 |
| Dim | 0.9 | 0.59 | 0.9 |
| Dark | 0.8 | 0.525 | 0.8 |

- The surround is classed by the ratio SR of the luminance of the surround
  to that of the display white: dark if SR = 0, dim if 0 < SR < 0.2, and
  average if SR ≥ 0.2.
- F and N_c may be linearly interpolated as functions of c.

## CAT16 matrix (Eq. 18)

```
M16 = [[ 0.401288,  0.650173, -0.051461],
       [-0.250268,  1.204414,  0.045854],
       [-0.002079,  0.048952,  0.953127]]

M16^-1 = [[ 1.86206786, -1.01125463,  0.14918677],
          [ 0.38752654,  0.62144744, -0.00897398],
          [-0.01584150, -0.03412294,  1.04996444]]
```

## Step 0: viewing-condition constants (computed once)

```
[R_w, G_w, B_w] = M16 · [X_w, Y_w, Z_w]
D    = F · (1 − (1/3.6) · exp((−L_A − 42) / 92))        clamp to [0, 1]
D_R  = D · Y_w / R_w + 1 − D        (and likewise D_G, D_B)
k    = 1 / (5·L_A + 1)
F_L  = 0.2 · k^4 · (5·L_A) + 0.1 · (1 − k^4)^2 · (5·L_A)^(1/3)
n    = Y_b / Y_w
z    = 1.48 + sqrt(n)
N_bb = N_cb = 0.725 · (1/n)^0.2
R_wc = D_R · R_w                     (and likewise G_wc, B_wc)
R_aw = 400 · (F_L·R_wc/100)^0.42 / ((F_L·R_wc/100)^0.42 + 27.13) + 0.1
A_w  = (2·R_aw + G_aw + B_aw/20 − 0.305) · N_bb
```

N_bb diverges as Y_b → 0.

## Per-sample steps

```
1. [R, G, B] = M16 · [X, Y, Z]
2. R_c = D_R · R                     (and likewise G_c, B_c)
3. R_a = sign(R_c) · 400 · (F_L·|R_c|/100)^0.42 / ((F_L·|R_c|/100)^0.42 + 27.13) + 0.1
   The +0.1 is not mirrored for negative values. For every colour in the sRGB
   cube, including after simulation of deficient colour vision, the cone
   signals are non-negative (checked numerically), so the negative branch is
   not reached in MCCP.
4. a = R_a − 12·G_a/11 + B_a/11
   b = (R_a + G_a − 2·B_a) / 9
   h = atan2(b, a) in degrees, wrapped to [0, 360)
5. e_t = (cos(h·π/180 + 2) + 3.8) / 4
6. A = (2·R_a + G_a + B_a/20 − 0.305) · N_bb
7. J = 100 · (A / A_w)^(c·z)
8. Q = (4/c) · sqrt(J/100) · (A_w + 4) · F_L^0.25
9. t = (50000/13) · N_c · N_cb · e_t · sqrt(a² + b²) / (R_a + G_a + 21·B_a/20)
   C = t^0.9 · sqrt(J/100) · (1.64 − 0.29^n)^0.73
   M = C · F_L^0.25
   s = 100 · sqrt(M / Q)
```

Hue quadrature H (Table A2) is not needed for UCS distances.

## CAM16-UCS (Eqs. A3–A5)

```
J' = 1.7·J / (1 + 0.007·J)
M' = ln(1 + 0.0228·M) / 0.0228
a' = M' · cos(h)
b' = M' · sin(h)
ΔE' = sqrt(ΔJ'² + Δa'² + Δb'²)
```

Li et al. also give an optional power correction, ΔE = 1.41 · ΔE'^0.63,
after Huang et al. (2015), as cited there. MCCP does not use it.

### LCD and SCD variants (not in Li et al.)

These come from Luo et al. (2006) via colour-science's
`COEFFICIENTS_UCS_LUO2006`, given as (K_L, c₁, c₂):

| Variant | K_L | c₁ | c₂ |
|---|---|---|---|
| LCD | 0.77 | 0.007 | 0.0053 |
| SCD | 1.24 | 0.007 | 0.0363 |
| UCS | 1.00 | 0.007 | 0.0228 |

General form (unverified against Luo 2006):

```
J'  = (1 + 100·c₁)·J / (1 + c₁·J)
M'  = ln(1 + c₂·M) / c₂
ΔE' = sqrt((ΔJ'/K_L)² + Δa'² + Δb'²)
```

## Test vector

Li et al. give no full worked example. This vector is from colour-science's
`XYZ_to_CAM16` docstring. It does not exercise the UCS step or the branch for
negative cone signals, which need separate tests.

- Inputs: XYZ = [19.01, 20.00, 21.78], XYZ_w = [95.05, 100.00, 108.88],
  L_A = 318.31, Y_b = 20, average surround
- Outputs: J = 41.7312079, C = 0.1033557, h = 217.0679597, s = 2.3450150,
  Q = 195.3717089, M = 0.1074367, H = 275.5949861
