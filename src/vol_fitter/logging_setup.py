"""One place to configure logging; every module calls get_logger(__name__).

Besides the console, the last LOG_BUFFER_LINES formatted lines are kept in
memory so the web console can show them (GET /api/logs). Nothing is written
to disk; the buffer clears when the process restarts.
"""
from __future__ import annotations

import logging
from collections import deque

from vol_fitter import config

LOG_BUFFER_LINES = 2000
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


class _RingBuffer(logging.Handler):
    def __init__(self, size: int) -> None:
        super().__init__()
        self.lines: deque[str] = deque(maxlen=size)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # a broken record must never take the app down
            self.handleError(record)


_buffer = _RingBuffer(LOG_BUFFER_LINES)
_buffer.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))


def configure_logging(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(level=level or config.LOG_LEVEL, format=_FORMAT, datefmt=_DATEFMT)
    logging.getLogger().addHandler(_buffer)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def recent_logs(limit: int = LOG_BUFFER_LINES) -> list[str]:
    """The newest `limit` log lines, oldest first."""
    lines = list(_buffer.lines)
    return lines[-limit:] if limit > 0 else []
