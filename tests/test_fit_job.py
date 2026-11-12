"""run_fit_job argument checks (the fitting itself is covered by test_bidask_fit / test_delta_smile)."""
import pytest

from vol_fitter.orchestration.fit_run import run_fit_job


def test_snapshot_mode_needs_a_timestamp():
    with pytest.raises(ValueError, match="snapshot_ts"):
        run_fit_job(None, "X", "snapshot")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown fit mode"):
        run_fit_job(None, "X", "everything")
