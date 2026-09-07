"""
Logging configuration with sensitive data masking and structured formatting.
"""
import logging
import os
import re
from pathlib import Path
from logging.handlers import RotatingFileHandler


class SensitiveDataFilter(logging.Filter):
    """Masks tokens, cookies, auth headers, and passwords from logs."""

    PATTERNS = [
        (re.compile(r"(cf_clearance=)[^;\s]+", re.IGNORECASE), r"\1***MASKED***"),
        (re.compile(r"(_iidt=)[^;\s]+", re.IGNORECASE), r"\1***MASKED***"),
        (re.compile(r"(_vid_t=)[^;\s]+", re.IGNORECASE), r"\1***MASKED***"),
        (re.compile(r"(Authorization:\s*Bearer\s+)[^\s]+", re.IGNORECASE), r"\1***MASKED***"),
        (re.compile(r"(token=)['\"][^'\"]+['\"]", re.IGNORECASE), r"\1'***MASKED***'"),
        (re.compile(r"([A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,})"), r"***DISCORD_TOKEN***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, repl in self.PATTERNS:
                msg = pattern.sub(repl, msg)
            record.msg = msg
        return True


import collections
import time

_RECENT_LOGS = collections.deque(maxlen=200)

class RingBufferLogHandler(logging.Handler):
    """Keeps the last N log lines in memory with timestamp and level for the Web Panel."""
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            _RECENT_LOGS.append({
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "name": record.name,
                "message": msg,
            })
        except Exception:
            self.handleError(record)


def get_recent_logs(limit: int = 50):
    """Returns the most recent log entries."""
    logs = list(_RECENT_LOGS)
    return logs[-limit:]


def setup_logger(
    name: str = "gamblit_redeemer",
    log_level: str = "INFO",
    log_file: str = "logs/app.log",
) -> logging.Logger:
    """Configures and returns the application logger."""
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers if re-initialized
    if logger.handlers:
        return logger

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sensitive_filter = SensitiveDataFilter()

    # Console Handler (Fast)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    logger.addHandler(console_handler)

    # In-memory Ring Buffer Handler for Web Panel live stream
    ring_handler = RingBufferLogHandler()
    ring_formatter = logging.Formatter(fmt="%(message)s")
    ring_handler.setFormatter(ring_formatter)
    ring_handler.addFilter(sensitive_filter)
    logger.addHandler(ring_handler)

    # File Handler with Rotation (max 10MB, 5 backups)
    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)
    logger.addHandler(file_handler)

    return logger

