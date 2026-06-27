"""Parser for the native `ceph` command help format.

The `ceph` CLI has its own distinctive help output format that differs from
both argparse and boost::program_options. This parser handles:
- `ceph -h` (lists all commands or command groups)
- `ceph <prefix> -h` (lists commands under a prefix)
- `ceph help <command>` (detailed help for a specific command)
"""

from __future__ import annotations

import logging
import re

from ceph_command_kb.models import Argument, ArgumentType, Flag, ParseResult
from ceph_command_kb.parsing.base import BaseParser

logger = logging.getLogger(__name__)

CEPH_COMMAND_LINE = re.compile(
    r"^\s*([\w-]+(?:\s+[\w-]+)*)"
    r"(?:\s+(.+))?"
    r"\s*$",
)

CEPH_FLAG = re.compile(
    r"<([\w-]+)(?::([\w-]+))?>",
)

CEPH_NOISE_WORDS = frozenset({
    "general", "usage", "commands", "options", "synopsis", "description",
    "monitor", "tell", "see", "the", "for", "more", "information", "note",
    "warning", "error", "example", "examples", "deprecated", "global",
})


class CephParser(BaseParser):
    """Parser for the native ceph CLI help format.

    The `ceph` command has a distinctive help format where:
    - Top-level help lists command prefixes or full commands
    - Each command line shows the command followed by argument placeholders
    - Arguments are in angle brackets: <pool>, <pool:int>
    - Optional arguments are in square brackets: [<start>]
    """

    def parse(self, raw_help: str, command_parts: list[str] | None = None) -> ParseResult:
        result = ParseResult()

        result.usage = self._extract_usage(raw_help)
        result.description = self._extract_description(raw_help, command_parts)
        result.flags = self._extract_flags(raw_help, command_parts)
        result.subcommand_names = self._extract_subcommands(raw_help, command_parts)
        result.arguments = self._extract_arguments(raw_help, command_parts)

        return result

    def can_parse(self, raw_help: str) -> bool:
        lower = raw_help.lower()
        return (
            "ceph" in lower
            and ("<" in raw_help or "usage:" in lower)
            and "-h [ --help ]" not in raw_help
        )

    def _extract_usage(self, text: str) -> str | None:
        match = re.search(r"^usage:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_description(self, text: str, command_parts: list[str] | None) -> str:
        if command_parts and len(command_parts) > 1:
            return self._extract_command_description(text, command_parts)

        lines = text.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped and stripped.lower().startswith("ceph administration"):
                return stripped
        return ""

    def _extract_command_description(self, text: str, command_parts: list[str]) -> str:
        """Extract description from the Monitor commands section.

        In `ceph <subcmd> -h` output, the command's description appears as:
            subcmd <args>...     description text
        in the Monitor commands section.
        """
        subcommand = " ".join(command_parts[1:])

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("-"):
                continue

            if stripped.startswith(subcommand):
                parts = re.split(r"\s{2,}", stripped)
                if len(parts) >= 2:
                    return parts[-1].strip()

        return ""

    def _extract_flags(self, text: str, command_parts: list[str] | None = None) -> list[Flag]:
        flags: list[Flag] = []
        seen = set()

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped.startswith("-"):
                continue

            match = re.match(
                r"(-\w)(?:\s*[,|]\s*|\s+)(--[\w-]+)?\s*(.*)", stripped
            )
            if match:
                short = match.group(1)
                long = match.group(2)
                desc = match.group(3).strip() if match.group(3) else ""
                key = (short, long)
                if key not in seen:
                    seen.add(key)
                    flags.append(Flag(
                        short_form=short,
                        long_form=long,
                        description=desc,
                    ))
                continue

            match = re.match(r"(--[\w-]+)\s*(.*)", stripped)
            if match:
                long = match.group(1)
                desc = match.group(2).strip() if match.group(2) else ""
                key = (None, long)
                if key not in seen:
                    seen.add(key)
                    flags.append(Flag(
                        long_form=long,
                        description=desc,
                    ))

        self._extract_syntax_flags(text, command_parts, flags, seen)

        return flags

    def _extract_syntax_flags(
        self,
        text: str,
        command_parts: list[str] | None,
        flags: list[Flag],
        seen: set,
    ) -> None:
        """Extract flags from command syntax lines in the Monitor commands section.

        Ceph help embeds flags in the command listing:
            nfs cluster create <id> [--ingress] [--enable-rdma] [--rdma_port <int>]
        """
        if not command_parts or len(command_parts) < 2:
            return

        subcommand = " ".join(command_parts[1:])
        in_monitor = False
        syntax_lines: list[str] = []
        capturing = False

        for line in text.split("\n"):
            if "Monitor commands" in line:
                in_monitor = True
                continue
            if not in_monitor:
                continue

            stripped = line.strip()

            if stripped.startswith(subcommand) and not capturing:
                syntax_lines.append(stripped)
                capturing = True
            elif capturing:
                if stripped and (stripped.startswith("[") or stripped.startswith("mode") or stripped.startswith("--")):
                    syntax_lines.append(stripped)
                elif line.startswith(" ") and stripped and not stripped[0].isupper():
                    syntax_lines.append(stripped)
                else:
                    break

        full_syntax = " ".join(syntax_lines)
        full_syntax = re.sub(r"-\s+", "-", full_syntax)
        full_syntax = re.sub(r"\s{2,}", " ", full_syntax)

        for match in re.finditer(r"\[--([\w-]+)(?:\s+<([\w-]+)(?::[\w|]+)?>)?\]", full_syntax):
            flag_name = f"--{match.group(1)}"
            value_name = match.group(2)
            key = (None, flag_name)
            if key not in seen:
                seen.add(key)
                flags.append(Flag(
                    long_form=flag_name,
                    takes_value=value_name is not None,
                    value_name=f"<{value_name}>" if value_name else None,
                ))

    def _extract_subcommands(
        self, text: str, command_parts: list[str] | None
    ) -> list[str]:
        """Extract subcommand names from ceph help output.

        For `ceph -h`, commands are listed as full command lines like:
            osd pool create <pool> ...
            osd pool delete <pool> ...

        We extract the next token after the current prefix as subcommands.
        """
        subcommands: list[str] = []
        seen: set[str] = set()

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("-"):
                continue
            lower = stripped.lower()
            if lower.startswith("usage") or lower.startswith("general") or lower.endswith(":"):
                continue
            if lower.startswith("="):
                continue

            words = stripped.split()
            if not words:
                continue

            if command_parts and len(command_parts) > 1:
                prefix_words = command_parts[1:]
                if words[:len(prefix_words)] != prefix_words:
                    continue
                remaining = words[len(prefix_words):]
            else:
                remaining = words

            if not remaining:
                continue

            candidate = remaining[0]

            if candidate.startswith("<") or candidate.startswith("["):
                continue
            if candidate.startswith("-"):
                continue
            if not re.match(r"^[a-zA-Z][\w-]*$", candidate):
                continue
            if candidate.lower() in CEPH_NOISE_WORDS:
                continue

            if candidate not in seen:
                seen.add(candidate)
                subcommands.append(candidate)

        return subcommands

    def _extract_arguments(
        self, text: str, command_parts: list[str] | None
    ) -> list[Argument]:
        """Extract argument placeholders from ceph command syntax.

        Arguments appear as <name> or <name:type> in command lines.
        Optional arguments appear as [<name>].
        """
        args: list[Argument] = []
        seen: set[str] = set()

        required_matches = CEPH_FLAG.finditer(text)
        for match in required_matches:
            name = match.group(1)
            value_type = match.group(2)
            if name not in seen:
                seen.add(name)
                full_context = text[max(0, match.start() - 1): match.start()]
                is_optional = full_context.endswith("[")

                args.append(Argument(
                    name=name,
                    required=not is_optional,
                    arg_type=ArgumentType.POSITIONAL,
                    value_type=value_type,
                ))

        return args
