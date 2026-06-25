"""JSON output writer for commands.json and metadata.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ceph_command_kb.models import KnowledgeBase

logger = logging.getLogger(__name__)


class JsonWriter:
    """Writes the knowledge base to structured JSON files."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def write(self, kb: KnowledgeBase) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._write_commands(kb)
        self._write_metadata(kb)

    def _write_commands(self, kb: KnowledgeBase) -> None:
        path = self._output_dir / "commands.json"
        data = {
            "version": kb.version.to_dict(),
            "total_commands": kb.total_commands,
            "commands": [cmd.to_dict() for cmd in sorted(kb.commands.values(), key=lambda c: c.name)],
        }
        self._write_json(path, data)
        logger.info("Wrote %d commands to %s", kb.total_commands, path)

    def _write_metadata(self, kb: KnowledgeBase) -> None:
        path = self._output_dir / "metadata.json"

        commands_with_desc = sum(1 for c in kb.commands.values() if c.description)
        commands_with_args = sum(1 for c in kb.commands.values() if c.arguments)
        commands_with_flags = sum(1 for c in kb.commands.values() if c.flags)
        commands_with_examples = sum(1 for c in kb.commands.values() if c.examples)
        total = kb.total_commands or 1

        data = {
            "version": kb.version.to_dict(),
            "generated_at": kb.generated_at,
            "generator_version": kb.generator_version,
            "binaries_discovered": kb.binaries_discovered,
            "binary_versions": kb.binary_versions,
            "total_commands": kb.total_commands,
            "total_binaries": kb.total_binaries,
            "commands_by_binary": self._count_by_binary(kb),
            "parse_quality": {
                "commands_with_description": commands_with_desc,
                "commands_with_arguments": commands_with_args,
                "commands_with_flags": commands_with_flags,
                "commands_with_examples": commands_with_examples,
                "description_coverage_pct": round(commands_with_desc / total * 100, 1),
                "argument_coverage_pct": round(commands_with_args / total * 100, 1),
                "flag_coverage_pct": round(commands_with_flags / total * 100, 1),
            },
        }
        self._write_json(path, data)
        logger.info("Wrote metadata to %s", path)

    @staticmethod
    def _count_by_binary(kb: KnowledgeBase) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cmd in kb.commands.values():
            counts[cmd.binary] = counts.get(cmd.binary, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
