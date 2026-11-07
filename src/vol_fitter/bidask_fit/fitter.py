"""Fit any vol model inside bid-ask. The model is a black box: model(p, quotes) -> vols.

Pipeline: solve (with the optional previous-fit anchor and its guard) ->
status check -> outlier classification -> at most one refit without outliers,
warm-started from the first fit, unless a guard rail says excluding them is unsafe.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from vol_fitter.bidask_fit.models import (
    DEFAULT_CFG, FitConfig, FitResult, FitStatus, QuoteClass, SolveOutcome,
)
from vol_fitter.bidask_fit.outliers import OutlierClassifier, class_array
from vol_fitter.bidask_fit.penalty import ExpWallPenalty
from vol_fitter.bidask_fit.report import FitReporter
from vol_fitter.bidask_fit.residuals import ModelFn, PenaltyFn, ResidualFunction
from vol_fitter.bidask_fit.spread import SpreadBuilder
from vol_fitter.logging_setup import get_logger

logger = get_logger(__name__)


class BidAskFitter:
    def __init__(self, cfg: FitConfig = DEFAULT_CFG):
        self.cfg = cfg
        self.penalty = ExpWallPenalty(cfg)
        self.spreads = SpreadBuilder(cfg)
        self.classifier = OutlierClassifier(cfg)
        self.reporter = FitReporter(cfg, self.penalty)

    def fit(
        self,
        model: ModelFn,
        quotes: pd.DataFrame,
        p0,
        bounds,
        p_prev=None,
        model_penalty: PenaltyFn | None = None,
    ) -> FitResult:
        lb, ub = (np.asarray(b, dtype=float) for b in bounds)
        p0 = np.clip(np.asarray(p0, dtype=float), lb, ub)
        p_prev = None if p_prev is None else np.asarray(p_prev, dtype=float)
        flags: list[str] = []

        usable = SpreadBuilder.usable(quotes)
        if not usable.all():
            flags.append(f"dropped {int((~usable).sum())} quotes with neither bid nor ask vol")
        fit_q = quotes[usable]
        if fit_q.empty:
            logger.warning("no usable quotes; nothing to fit")
            return self._result(model, quotes, usable, np.zeros(0, bool), class_array(len(quotes), QuoteClass.DROPPED),
                                SolveOutcome(p0, False, "no usable quotes", np.nan, 0.0), None, flags)

        first = self._solve(model, fit_q, p0, (lb, ub), p_prev, model_penalty)
        spread = self.spreads.build(fit_q)
        sig = ResidualFunction(model, fit_q, spread, self.penalty, self.cfg).model_vols(first.p)
        v_ask, v_bid = self.penalty.violations(sig, spread)
        classes = self.classifier.classify(fit_q, v_ask, v_bid, spread.expiry_code)

        final, p_first, excluded = first, None, np.zeros(len(fit_q), bool)
        is_out = classes == QuoteClass.OUTLIER.value
        if is_out.any():
            guard = self.classifier.guard_message(classes, spread.expiry_code)
            if guard:
                logger.warning(guard)
                flags.append(guard)
            else:
                flags.append(f"refit without {int(is_out.sum())} outlier(s)")
                logger.info("refitting without %d outlier(s)", int(is_out.sum()))
                final = self._solve(model, fit_q[~is_out], first.p, (lb, ub), p_prev, model_penalty)
                p_first, excluded = first.p, is_out
        n_miss = int((classes == QuoteClass.MODEL_MISS.value).sum())
        if n_miss:
            flags.append(f"{n_miss} model_miss quote(s)")

        all_classes = class_array(len(quotes), QuoteClass.DROPPED)
        all_classes[usable] = classes
        return self._result(model, quotes, usable, excluded, all_classes, final, p_first, flags)

    # ---- solving -----------------------------------------------------------------

    def _solve(self, model, q, p0, bounds, p_prev, model_penalty) -> SolveOutcome:
        """Least squares with the anchor; the guard backs lambda off if anchoring costs quotes."""
        spread = self.spreads.build(q)
        lam = self.cfg.lam_a if p_prev is not None else 0.0
        anchored = self._least_squares(model, q, spread, p0, bounds, p_prev, lam, model_penalty)
        if lam <= 0 or not self.cfg.anchor_guard:
            return anchored

        free = self._least_squares(model, q, spread, p0, bounds, None, 0.0, model_penalty)
        n_free = self._n_outside(model, q, spread, free.p)
        for attempt in range(self.cfg.anchor_max_backoffs + 1):
            n_anch = self._n_outside(model, q, spread, anchored.p)
            if n_anch <= n_free:
                return anchored
            if attempt == self.cfg.anchor_max_backoffs:
                break
            lam /= self.cfg.anchor_backoff
            logger.debug("anchor costs %d quote(s) (%d vs %d outside); lambda -> %g", n_anch - n_free, n_anch, n_free, lam)
            anchored = self._least_squares(model, q, spread, anchored.p, bounds, p_prev, lam, model_penalty)
        logger.info("anchor relaxed: every lambda left more quotes outside than the unanchored fit")
        return replace(free, anchor_relaxed=True)

    def _least_squares(self, model, q, spread, p0, bounds, p_prev, lam, model_penalty) -> SolveOutcome:
        resid = ResidualFunction(model, q, spread, self.penalty, self.cfg, p_prev, lam, model_penalty)
        res = least_squares(resid, p0, bounds=bounds, method="trf", x_scale="jac", max_nfev=self.cfg.max_nfev)
        return SolveOutcome(p=res.x, success=bool(res.success), message=str(res.message),
                            objective=float(2.0 * res.cost), anchor_lambda=lam)

    def _n_outside(self, model, q, spread, p) -> int:
        sig = ResidualFunction(model, q, spread, self.penalty, self.cfg).model_vols(p)
        return int((self.penalty.raw_x(sig, spread) > self.cfg.inside_tol).sum())

    # ---- reporting ---------------------------------------------------------------

    def _result(self, model, quotes, usable, excluded, classes, final: SolveOutcome, p_first, flags) -> FitResult:
        spread = self.spreads.build(quotes)
        sig = ResidualFunction(model, quotes, spread, self.penalty, self.cfg).model_vols(final.p)
        table = self.reporter.quote_table(quotes, sig, spread)
        table["classification"] = classes
        table["excluded"] = ~usable
        table.loc[table.index[usable], "excluded"] = excluded
        used = ~table["excluded"].to_numpy()
        pct, by_expiry = self.reporter.pct_inside(table, used)

        x_capped = int(table.loc[used, "x_capped"].sum())
        if x_capped:
            flags.append(f"{x_capped} quote(s) beyond x_max (no gradient)")
        outside_frac = 1.0 - pct
        status = FitStatus.OK
        if not final.success:
            status = FitStatus.FAILED
            flags.append(f"optimizer failed: {final.message}")
        elif outside_frac > self.cfg.max_outside_frac:
            status = FitStatus.FAILED
            flags.append(f"{outside_frac:.0%} of quotes outside (> {self.cfg.max_outside_frac:.0%})")
        if final.anchor_relaxed:
            flags.append("anchor_relaxed")

        logger.info("fit %s: %d quotes, %.1f%% inside, objective %.4g", status.value, int(used.sum()), 100 * pct, final.objective)
        return FitResult(
            p=final.p, status=status, objective=final.objective, n_quotes=int(used.sum()),
            pct_inside=pct, pct_inside_by_expiry=by_expiry, quotes=table, flags=flags,
            p_first=p_first, refit_delta=None if p_first is None else final.p - p_first,
            anchor_lambda=final.anchor_lambda, anchor_relaxed=final.anchor_relaxed, cfg=self.cfg,
        )


def fit(model: ModelFn, quotes: pd.DataFrame, p0, bounds, cfg: FitConfig = DEFAULT_CFG,
        p_prev=None, model_penalty: PenaltyFn | None = None) -> FitResult:
    """Functional entry point matching the module spec."""
    return BidAskFitter(cfg).fit(model, quotes, p0, bounds, p_prev=p_prev, model_penalty=model_penalty)
