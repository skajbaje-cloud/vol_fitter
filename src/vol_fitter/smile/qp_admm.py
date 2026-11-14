"""Small convex QP with L1-softened one-sided bounds, by ADMM (OSQP's scheme) plus an exact polish.

    minimise  1/2 x'Hx + q'x + M * sum_i dist(A_i x, [l_i, u_i])

M * dist is an exact penalty: bounds hold whenever they can, and the few that can't are broken
by the least amount. Its prox is closed-form, so ADMM needs no slack variables. After ADMM,
the active set (bounds touching, bounds broken) is solved exactly as an equality QP.
Multipliers follow OSQP: y_i <= 0 on a lower bound, >= 0 on an upper one, |y_i| <= M.
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


class SoftBoundQP:
    def __init__(self, max_iter: int = 3000, tol: float = 1e-5, alpha: float = 1.6, sigma: float = 1e-8):
        # ADMM only has to find the active set roughly; _polish makes the answer exact.
        self.max_iter, self.tol, self.alpha, self.sigma = max_iter, tol, alpha, sigma

    def solve(self, H, q, A, lower, upper, M: float) -> tuple[np.ndarray, np.ndarray, bool]:
        """Returns (x, y, polished). Normalise H to O(1) first; M is in the same units as the objective."""
        n, m = H.shape[0], A.shape[0]
        x, z, y = np.zeros(n), np.zeros(m), np.zeros(m)
        rho = 1.0
        fac = cho_factor(H + self.sigma * np.eye(n) + rho * A.T @ A)
        for it in range(1, self.max_iter + 1):
            xt = cho_solve(fac, self.sigma * x - q + A.T @ (rho * z - y))
            zt = A @ xt
            x = self.alpha * xt + (1 - self.alpha) * x
            zh = self.alpha * zt + (1 - self.alpha) * z
            z_new = self._prox(zh + y / rho, lower, upper, M / rho)
            y = y + rho * (zh - z_new)
            z = z_new
            if it % 25:
                continue
            Ax = A @ x
            r_prim = np.max(np.abs(Ax - z), initial=0.0)
            r_dual = np.max(np.abs(H @ x + q + A.T @ y), initial=0.0)
            s_prim = max(np.max(np.abs(Ax), initial=0.0), np.max(np.abs(z), initial=0.0), 1.0)
            s_dual = max(np.max(np.abs(H @ x)), np.max(np.abs(A.T @ y), initial=0.0), np.max(np.abs(q)), 1.0)
            if r_prim <= self.tol * s_prim and r_dual <= self.tol * s_dual:
                break
            if it % 200 == 0:   # OSQP's rho update: balance the two residuals, then refactor
                new = rho * np.sqrt((r_prim / s_prim) / max(r_dual / s_dual, 1e-30))
                new = float(np.clip(new, 1e-6, 1e6))
                if new > 5 * rho or new < rho / 5:
                    rho = new
                    fac = cho_factor(H + self.sigma * np.eye(n) + rho * A.T @ A)
        else:
            logger.debug("ADMM stopped at %d iterations (primal %.2e, dual %.2e)", self.max_iter, r_prim, r_dual)
        polished = self._polish(H, q, A, lower, upper, M, x, y)
        if polished is not None:
            return polished[0], polished[1], True
        return x, y, False

    @staticmethod
    def _prox(v, lower, upper, t):
        """prox of t * dist(., [lower, upper]), elementwise."""
        p = np.clip(v, lower, upper)
        d = v - p
        return np.where(np.abs(d) <= t, p, v - np.sign(d) * t)

    def _polish(self, H, q, A, lower, upper, M, x, y, max_rounds: int = 300):
        """Exact solution by active-set refinement from ADMM's guess. Rows must be one-sided
        (lower or upper finite, not both). States: free, held at the bound, broken (y = +-M)."""
        side = np.where(np.isfinite(lower), -1.0, 1.0)          # sign y takes when the bound binds
        bound = np.where(side < 0, lower, upper)
        tol_y = 1e-4 * M
        broken = np.abs(y) >= M - tol_y
        held = (np.abs(y) > tol_y) & ~broken
        n = H.shape[0]
        for _ in range(max_rounds):
            y_fixed = np.where(broken, side * M, 0.0)
            Aa = A[held]
            kkt = np.block([[H + self.sigma * np.eye(n), Aa.T], [Aa, -1e-12 * np.eye(len(Aa))]])
            try:
                sol = np.linalg.solve(kkt, np.concatenate([-q - A.T @ y_fixed, bound[held]]))
            except np.linalg.LinAlgError:
                return None
            xp, yp = sol[:n], y_fixed.copy()
            yp[held] = sol[n:]
            # One change per round (several at once cycles): worst wrong-way multiplier, then an
            # over-priced hold, then the most violated free bound, then a break that isn't needed.
            gap = side * (A @ xp - bound)                 # > 0: the bound is broken
            eps = 1e-9 * max(1.0, np.max(np.abs(bound)))
            pull = np.where(held, yp * side, np.inf)      # < 0: a held bound pulling the wrong way
            cost = np.where(held, np.abs(yp), 0.0)
            free_gap = np.where(~held & ~broken, gap, -np.inf)
            spare = np.where(broken, gap, np.inf)
            if pull.min() < -tol_y:
                held[np.argmin(pull)] = False
            elif cost.max() > M + tol_y:
                i = int(np.argmax(cost))
                held[i], broken[i] = False, True
            elif free_gap.max() > eps:
                held[np.argmax(free_gap)] = True
            elif spare.min() < -eps:
                i = int(np.argmin(spare))
                broken[i], held[i] = False, True
            else:
                return xp, yp
        logger.debug("polish did not settle in %d rounds", max_rounds)
        return None
