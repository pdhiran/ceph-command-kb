"""Parser for Python argparse-style help output.

Handles tools that use Python's argparse module, such as cephadm and ceph-volume.
Recognizes the standard argparse sections: usage, description, positional arguments,
optional arguments, and subcommands.
"""

from __future__ import annotations

import re

from ceph_command_kb.models import Argument, ArgumentType, Flag, ParseResult
from ceph_command_kb.parsing.base import BaseParser

ARGPARSE_FLAG = re.compile(
    r"^\s+"
    r"(?:"
    r"(-\w)\s*,\s*(--[\w][\w-]*)"            # -h, --help
    r"|(--[\w][\w-]*)\s*,\s*(-\w)"            # --verbose, -v
    r"|(-\w)"                                  # -h alone
    r"|(--[\w][\w-]*)"                         # --help alone
    r")"
    r"(?:\s+(\S+))?"
    r"\s{2,}(.+)$",
    re.MULTILINE,
)

SUBCOMMAND_WITH_BRACES = re.compile(r"\{([^}]+)\}")


class ArgparseParser(BaseParser):
    """Parser for Python argparse-style help output."""

    def parse(self, raw_help: str, command_parts: list[str] | None = None) -> ParseResult:
        result = ParseResult()
        sections = self._split_sections(raw_help)

        raw_usage = sections.get("usage", "")
        result.usage, embedded_desc = self._split_usage_description(raw_usage)
        result.description = sections.get("description", "") or embedded_desc
        result.flags = self._parse_optional_args(
            sections.get("optional arguments", "") or sections.get("options", "")
        )
        result.arguments = self._parse_positional_args(sections.get("positional arguments", ""))
        subcommands, sub_descs = self._extract_subcommand_names(raw_help, sections)
        result.subcommand_names = subcommands
        result.subcommand_descriptions = sub_descs

        return result

    def can_parse(self, raw_help: str) -> bool:
        lower = raw_help.lower()
        return (
            "optional arguments:" in lower
            or "options:" in lower
            or "positional arguments:" in lower
        ) and "usage:" in lower

    def _split_sections(self, text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []

        lines = text.split("\n")
        i = 0

        for line in lines:
            stripped = line.strip()

            usage_match = re.match(r"^usage:\s*(.*)", stripped, re.IGNORECASE)
            if usage_match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = "usage"
                current_lines = [usage_match.group(1)]
                continue

            section_match = re.match(
                r"^(positional arguments|optional arguments|options|subcommands?|description)\s*:\s*$",
                stripped,
                re.IGNORECASE,
            )
            if section_match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = section_match.group(1).lower()
                current_lines = []
                continue

            if current_key:
                current_lines.append(line)
            elif stripped and current_key is None:
                if "description" not in sections:
                    current_key = "description"
                    current_lines = [stripped]

        if current_key:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections

    @staticmethod
    def _split_usage_description(raw_usage: str) -> tuple[str | None, str]:
        """Argparse embeds the description after a blank line in the usage block."""
        if not raw_usage:
            return None, ""
        parts = re.split(r"\n\s*\n", raw_usage, maxsplit=1)
        usage = parts[0].strip() if parts else None
        desc = parts[1].strip() if len(parts) > 1 else ""
        return usage, desc

    def _parse_optional_args(self, section: str) -> list[Flag]:
        flags: list[Flag] = []
        if not section:
            return flags

        for match in ARGPARSE_FLAG.finditer(section):
            # Groups: 1,2 = "-h, --help" | 3,4 = "--verbose, -v" | 5 = "-h" | 6 = "--help"
            short = match.group(1) or match.group(4) or match.group(5)
            long = match.group(2) or match.group(3) or match.group(6)
            value_name = match.group(7)
            description = match.group(8).strip() if match.group(8) else ""

            takes_value = (
                value_name is not None
                and not value_name.startswith("-")
                and value_name not in ("True", "False")
            )

            flags.append(Flag(
                short_form=short,
                long_form=long,
                description=description,
                takes_value=takes_value,
                value_name=value_name if takes_value else None,
            ))

        return flags

    def _parse_positional_args(self, section: str) -> list[Argument]:
        args: list[Argument] = []
        if not section:
            return args

        lines = section.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("-"):
                continue
            if stripped.startswith("{"):
                continue

            match = re.match(r"^(\w[\w-]*)(?:\s{2,}(.+))?$", stripped)
            if match:
                name = match.group(1)
                desc = match.group(2) or ""
                args.append(Argument(
                    name=name,
                    description=desc.strip(),
                    required=True,
                    arg_type=ArgumentType.POSITIONAL,
                ))

        return args

    def _extract_subcommand_names(
        self, raw_help: str, sections: dict[str, str]
    ) -> tuple[list[str], dict[str, str]]:
        subcommands: list[str] = []
        descriptions: dict[str, str] = {}

        brace_match = SUBCOMMAND_WITH_BRACES.search(sections.get("usage", ""))
        if brace_match:
            candidates = brace_match.group(1).split(",")
            subcommands = [c.strip() for c in candidates if c.strip() and not c.strip().startswith("-")]

        positional = sections.get("positional arguments", "")
        if positional:
            if not subcommands:
                brace_in_positional = SUBCOMMAND_WITH_BRACES.search(positional)
                if brace_in_positional:
                    candidates = brace_in_positional.group(1).split(",")
                    subcommands = [c.strip() for c in candidates if c.strip()]

            for line in positional.split("\n"):
                stripped = line.strip()
                match = re.match(r"^(\w[\w-]*)(?:\s{2,}(.+))?$", stripped)
                if match:
                    name = match.group(1)
                    desc = (match.group(2) or "").strip()
                    if not name.startswith("-") and name not in ("help",):
                        if name not in subcommands:
                            subcommands.append(name)
                        if desc:
                            descriptions[name] = desc

        return subcommands, descriptions
