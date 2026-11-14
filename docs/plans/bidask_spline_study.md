# Bid-ask spline study: where does smile curvature peak?

## Motivation

The current per-expiry model, on z_old = Phi^-1(call delta),

    sigma(z) = atm + skew*z + kappa_put*(z+)^2 + kappa_call*(z-)^2

has s''(z) = 2*kappa on each side of 50 delta: curvature is a step at ATM by construction
and can never peak in the wings. Lee's moment formula says total variance grows at most
linearly in log-strike, i.e. sigma(z) is asymptotically linear in z and s''(z) -> 0 in both
far wings. So a smile that is convex near ATM must have a curvature profile that rises and
then decays. The study measures that profile without a parametric model.

## Coordinates

Study axis (increases with strike): z = Phi^-1(1 - call delta) = -d1. With k = ln(K/F):

    z(sigma; k) = k / (sigma*sqrt(T)) - sigma*sqrt(T)/2
    dz/dsigma   = -(z + sigma*sqrt(T)) / sigma

A quote's bid IV and ask IV sit at different z (about 0.1 per vol point at z = 2, sigma = 20%,
T = 0.25), so each quote is a slanted segment from (z_b, sigma_b) to (z_a, sigma_a).

## The constraint is linear

For a curve sigma = s(z), its vol at strike k is the fixed point sigma_m = s(z(sigma_m; k)).
h(sigma) = s(z(sigma; k)) - sigma is strictly decreasing whenever

    s(z) + s'(z) * (z + s(z)*sqrt(T)) > 0                      (*)

(strike -> delta is one-to-one along the smile; checked after the fit). Then

    sigma_b <= sigma_m <= sigma_a   <=>   s(z_b) >= sigma_b  and  s(z_a) <= sigma_a

Two linear inequalities per quote, at abscissae fixed by the quote itself. A missing bid IV
(zero bid / below intrinsic) drops the lower one; a missing ask IV drops the upper one.

## The fit

s(z) = sum_j c_j B_j(z), cubic B-splines on a uniform knot grid over the quotes' z-range
(spacing about 0.15). Objective:

    minimise  integral s'''(z)^2 dz  +  eps * sum_i (s(z_mid,i) - sigma_mid,i)^2  +  M * sum xi
    s.t.      s(z_b,i) >= sigma_b,i - xi_b,i,   s(z_a,i) <= sigma_a,i + xi_a,i,   xi >= 0

- Third-derivative penalty: zero for quadratics, so constant curvature is free and curvature
  varies only where the quotes force it. (Penalising s'' would bias curvature down.)
- eps: tiny tie-break toward mids (the feasible set is usually not a single curve).
- M * sum(xi): exact L1 penalty. xi = 0 whenever the quotes are consistent; the few xi > 0 are
  genuinely conflicting quotes (crossed put/call intervals, stale prices) = outliers.

Solved through the dual: with H = 2(P + eps*Bm'Bm), the dual is the box QP

    min_{0 <= lambda <= M}  1/2 lambda' (G H^-1 G') lambda + (h + G H^-1 q)' lambda

(L-BFGS-B), primal c = -H^-1 (q + G' lambda). Active constraints are lambda > 0; slacked ones
are lambda = M. Works in vol points (x100) for conditioning.

## Outputs per expiry

- s(z), s'(z), s''(z) on a grid inside the data range (no extrapolation: the s''' penalty
  extrapolates quadratically, which breaks Lee).
- Bid/ask points with active and slack flags; number and size of conflicts.
- s''(0) (ATM), and per wing the peak location z*, peak height s''(z*), and whether the peak
  is interior (curvature turns over inside the data) or at the edge (still rising at the last
  quote).
- Check of (*) on the grid.
- The current model's step (2*kappa_put for z < 0, 2*kappa_call for z > 0) for comparison.

"Peaks on the wings" is then testable: s''(z*) > s''(0) with z* interior, on each side.

## Next, if confirmed

One hyperbola per wing in z-space:

    sigma(z) = a + b*z + sum_w c_w * (sqrt((z - m_w)^2 + l_w^2) - l_w)

Each term adds curvature c_w*l_w^2 / ((z - m_w)^2 + l_w^2)^(3/2): a smooth bump at m_w of
width l_w, decaying as |z|^-3. Continuous at ATM, peaked wings, linear (Lee) tails. The
study's z* and peak widths seed m_w and l_w.

## Where it lives

- `smile/spline_points.py`: quotes -> bid/ask constraint points.
- `smile/bidask_spline.py`: the QP and the curvature statistics; data classes in `smile/models.py`.
- `orchestration/spline_run.py`: loads a snapshot and fits every expiry (cached per snapshot).
- `GET /api/spline/{name}/{snapshot_ts}`; Analysis tab, "Curvature study" view.
