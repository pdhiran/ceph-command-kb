"""Logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    log_dir: Path | None = None,
) -> logging.Logger:
    """Configure the root logger for the application.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional filename for file logging (written into log_dir).
        log_dir: Directory for the log file. Defaults to current directory.

    Returns:
        The configured root logger.
    """
    root = logging.getLogger("ceph_command_kb")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file:
        target = Path(log_dir or ".") / log_file
        target.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(target, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    return root
