"""Parser for boost::program_options-style help output.

Handles tools like rbd and rados that use C++ boost::program_options
for their CLI, producing a distinctive help format with sections like
"Positional arguments", "Optional arguments", and command listings.
"""

from __future__ import annotations

import re

from ceph_command_kb.models import Argument, ArgumentType, Flag, ParseResult
from ceph_command_kb.parsing.base import BaseParser

BOOST_FLAG = re.compile(
    r"^\s+"
    r"(?:(-\w)\s*\[\s*--([\w-]+)\s*\])"     # -f [ --flag ]
    r"|(?:(-\w)\s*,?\s*--([\w-]+))"          # -f, --flag  or  -f --flag
    r"|(?:--([\w-]+))"                         # --flag only
    r"|(?:(-\w))"                              # -f only
)

BOOST_FLAG_WITH_DESC = re.compile(
    r"^\s+"
    r"(-\w\s*\[\s*--[\w-]+\s*\]|"
    r"-\w\s*,?\s*--[\w-]+|"
    r"--[\w-]+|"
    r"-\w)"
    r"(?:\s+(arg|ARG|\S+))?"
    r"\s{2,}(.+)$",
)


class BoostParser(BaseParser):
    """Parser for boost::program_options-style help output."""

    def parse(self, raw_help: str, command_parts: list[str] | None = None) -> ParseResult:
        result = ParseResult()
        sections = self._split_sections(raw_help)

        result.usage = sections.get("usage")
        result.description = self._extract_description(raw_help, sections)
        result.flags = self._parse_flags(sections)
        subcommands, sub_descs = self._extract_subcommands(raw_help, sections)
        result.subcommand_names = subcommands
        result.subcommand_descriptions = sub_descs
        result.arguments = self._parse_positional_args(sections)

        return result

    def can_parse(self, raw_help: str) -> bool:
        return bool(re.search(r"-\w\s*\[\s*--\w", raw_help))

    def _split_sections(self, text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current_key: str | None = None
        current_lines: list[str] = []

        for line in text.split("\n"):
            stripped = line.strip()

            usage_match = re.match(r"^usage:\s*(.*)", stripped, re.IGNORECASE)
            if usage_match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines).rstrip()
                current_key = "usage"
                current_lines = [usage_match.group(1)]
                continue

            is_allcaps_header = (
                stripped == stripped.upper()
                and len(stripped) > 2
                and re.match(r"^[A-Z][A-Z\s&:]+$", stripped)
                and not stripped.startswith("-")
            )

            section_match = re.match(
                r"^(positional arguments|optional arguments|options|"
                r"commands?|subcommands?|pool commands|image commands|"
                r"snap commands|group commands|.*?commands?)\s*:?\s*$",
                stripped,
                re.IGNORECASE,
            )

            if not section_match and is_allcaps_header:
                section_match = re.match(r"^(.+?)(?:\s*:?\s*)$", stripped)
            if section_match:
                if current_key:
                    sections[current_key] = "\n".join(current_lines).rstrip()
                current_key = section_match.group(1).lower()
                current_lines = []
                continue

            if current_key:
                current_lines.append(line)

        if current_key:
            sections[current_key] = "\n".join(current_lines).rstrip()

        return sections

    def _extract_description(self, raw_help: str, sections: dict[str, str]) -> str:
        if "description" in sections:
            return sections["description"]

        lines = raw_help.split("\n")
        desc_lines = []
        past_usage = False

        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("usage:"):
                past_usage = True
                continue
            if past_usage and stripped and not stripped.endswith(":"):
                if not re.match(r"^-", stripped) and not re.match(r"^\s+-", line):
                    desc_lines.append(stripped)
                else:
                    break
            elif past_usage and not stripped and desc_lines:
                break

        return " ".join(desc_lines)

    def _parse_flags(self, sections: dict[str, str]) -> list[Flag]:
        flags: list[Flag] = []
        seen = set()

        for key in ("optional arguments", "options"):
            section = sections.get(key, "")
            if not section:
                continue

            for line in section.split("\n"):
                flag = self._parse_flag_line(line)
                if flag:
                    identifier = (flag.short_form, flag.long_form)
                    if identifier not in seen:
                        seen.add(identifier)
                        flags.append(flag)

        return flags

    def _parse_flag_line(self, line: str) -> Flag | None:
        stripped = line.strip()
        if not stripped or not stripped.startswith("-"):
            return None

        short = None
        long = None
        value_name = None
        description = ""

        bracket_match = re.match(
            r"(-\w)\s*\[\s*--([\w-]+)\s*\](?:\s+(arg|\S+))?\s{2,}(.+)", stripped
        )
        if bracket_match:
            short = bracket_match.group(1)
            long = f"--{bracket_match.group(2)}"
            value_name = bracket_match.group(3)
            description = bracket_match.group(4).strip()
        else:
            comma_match = re.match(
                r"(-\w)\s*,?\s*(--[\w-]+)(?:\s+(arg|\S+))?\s{2,}(.+)", stripped
            )
            if comma_match:
                short = comma_match.group(1)
                long = comma_match.group(2)
                value_name = comma_match.group(3)
                description = comma_match.group(4).strip()
            else:
                long_only = re.match(
                    r"(--[\w-]+)(?:\s+(arg|\S+))?\s{2,}(.+)", stripped
                )
                if long_only:
                    long = long_only.group(1)
                    value_name = long_only.group(2)
                    description = long_only.group(3).strip()
                else:
                    short_only = re.match(
                        r"(-\w)(?:\s+(arg|\S+))?\s{2,}(.+)", stripped
                    )
                    if short_only:
                        short = short_only.group(1)
                        value_name = short_only.group(2)
                        description = short_only.group(3).strip()

        if not short and not long:
            return None

        takes_value = value_name is not None and value_name.lower() != "arg"

        return Flag(
            short_form=short,
            long_form=long,
            description=description,
            takes_value=takes_value or (value_name and value_name.lower() == "arg"),
            value_name=value_name,
        )

    def _extract_subcommands(
        self, raw_help: str, sections: dict[str, str]
    ) -> tuple[list[str], dict[str, str]]:
        subcommands: list[str] = []
        descriptions: dict[str, str] = {}
        seen: set[str] = set()

        skip_sections = {"usage", "options", "global options", "bench options",
                         "load gen options", "cache pools options", "omap options",
                         "generic options"}

        command_sections = [
            v for k, v in sections.items()
            if k.lower() not in skip_sections
        ]

        if not command_sections:
            command_sections = [sections.get("positional arguments", "")]

        for section in command_sections:
            for line in section.split("\n"):
                if not line:
                    continue
                indent = len(line) - len(line.lstrip())
                if indent < 2 or indent > 12:
                    continue
                stripped = line.strip()
                if not stripped or stripped.startswith("-") or stripped.startswith("["):
                    continue

                parts = re.split(r"\s{2,}", stripped, maxsplit=1)
                if not parts:
                    continue

                cmd_part = parts[0]
                desc = parts[1].strip() if len(parts) > 1 else ""

                words = cmd_part.split()
                if not words:
                    continue
                first_word = words[0]

                if first_word.startswith("<") or first_word.startswith("-"):
                    continue
                if not re.match(r"^[a-zA-Z][\w-]*$", first_word):
                    continue

                full_name = " ".join(
                    w for w in words if not w.startswith("<") and not w.startswith("[") and not w.startswith("-") and not w.startswith("(") and "|" not in w
                )

                if first_word not in seen:
                    seen.add(first_word)
                    subcommands.append(first_word)

                if desc:
                    descriptions[full_name] = desc

        return subcommands, descriptions

    def _parse_positional_args(self, sections: dict[str, str]) -> list[Argument]:
        args: list[Argument] = []
        positional = sections.get("positional arguments", "")

        for line in positional.split("\n"):
            stripped = line.strip()
            angle = re.match(r"<([\w-]+)>(?:\s{2,}(.+))?", stripped)
            if angle:
                args.append(Argument(
                    name=angle.group(1),
                    description=(angle.group(2) or "").strip(),
                    required=True,
                    arg_type=ArgumentType.POSITIONAL,
                ))

        return args
