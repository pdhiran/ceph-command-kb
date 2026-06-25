"""Extract Ceph commands from test scripts and automation code.

Handles:
- Shell scripts with direct ceph/rbd/rados commands
- Python cephci automation patterns (shell(), exec_command(), run_ceph_command())
- Raw string commands
- YAML test definitions
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterator

CEPH_BINARIES = frozenset({
    "ceph", "rbd", "rados", "cephadm", "ceph-volume",
    "ceph-authtool", "ceph-bluestore-tool", "ceph-objectstore-tool",
    "cephfs-shell", "crushtool", "monmaptool", "osdmaptool",
})

CEPH_CMD_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(b) for b in sorted(CEPH_BINARIES, key=len, reverse=True))
    + r")\b\s+(.+?)(?:\s*[;|&\n\r]|$)",
    re.MULTILINE,
)

PYTHON_SHELL_PATTERNS = [
    re.compile(r"""(?:shell|exec_command|run_ceph_command|run|exec)\s*\(\s*(?:cmd\s*=\s*)?f["'](.+?)["']\s*\)"""),
    re.compile(r"""(?:shell|exec_command|run_ceph_command|run|exec)\s*\(\s*(?:cmd\s*=\s*)?["'](.+?)["']\s*\)"""),
    re.compile(r"""(?:shell|exec_command|run_ceph_command|run|exec)\s*\(\s*(?:cmd\s*=\s*)?\[(.+?)\]\s*\)"""),
]

PYTHON_CMD_ASSIGN = re.compile(
    r"""(?:cmd|command|cmd_str)\s*=\s*(?:f)?["']((?:ceph|rbd|rados|cephadm|ceph-volume)\s+.+?)["']"""
)


@dataclass
class ExtractedCommand:
    line: int | None
    raw: str
    binary: str
    parts: list[str]
    flags: list[str]
    positional_args: list[str]


def extract_from_text(text: str, script_type: str = "auto") -> list[ExtractedCommand]:
    """Extract Ceph commands from script content.

    Args:
        text: The script content.
        script_type: "python", "shell", "yaml", or "auto" (detect).
    """
    if script_type == "auto":
        script_type = _detect_type(text)

    if script_type == "python":
        return _extract_python(text)
    elif script_type == "shell":
        return _extract_shell(text)
    elif script_type == "yaml":
        return _extract_yaml(text)
    else:
        return _extract_generic(text)


def _detect_type(text: str) -> str:
    if text.strip().startswith("#!/") and ("python" in text[:100] or "pytest" in text[:200]):
        return "python"
    if text.strip().startswith("#!/") and ("bash" in text[:50] or "sh" in text[:50]):
        return "shell"
    if "def test_" in text or "import " in text or "class Test" in text:
        return "python"
    if re.search(r"^\s*-\s+(ceph|rbd|rados)", text, re.MULTILINE):
        return "yaml"
    return "shell"


def _extract_shell(text: str) -> list[ExtractedCommand]:
    commands = []
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        for match in CEPH_CMD_PATTERN.finditer(stripped):
            binary = match.group(1)
            rest = match.group(2).strip()
            cmd_str = f"{binary} {rest}"
            cmd = _parse_command_string(cmd_str, line=i)
            if cmd:
                commands.append(cmd)

    return commands


def _extract_python(text: str) -> list[ExtractedCommand]:
    commands = []
    lines = text.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        matched_this_line = False

        for pattern in PYTHON_SHELL_PATTERNS:
            for match in pattern.finditer(stripped):
                cmd_str = match.group(1)
                if "[" not in cmd_str:
                    cmd_str = _clean_python_string(cmd_str)
                else:
                    cmd_str = _parse_python_list_string(cmd_str)

                if _looks_like_ceph_command(cmd_str):
                    cmd = _parse_command_string(cmd_str, line=i)
                    if cmd:
                        commands.append(cmd)
                        matched_this_line = True

        if not matched_this_line:
            for match in PYTHON_CMD_ASSIGN.finditer(stripped):
                cmd_str = _clean_python_string(match.group(1))
                if _looks_like_ceph_command(cmd_str):
                    cmd = _parse_command_string(cmd_str, line=i)
                    if cmd:
                        commands.append(cmd)
                        matched_this_line = True

    return _deduplicate_by_line(commands)


def _extract_yaml(text: str) -> list[ExtractedCommand]:
    commands = []
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip().lstrip("- ")
        if _looks_like_ceph_command(stripped):
            cmd = _parse_command_string(stripped, line=i)
            if cmd:
                commands.append(cmd)
    return commands


def _extract_generic(text: str) -> list[ExtractedCommand]:
    """Fallback: find any Ceph command strings in the text."""
    commands = []
    for i, line in enumerate(text.split("\n"), 1):
        for match in CEPH_CMD_PATTERN.finditer(line):
            cmd_str = f"{match.group(1)} {match.group(2).strip()}"
            cmd_str = _clean_python_string(cmd_str)
            if _looks_like_ceph_command(cmd_str):
                cmd = _parse_command_string(cmd_str, line=i)
                if cmd:
                    commands.append(cmd)
    return commands


def _parse_command_string(cmd_str: str, line: int | None = None) -> ExtractedCommand | None:
    """Parse a command string into structured parts."""
    cmd_str = cmd_str.strip()
    if not cmd_str:
        return None

    cmd_str = re.sub(r"\{[^}]*\}", "PLACEHOLDER", cmd_str)
    cmd_str = re.sub(r"\$\w+", "VARIABLE", cmd_str)

    tokens = cmd_str.split()
    if not tokens:
        return None

    binary = tokens[0]
    if binary not in CEPH_BINARIES:
        return None

    flags = []
    positional = []
    for token in tokens[1:]:
        if token.startswith("-"):
            flag = token.split("=")[0]
            flags.append(flag)
        elif token not in ("PLACEHOLDER", "VARIABLE"):
            positional.append(token)

    cmd_parts = [binary]
    for token in tokens[1:]:
        if token.startswith("-") or token.startswith("PLACEHOLDER") or token.startswith("VARIABLE"):
            break
        if re.match(r"^[a-zA-Z][\w-]*$", token):
            cmd_parts.append(token)
        else:
            break

    return ExtractedCommand(
        line=line,
        raw=cmd_str,
        binary=binary,
        parts=cmd_parts,
        flags=flags,
        positional_args=positional,
    )


def _clean_python_string(s: str) -> str:
    """Remove Python string artifacts like f-string braces, quotes."""
    s = re.sub(r"\{[^}]*\}", "PLACEHOLDER", s)
    s = s.replace("'", "").replace('"', "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_python_list_string(s: str) -> str:
    """Convert a Python list-like string to a command string."""
    items = re.findall(r"""["']([^"']+)["']""", s)
    return " ".join(items)


def _looks_like_ceph_command(s: str) -> bool:
    if not s:
        return False
    first = s.split()[0] if s.split() else ""
    return first in CEPH_BINARIES


def _deduplicate_by_line(commands: list[ExtractedCommand]) -> list[ExtractedCommand]:
    """Remove duplicate commands from the same line."""
    seen: set[tuple[int | None, str]] = set()
    result = []
    for cmd in commands:
        key = (cmd.line, cmd.raw)
        if key not in seen:
            seen.add(key)
            result.append(cmd)
    return result
