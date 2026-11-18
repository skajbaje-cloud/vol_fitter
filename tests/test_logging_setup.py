from vol_fitter.logging_setup import get_logger, recent_logs


def test_recent_logs_keeps_formatted_lines_newest_last():
    log = get_logger("vol_fitter.test_logging")
    log.info("first line")
    log.warning("second line")
    last = recent_logs(2)
    assert "INFO" in last[0] and last[0].endswith("vol_fitter.test_logging: first line")
    assert "WARNING" in last[1] and last[1].endswith("second line")
    assert recent_logs(0) == []
