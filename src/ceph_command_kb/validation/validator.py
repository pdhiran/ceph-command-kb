"""Batch validation engine for Ceph test scripts.

Runs all deterministic validation phases against extracted commands:
1. Command verification (exists in KB)
2. Flag/argument validation (known flags)
3. Cleanup pairing (resources created but not cleaned up)
4. Risk detection (destructive commands)
5. Duplicate detection (identical commands)
"""

from __future__ import annotations

import logging
from collections import Counter

from ceph_command_kb.validation.cleanup_pairs import (
    get_cleanup_commands,
    get_create_command,
    is_cleanup_command,
)
from ceph_command_kb.validation.extractor import ExtractedCommand, extract_from_text
from ceph_command_kb.validation.report import CommandEntry, Finding, ValidationReport
from ceph_command_kb.validation.risk_patterns import DESTRUCTIVE_PATTERNS

logger = logging.getLogger(__name__)


class Validator:
    """Runs deterministic validation phases against a knowledge base."""

    def __init__(self, commands_map: dict[str, dict]) -> None:
        self._commands = commands_map

    def validate(
        self,
        script_content: str,
        script_type: str = "auto",
        script_path: str = "",
    ) -> ValidationReport:
        extracted = extract_from_text(script_content, script_type=script_type)

        report = ValidationReport(
            script_path=script_path,
            script_type=script_type,
            total_commands=len(extracted),
        )

        if not extracted:
            report.findings.append(Finding(
                severity="info",
                phase="extraction",
                line=None,
                command="",
                message="No Ceph commands found in the script",
            ))
            return report

        for cmd in extracted:
            entry = self._verify_command(cmd, report)
            report.command_map.append(entry)

        self._check_cleanup(extracted, report)
        self._check_risks(extracted, report)
        self._check_duplicates(extracted, report)

        report.verified_commands = sum(1 for e in report.command_map if e.verified)
        report.unverified_commands = report.total_commands - report.verified_commands

        return report

    def _verify_command(self, cmd: ExtractedCommand, report: ValidationReport) -> CommandEntry:
        """Phase 1 + 3: Verify command existence and flag validity."""
        command_name = " ".join(cmd.parts)

        entry = CommandEntry(
            line=cmd.line,
            raw=cmd.raw,
            parts=cmd.parts,
        )

        kb_cmd = self._find_command(command_name)

        if kb_cmd is None:
            entry.exists_in_kb = False
            entry.verified = False

            similar = self._find_similar(command_name)
            suggested = similar[0] if similar else None

            report.findings.append(Finding(
                severity="error",
                phase="command_verify",
                line=cmd.line,
                command=cmd.raw,
                message=f"Command not found in knowledge base: {command_name}",
                suggested_fix=f"Did you mean: {suggested}" if suggested else None,
            ))
            return entry

        entry.exists_in_kb = True
        entry.verified = True

        known_flags = set()
        for f in kb_cmd.get("flags", []):
            if f.get("short_form"):
                known_flags.add(f["short_form"])
            if f.get("long_form"):
                known_flags.add(f["long_form"])

        if known_flags:
            for flag in cmd.flags:
                flag_name = flag.split("=")[0]
                if flag_name not in known_flags:
                    entry.unknown_flags.append(flag_name)
                    entry.verified = False

            if entry.unknown_flags:
                report.findings.append(Finding(
                    severity="warning",
                    phase="flag_check",
                    line=cmd.line,
                    command=cmd.raw,
                    message=f"Unknown flags for {command_name}: {', '.join(entry.unknown_flags)}",
                ))

        return entry

    def _check_cleanup(self, commands: list[ExtractedCommand], report: ValidationReport) -> None:
        """Phase 6: Check that created resources have cleanup commands."""
        created: dict[str, ExtractedCommand] = {}
        cleaned: set[str] = set()

        for cmd in commands:
            cmd_name = " ".join(cmd.parts)
            create_key = get_create_command(cmd_name)
            if create_key:
                created[create_key] = cmd

            cleanup_for = is_cleanup_command(cmd_name)
            if cleanup_for:
                cleaned.add(cleanup_for)

        for create_cmd, cmd in created.items():
            if create_cmd not in cleaned:
                expected = get_cleanup_commands(create_cmd)
                if expected:
                    report.findings.append(Finding(
                        severity="warning",
                        phase="cleanup",
                        line=cmd.line,
                        command=cmd.raw,
                        message=f"Resource created but no cleanup found. Expected one of: {', '.join(expected)}",
                    ))

    def _check_risks(self, commands: list[ExtractedCommand], report: ValidationReport) -> None:
        """Phase 8: Detect destructive or risky commands."""
        for cmd in commands:
            cmd_lower = cmd.raw.lower()
            for pattern, severity, message in DESTRUCTIVE_PATTERNS:
                if pattern.lower() in cmd_lower:
                    report.findings.append(Finding(
                        severity=severity,
                        phase="risk",
                        line=cmd.line,
                        command=cmd.raw,
                        message=message,
                    ))

    def _check_duplicates(self, commands: list[ExtractedCommand], report: ValidationReport) -> None:
        """Phase 9: Detect duplicate commands."""
        EXPECTED_REPEATS = {"ceph health", "ceph -s", "ceph status", "ceph osd stat"}

        counter: Counter[str] = Counter()
        for cmd in commands:
            normalized = " ".join(cmd.parts)
            if normalized not in EXPECTED_REPEATS:
                counter[cmd.raw] += 1

        for raw, count in counter.items():
            if count > 1:
                report.findings.append(Finding(
                    severity="info",
                    phase="duplicate",
                    line=None,
                    command=raw,
                    message=f"Command appears {count} times. Consider if this is intentional.",
                ))

    def _find_command(self, name: str) -> dict | None:
        """Look up a command, trying progressively shorter prefixes."""
        parts = name.split()
        for length in range(len(parts), 0, -1):
            candidate = " ".join(parts[:length])
            if candidate in self._commands:
                return self._commands[candidate]
        return None

    def _find_similar(self, name: str) -> list[str]:
        name_lower = name.lower()
        return [
            n for n in self._commands
            if name_lower in n.lower() or n.lower() in name_lower
        ][:5]
