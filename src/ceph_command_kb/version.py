"""Ceph version detection."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from ceph_command_kb.models import CephVersion

logger = logging.getLogger(__name__)

KNOWN_RELEASE_NAMES: dict[int, str] = {
    12: "luminous",
    13: "mimic",
    14: "nautilus",
    15: "octopus",
    16: "pacific",
    17: "quincy",
    18: "reef",
    19: "squid",
    20: "tentacle",
}

VERSION_PATTERN = re.compile(
    r"ceph\s+version\s+(\d+)\.(\d+)\.(\d+)"
    r"(?:\s+\(.*?\))?"
    r"(?:\s+(\w+))?"
)


def detect_ceph_version(timeout: int = 10) -> CephVersion:
    """Detect the installed Ceph version by running `ceph --version`.

    Raises:
        FileNotFoundError: If the ceph binary is not found.
        RuntimeError: If the version string cannot be parsed.
    """
    ceph_path = shutil.which("ceph")
    if ceph_path is None:
        raise FileNotFoundError(
            "ceph binary not found on PATH. "
            "Ensure Ceph is installed and available."
        )

    result = subprocess.run(
        ["ceph", "--version"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    output = result.stdout.strip()
    if result.returncode != 0:
        raise RuntimeError(
            f"'ceph --version' failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )

    match = VERSION_PATTERN.search(output)
    if not match:
        raise RuntimeError(
            f"Could not parse Ceph version from: {output!r}"
        )

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    release_name = (
        match.group(4)
        or KNOWN_RELEASE_NAMES.get(major, "unknown")
    )

    version = CephVersion(
        major=major,
        minor=minor,
        patch=patch,
        release_name=release_name.lower(),
        full_string=output,
    )

    logger.info(
        "Detected Ceph version: %s (%s)",
        version.label(),
        version.full_string,
    )
    return version


def detect_binary_version(binary: str, timeout: int = 10) -> str | None:
    """Attempt to detect the version of a specific binary.

    Returns the version string or None if detection fails.
    """
    binary_path = shutil.which(binary)
    if binary_path is None:
        logger.warning("Binary not found: %s", binary)
        return None

    for flag in ["--version", "-v", "version"]:
        try:
            result = subprocess.run(
                [binary, flag],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except (subprocess.TimeoutExpired, OSError):
            continue

    return None
