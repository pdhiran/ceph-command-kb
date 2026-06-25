"""Generic fallback parser for unrecognized help formats.

Applies broad heuristics to extract whatever structure it can from
arbitrary help text. Used when no specialized parser matches.
"""

from __future__ import annotations

import re

from ceph_command_kb.models import Argument, ArgumentType, Flag, ParseResult
from ceph_command_kb.parsing.base import BaseParser

USAGE_PATTERNS = [
    re.compile(r"^\s*(?:usage|synopsis)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
]

FLAG_PATTERN = re.compile(
    r"^\s+"
    r"(?:(-\w)(?:\s*[,|]\s*)?)?"
    r"(--[\w][\w-]*)?"
    r"(?:\s*[= ]\s*(\S+))?"
    r"\s{2,}(.+)$",
    re.MULTILINE,
)

POSITIONAL_SECTION = re.compile(
    r"^(?:positional arguments|commands?|subcommands?)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

SUBCOMMAND_LINE = re.compile(
    r"^\s{2,4}(\w[\w-]*)\s{2,}(.+)$",
)


class GenericParser(BaseParser):
    """Best-effort parser for arbitrary help output."""

    def parse(self, raw_help: str, command_parts: list[str] | None = None) -> ParseResult:
        result = ParseResult()

        result.usage = self._extract_usage(raw_help)
        result.description = self._extract_description(raw_help)
        result.flags = self._extract_flags(raw_help)
        result.subcommand_names = self._extract_subcommands(raw_help)
        result.arguments = self._extract_arguments(raw_help)

        return result

    def can_parse(self, raw_help: str) -> bool:
        return True

    def _extract_usage(self, text: str) -> str | None:
        for pattern in USAGE_PATTERNS:
            match = pattern.search(text)
            if match:
                usage = match.group(1).strip()
                lines = [usage]
                start = match.end()
                for line in text[start:].split("\n"):
                    stripped = line.strip()
                    if stripped and (stripped.startswith("-") or stripped.startswith("[")):
                        break
                    if line.startswith("    ") or line.startswith("\t"):
                        lines.append(stripped)
                    else:
                        break
                return " ".join(lines)
        return None

    def _extract_description(self, text: str) -> str:
        lines = text.strip().split("\n")
        if not lines:
            return ""

        desc_lines = []
        in_description = False

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if lower.startswith("usage:") or lower.startswith("synopsis:"):
                in_description = False
                continue
            if lower.startswith("description:"):
                in_description = True
                rest = stripped[len("description:"):].strip()
                if rest:
                    desc_lines.append(rest)
                continue
            if re.match(r"^(options|arguments|commands|subcommands|positional|optional)\s*:", stripped, re.IGNORECASE):
                break
            if in_description and stripped:
                desc_lines.append(stripped)
            elif not in_description and not desc_lines:
                if stripped and not stripped.startswith("-") and not stripped.startswith("usage"):
                    first_usage = text.lower().find("usage")
                    first_options = text.lower().find("option")
                    pos = text.find(line)
                    if first_usage != -1 and pos > first_usage and (first_options == -1 or pos < first_options):
                        desc_lines.append(stripped)
                        in_description = True

        return " ".join(desc_lines)

    def _extract_flags(self, text: str) -> list[Flag]:
        flags = []
        seen = set()

        for match in FLAG_PATTERN.finditer(text):
            short = match.group(1)
            long = match.group(2)
            value_name = match.group(3)
            description = match.group(4).strip() if match.group(4) else ""

            key = (short, long)
            if key in seen:
                continue
            seen.add(key)

            takes_value = value_name is not None and not value_name.startswith("-")

            flags.append(Flag(
                short_form=short,
                long_form=long,
                description=description,
                takes_value=takes_value,
                value_name=value_name if takes_value else None,
            ))

        return flags

    def _extract_subcommands(self, text: str) -> list[str]:
        subcommands = []
        in_subcommand_section = False

        for line in text.split("\n"):
            if POSITIONAL_SECTION.match(line):
                in_subcommand_section = True
                continue

            if in_subcommand_section:
                if not line.strip():
                    if subcommands:
                        break
                    continue
                if re.match(r"^\S", line) and not line.startswith(" "):
                    break

                match = SUBCOMMAND_LINE.match(line)
                if match:
                    name = match.group(1)
                    if not name.startswith("-") and not name.startswith("<"):
                        subcommands.append(name)

        return subcommands

    def _extract_arguments(self, text: str) -> list[Argument]:
        args = []
        in_args_section = False

        for line in text.split("\n"):
            lower = line.strip().lower()
            if re.match(r"^(?:positional arguments|arguments)\s*:", lower):
                in_args_section = True
                continue
            if re.match(r"^(?:optional arguments|options|commands|subcommands)\s*:", lower):
                in_args_section = False
                continue

            if in_args_section:
                stripped = line.strip()
                if not stripped:
                    continue
                angle_match = re.match(r"<(\w[\w-]*)>(?:\s{2,}(.+))?", stripped)
                if angle_match:
                    args.append(Argument(
                        name=angle_match.group(1),
                        description=angle_match.group(2) or "",
                        required=True,
                        arg_type=ArgumentType.POSITIONAL,
                    ))

        return args
