#!/usr/bin/env python3
"""Re-parse the knowledge base with updated parsers.

Reads raw_help files and commands.json, re-parses descriptions,
generates multi-word stub entries, and regenerates all output files.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ceph_command_kb import __version__
from ceph_command_kb.models import Command, CephVersion, KnowledgeBase, extract_keywords
from ceph_command_kb.parsing.registry import ParserRegistry
from ceph_command_kb.storage.json_writer import JsonWriter
from ceph_command_kb.storage.markdown_writer import MarkdownWriter
from ceph_command_kb.storage.raw_help_writer import RawHelpWriter
from ceph_command_kb.storage.search_index import SearchIndexWriter

KB_DIR = Path("knowledge/ceph-20.2.1-tentacle")


def main():
    with open(KB_DIR / "metadata.json") as f:
        metadata = json.load(f)

    with open(KB_DIR / "commands.json") as f:
        kb_data = json.load(f)

    version = CephVersion.from_dict(metadata["version"])
    registry = ParserRegistry()
    commands: dict[str, Command] = {}
    raw_help_dir = KB_DIR / "raw_help"

    print(f"Re-parsing {len(kb_data['commands'])} commands...")

    for cmd_data in kb_data["commands"]:
        name = cmd_data["name"]
        parts = name.split()
        binary = parts[0]

        raw_file = raw_help_dir / f"{name.replace(' ', '-')}.txt"
        if raw_file.exists():
            raw_help = raw_file.read_text(encoding="utf-8")
        else:
            raw_help = cmd_data.get("raw_help", "")

        if raw_help and not raw_help.startswith("(Extracted from"):
            parser = registry.get_parser_for_output(binary, raw_help)
            result = parser.parse(raw_help, command_parts=parts)

            cmd_data["description"] = result.description or cmd_data.get("description", "")
            if result.usage:
                cmd_data["usage"] = result.usage
            if result.flags:
                cmd_data["flags"] = [f.to_dict() for f in result.flags]
            if result.arguments:
                cmd_data["arguments"] = [a.to_dict() for a in result.arguments]

            # Create multi-word stub entries from subcommand_descriptions
            for full_sub, desc in result.subcommand_descriptions.items():
                sub_words = full_sub.split()
                if len(sub_words) <= 1:
                    continue
                stub_name = f"{name} {full_sub}" if name == binary else full_sub
                if binary != name:
                    stub_name = f"{binary} {full_sub}"
                else:
                    stub_name = f"{name} {full_sub}"

                if stub_name not in commands:
                    stub_parts = stub_name.split()
                    commands[stub_name] = Command(
                        name=stub_name,
                        binary=binary,
                        parts=stub_parts,
                        description=desc,
                        raw_help=f"(Extracted from parent help: {name})",
                        discovery_path=" -> ".join(
                            " ".join(stub_parts[:i+1]) for i in range(len(stub_parts))
                        ),
                        keywords=_extract_keywords(stub_name, desc),
                    )

        commands[name] = Command.from_dict(cmd_data)

    print(f"After re-parse: {len(commands)} commands (was {len(kb_data['commands'])})")

    kb = KnowledgeBase(
        version=version,
        commands=commands,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator_version=__version__,
        binaries_discovered=metadata.get("binaries_discovered", []),
        binary_versions=metadata.get("binary_versions", {}),
    )

    JsonWriter(KB_DIR).write(kb)
    MarkdownWriter(KB_DIR).write(kb)
    SearchIndexWriter(KB_DIR).write(kb)
    RawHelpWriter(KB_DIR).write(kb)

    # Print per-binary counts
    counts: dict[str, int] = {}
    for cmd in commands.values():
        counts[cmd.binary] = counts.get(cmd.binary, 0) + 1
    print("\nCommands by binary:")
    for b, c in sorted(counts.items()):
        print(f"  {b}: {c}")


def _extract_keywords(name, desc):
    return extract_keywords(name, desc or "")


if __name__ == "__main__":
    main()
