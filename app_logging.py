r"""
Shared logging setup.

Why this exists: the packaged app runs with PyInstaller `--windowed`, which
means there is NO console and every `print()` / traceback vanishes silently.
Routing everything through here gives us a log file on disk we can actually
read when the .exe misbehaves, while still printing to the console when one
is attached (running from source).

Log file location:
  %LOCALAPPDATA%\WhisperKey\whisperkey.log   (falls back to the app dir)
"""

import logging
import os
import sys

_LOGGER = None


def _log_dir():
    base = os.environ.get("LOCALAPPDATA")
    if base:
        d = os.path.join(base, "WhisperKey")
    else:
        d = os.path.dirname(os.path.abspath(sys.argv[0] or __file__))
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        # Last resort: alongside this module.
        return os.path.dirname(os.path.abspath(__file__))


def get_logger(name: str = "whisperkey") -> logging.Logger:
    """Return the shared, configured logger. Safe to call repeatedly."""
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("whisperkey")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%H:%M:%S"
    )

    log_path = os.path.join(_log_dir(), "whisperkey.log")
    try:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # can't write a log file; console handler below still works

    # Console handler only when a real stdout exists (None under --windowed).
    if sys.stdout is not None:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    logger.debug("logging initialized -> %s", log_path)
    _LOGGER = logger
    return logger


# Convenience module-level logger.
log = get_logger()
