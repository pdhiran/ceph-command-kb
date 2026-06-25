"""Tests for the safe command executor."""

import pytest

from ceph_command_kb.discovery.executor import (
    ALLOWED_SUFFIXES,
    Executor,
    ExecutorSafetyError,
)


class TestExecutorSafety:
    def test_rejects_non_help_flags(self):
        executor = Executor()
        with pytest.raises(ExecutorSafetyError):
            executor.run_help(["ceph", "osd", "pool", "create"], help_flag="--force")

    def test_rejects_empty_command(self):
        executor = Executor()
        with pytest.raises(ExecutorSafetyError):
            executor.run_help([], help_flag="-h")

    def test_allowed_suffixes(self):
        assert "-h" in ALLOWED_SUFFIXES
        assert "--help" in ALLOWED_SUFFIXES
        assert "help" in ALLOWED_SUFFIXES
        assert "--force" not in ALLOWED_SUFFIXES

    def test_validates_help_flag(self):
        executor = Executor()
        with pytest.raises(ExecutorSafetyError, match="not in the allowed set"):
            executor.run_help(["some-tool"], help_flag="--version")

    def test_binary_not_found(self):
        executor = Executor()
        with pytest.raises(FileNotFoundError, match="not found on PATH"):
            executor.run_help(["nonexistent-binary-xyz"], help_flag="-h")


class TestExecutorExecution:
    def test_run_help_with_real_binary(self):
        executor = Executor(timeout=5)
        result = executor.run_help(["python3"], help_flag="-h")
        assert result.success
        assert "python" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_binary_exists(self):
        assert Executor.binary_exists("python3")
        assert not Executor.binary_exists("nonexistent-binary-xyz")

    def test_timeout_handling(self):
        executor = Executor(timeout=5)
        result = executor.run_help(["ls"], help_flag="--help")
        assert not result.timed_out
