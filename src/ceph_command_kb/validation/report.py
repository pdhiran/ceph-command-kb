"""Validation report data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    severity: str
    phase: str
    line: int | None
    command: str
    message: str
    suggested_fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity,
            "phase": self.phase,
            "command": self.command,
            "message": self.message,
        }
        if self.line is not None:
            d["line"] = self.line
        if self.suggested_fix:
            d["suggested_fix"] = self.suggested_fix
        return d


@dataclass
class CommandEntry:
    """One extracted command and its verification result."""

    line: int | None
    raw: str
    parts: list[str]
    verified: bool = False
    exists_in_kb: bool = False
    unknown_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "raw": self.raw,
            "verified": self.verified,
            "exists_in_kb": self.exists_in_kb,
            "unknown_flags": self.unknown_flags,
        }


@dataclass
class ValidationReport:
    script_path: str = ""
    script_type: str = ""
    total_commands: int = 0
    verified_commands: int = 0
    unverified_commands: int = 0
    findings: list[Finding] = field(default_factory=list)
    command_map: list[CommandEntry] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        summary = {
            "errors": self.error_count,
            "warnings": self.warning_count,
            "recommendations": sum(1 for f in self.findings if f.severity == "recommendation"),
            "info": sum(1 for f in self.findings if f.severity == "info"),
        }
        by_phase: dict[str, int] = {}
        for f in self.findings:
            by_phase[f.phase] = by_phase.get(f.phase, 0) + 1

        return {
            "script_path": self.script_path,
            "script_type": self.script_type,
            "total_commands": self.total_commands,
            "verified_commands": self.verified_commands,
            "unverified_commands": self.unverified_commands,
            "summary": summary,
            "findings_by_phase": by_phase,
            "findings": [f.to_dict() for f in self.findings],
            "command_map": [c.to_dict() for c in self.command_map],
        }
