"""Markdown documentation writer — one file per command."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from ceph_command_kb.models import Command, KnowledgeBase

logger = logging.getLogger(__name__)


class MarkdownWriter:
    """Generates Markdown documentation files for each command."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir / "markdown"

    def write(self, kb: KnowledgeBase) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        for cmd in sorted(kb.commands.values(), key=lambda c: c.name):
            self._write_command(cmd, kb)

        logger.info("Wrote %d markdown files to %s", len(kb.commands), self._output_dir)

    def _write_command(self, cmd: Command, kb: KnowledgeBase) -> None:
        filename = cmd.name.replace(" ", "-") + ".md"
        path = self._output_dir / filename

        lines: list[str] = []
        lines.append(f"# {cmd.name}")
        lines.append("")

        if cmd.description:
            lines.append(cmd.description)
            lines.append("")

        lines.append("## Metadata")
        lines.append("")
        lines.append(f"- **Binary:** `{cmd.binary}`")
        lines.append(f"- **Ceph Version:** {kb.version.full_string}")
        lines.append(f"- **Generated:** {kb.generated_at}")
        if cmd.discovery_path:
            lines.append(f"- **Discovery Path:** {cmd.discovery_path}")
        if cmd.deprecated:
            lines.append("- **Status:** DEPRECATED")
        lines.append("")

        if cmd.usage:
            lines.append("## Usage")
            lines.append("")
            lines.append(f"```")
            lines.append(cmd.usage)
            lines.append("```")
            lines.append("")

        if cmd.synopsis:
            lines.append("## Synopsis")
            lines.append("")
            lines.append(cmd.synopsis)
            lines.append("")

        if cmd.arguments:
            lines.append("## Arguments")
            lines.append("")
            lines.append("| Name | Type | Required | Default | Description |")
            lines.append("|------|------|----------|---------|-------------|")
            for arg in cmd.arguments:
                required = "Yes" if arg.required else "No"
                vtype = arg.value_type or "-"
                default = arg.default or "-"
                desc = arg.description or "-"
                lines.append(f"| `{arg.name}` | {vtype} | {required} | {default} | {desc} |")
            lines.append("")

        if cmd.flags:
            lines.append("## Flags")
            lines.append("")
            lines.append("| Short | Long | Takes Value | Default | Description |")
            lines.append("|-------|------|-------------|---------|-------------|")
            for flag in cmd.flags:
                short = f"`{flag.short_form}`" if flag.short_form else "-"
                long = f"`{flag.long_form}`" if flag.long_form else "-"
                takes = "Yes" if flag.takes_value else "No"
                default = flag.default or "-"
                desc = flag.description or "-"
                lines.append(f"| {short} | {long} | {takes} | {default} | {desc} |")
            lines.append("")

        if cmd.subcommands:
            lines.append("## Subcommands")
            lines.append("")
            for sub in sorted(cmd.subcommands):
                full_sub = f"{cmd.name} {sub}"
                link = full_sub.replace(" ", "-") + ".md"
                lines.append(f"- [{full_sub}]({link})")
            lines.append("")

        if cmd.aliases:
            lines.append("## Aliases")
            lines.append("")
            for alias in cmd.aliases:
                lines.append(f"- `{alias}`")
            lines.append("")

        if cmd.examples:
            lines.append("## Examples")
            lines.append("")
            for example in cmd.examples:
                lines.append(f"```bash")
                lines.append(example)
                lines.append("```")
                lines.append("")

        if cmd.notes:
            lines.append("## Notes")
            lines.append("")
            lines.append(cmd.notes)
            lines.append("")

        lines.append("## Raw Help Output")
        lines.append("")
        lines.append("```")
        lines.append(cmd.raw_help)
        lines.append("```")
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
