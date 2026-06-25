"""Safe command executor — the ONLY component that runs subprocesses.

This module enforces that only help-related commands are ever executed.
It is the sole subprocess boundary in the entire application.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = frozenset({"-h", "--help", "help"})


@dataclass(frozen=True)
class ExecResult:
    command: list[str]
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Return whichever stream has content (some tools print help to stderr)."""
        return self.stdout if self.stdout.strip() else self.stderr


class ExecutorSafetyError(Exception):
    """Raised when a command violates safety constraints."""


class Executor:
    """Runs CLI commands in a controlled, safe manner.

    Safety invariants:
    - Only commands ending with a recognized help flag are executed.
    - No shell=True — prevents injection.
    - Per-command timeout to prevent hangs.
    - Binary must exist on PATH before execution.
    """

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def run_help(self, command_parts: list[str], help_flag: str = "-h") -> ExecResult:
        """Execute a help command safely.

        Args:
            command_parts: The command prefix, e.g. ["ceph", "osd", "pool"].
            help_flag: The help flag to append, e.g. "-h", "--help", "help".

        Returns:
            ExecResult with stdout, stderr, return code.

        Raises:
            ExecutorSafetyError: If the command violates safety constraints.
            FileNotFoundError: If the binary is not found on PATH.
        """
        if not command_parts:
            raise ExecutorSafetyError("Empty command — no binary specified")

        if help_flag not in ALLOWED_SUFFIXES:
            raise ExecutorSafetyError(
                f"Help flag {help_flag!r} is not in the allowed set: "
                f"{ALLOWED_SUFFIXES}"
            )

        full_command = list(command_parts) + [help_flag]
        self._validate_command(full_command)

        binary = full_command[0]
        if shutil.which(binary) is None:
            raise FileNotFoundError(f"Binary not found on PATH: {binary}")

        logger.debug("Executing: %s", " ".join(full_command))

        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return ExecResult(
                command=full_command,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out after %ds: %s", self._timeout, full_command)
            return ExecResult(
                command=full_command,
                stdout="",
                stderr=f"Timed out after {self._timeout}s",
                returncode=-1,
                timed_out=True,
            )

    @staticmethod
    def _validate_command(command: list[str]) -> None:
        """Verify the command ends with a recognized help flag."""
        if not command:
            raise ExecutorSafetyError("Empty command")

        last = command[-1]
        if last not in ALLOWED_SUFFIXES:
            raise ExecutorSafetyError(
                f"Command must end with a help flag ({ALLOWED_SUFFIXES}), "
                f"got: {last!r}"
            )

    def run_help_prefix(self, binary: str, subcommand_parts: list[str]) -> ExecResult:
        """Execute help in prefix mode: `<binary> help <subcommand...>`.

        Used by tools like rbd/rados where `rbd help bench` works
        but `rbd bench -h` just shows top-level help.
        """
        full_command = [binary, "help"] + list(subcommand_parts)

        if shutil.which(binary) is None:
            raise FileNotFoundError(f"Binary not found on PATH: {binary}")

        logger.debug("Executing (prefix mode): %s", " ".join(full_command))

        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return ExecResult(
                command=full_command,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out after %ds: %s", self._timeout, full_command)
            return ExecResult(
                command=full_command,
                stdout="",
                stderr=f"Timed out after {self._timeout}s",
                returncode=-1,
                timed_out=True,
            )

    @staticmethod
    def binary_exists(binary: str) -> bool:
        return shutil.which(binary) is not None
