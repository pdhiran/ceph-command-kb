"""Search index generator for semantic command lookup."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ceph_command_kb.models import KnowledgeBase

logger = logging.getLogger(__name__)


class SearchIndexWriter:
    """Generates a search index optimized for command lookup.

    The index supports searching by:
    - Command name (exact and partial)
    - Binary name
    - Flag (short or long form)
    - Argument name
    - Keyword (from description)
    - Subcommand
    - Alias
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def write(self, kb: KnowledgeBase) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        index = self._build_index(kb)

        path = self._output_dir / "search_index.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
            f.write("\n")

        total_entries = sum(len(v) for v in index.get("by_keyword", {}).values())
        logger.info(
            "Wrote search index to %s (%d commands, %d keyword entries)",
            path,
            len(index.get("by_command", {})),
            total_entries,
        )

    def _build_index(self, kb: KnowledgeBase) -> dict:
        by_command: dict[str, dict] = {}
        by_binary: dict[str, list[str]] = {}
        by_flag: dict[str, list[str]] = {}
        by_argument: dict[str, list[str]] = {}
        by_keyword: dict[str, list[str]] = {}

        for cmd in kb.commands.values():
            entry = {
                "binary": cmd.binary,
                "description": cmd.description,
                "has_subcommands": bool(cmd.subcommands),
                "flag_count": len(cmd.flags),
                "argument_count": len(cmd.arguments),
                "markdown_file": cmd.name.replace(" ", "-") + ".md",
            }
            by_command[cmd.name] = entry

            by_binary.setdefault(cmd.binary, []).append(cmd.name)

            for flag in cmd.flags:
                if flag.short_form:
                    by_flag.setdefault(flag.short_form, []).append(cmd.name)
                if flag.long_form:
                    by_flag.setdefault(flag.long_form, []).append(cmd.name)

            for arg in cmd.arguments:
                by_argument.setdefault(arg.name, []).append(cmd.name)

            for kw in cmd.keywords:
                by_keyword.setdefault(kw, []).append(cmd.name)

            for alias in cmd.aliases:
                by_command[alias] = entry

        for key in by_binary:
            by_binary[key] = sorted(set(by_binary[key]))
        for key in by_flag:
            by_flag[key] = sorted(set(by_flag[key]))
        for key in by_argument:
            by_argument[key] = sorted(set(by_argument[key]))
        for key in by_keyword:
            by_keyword[key] = sorted(set(by_keyword[key]))

        return {
            "version": kb.version.to_dict(),
            "by_command": dict(sorted(by_command.items())),
            "by_binary": dict(sorted(by_binary.items())),
            "by_flag": dict(sorted(by_flag.items())),
            "by_argument": dict(sorted(by_argument.items())),
            "by_keyword": dict(sorted(by_keyword.items())),
        }
