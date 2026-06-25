#!/usr/bin/env python3
"""Ceph Command Knowledge Base Generator.

Discovers, parses, and documents every available Ceph CLI command.
Generates structured JSON, Markdown documentation, and a search index.

Usage:
    python generate_reference.py
    python generate_reference.py --resume
    python generate_reference.py --force
    python generate_reference.py --verbose
    python generate_reference.py --workers 8
    python generate_reference.py --output knowledge
    python generate_reference.py --config config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ceph_command_kb.config import Config
from ceph_command_kb.discovery.cache import DiscoveryCache
from ceph_command_kb.discovery.engine import DiscoveryEngine
from ceph_command_kb.log import setup_logging
from ceph_command_kb.storage.json_writer import JsonWriter
from ceph_command_kb.storage.markdown_writer import MarkdownWriter
from ceph_command_kb.storage.raw_help_writer import RawHelpWriter
from ceph_command_kb.storage.search_index import SearchIndexWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a comprehensive Ceph CLI command knowledge base.",
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory (default: knowledge)",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parallel discovery workers (default: 4)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=None,
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=None,
        help="Force regeneration, ignore cache",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        default=False,
        help="Re-parse from stored raw help (skip discovery)",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        default=False,
        help="Also generate Markdown docs and raw help text files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config = Config.load(args.config)
    config.merge_cli_args(
        output=args.output,
        workers=args.workers,
        resume=args.resume,
        force=args.force,
        verbose=args.verbose,
    )

    logger = setup_logging(
        level=config.log_level,
        log_file="generation.log",
        log_dir=Path(config.output_dir),
    )

    logger.info("=== Ceph Command Knowledge Base Generator ===")
    logger.info("Output directory: %s", config.output_dir)

    if args.reparse:
        logger.info("Re-parse mode: regenerating from stored raw help")
        return _reparse(config)

    cache_dir = Path(config.cache_dir)
    if config.force:
        cache = DiscoveryCache()
        logger.info("Force mode: ignoring cache")
    elif config.resume:
        cache = DiscoveryCache.load(cache_dir)
        logger.info("Resume mode: continuing from checkpoint")
    else:
        cache = DiscoveryCache()

    engine = DiscoveryEngine(config=config, cache=cache)

    try:
        kb = engine.discover_all()
    except KeyboardInterrupt:
        logger.warning("Interrupted — saving cache for resume")
        cache.save()
        return 130

    if kb.total_commands == 0:
        logger.error("No commands discovered. Are Ceph binaries on PATH?")
        return 1

    version_dir = Path(config.output_dir) / kb.version.label()
    logger.info("Writing output to %s", version_dir)

    JsonWriter(version_dir).write(kb)
    SearchIndexWriter(version_dir).write(kb)

    if args.docs:
        MarkdownWriter(version_dir).write(kb)
        RawHelpWriter(version_dir).write(kb)

    logger.info("=== Generation complete ===")
    logger.info("  Commands:  %d", kb.total_commands)
    logger.info("  Binaries:  %d", kb.total_binaries)
    logger.info("  Output:    %s", version_dir)

    return 0


def _reparse(config: Config) -> int:
    """Re-parse from stored raw help files without running discovery.

    Loads raw_help/*.txt, runs them through parsers, and regenerates
    JSON/Markdown/search index.
    """
    import json
    from ceph_command_kb.models import CephVersion, Command, KnowledgeBase
    from ceph_command_kb.parsing.registry import ParserRegistry
    from datetime import datetime, timezone
    from ceph_command_kb import __version__

    logger = setup_logging(level=config.log_level)

    output_path = Path(config.output_dir)
    version_dirs = sorted(output_path.iterdir()) if output_path.exists() else []

    if not version_dirs:
        logger.error("No existing knowledge base found in %s", output_path)
        return 1

    version_dir = version_dirs[-1]
    logger.info("Re-parsing from %s", version_dir)

    metadata_path = version_dir / "metadata.json"
    if not metadata_path.exists():
        logger.error("No metadata.json found in %s", version_dir)
        return 1

    with open(metadata_path) as f:
        metadata = json.load(f)

    version = CephVersion.from_dict(metadata["version"])
    registry = ParserRegistry()
    commands: dict[str, Command] = {}

    raw_help_dir = version_dir / "raw_help"
    if not raw_help_dir.exists():
        logger.error("No raw_help directory found in %s", version_dir)
        return 1

    for txt_file in sorted(raw_help_dir.glob("*.txt")):
        raw_help = txt_file.read_text(encoding="utf-8")
        command_name = txt_file.stem.replace("-", " ")
        parts = command_name.split()
        binary = parts[0]

        parser = registry.get_parser_for_output(binary, raw_help)
        result = parser.parse(raw_help, command_parts=parts)

        cmd = Command(
            name=command_name,
            binary=binary,
            parts=parts,
            description=result.description,
            usage=result.usage,
            synopsis=result.synopsis,
            arguments=result.arguments,
            flags=result.flags,
            subcommands=[],
            aliases=result.aliases,
            examples=result.examples,
            notes=result.notes,
            raw_help=raw_help,
        )
        commands[command_name] = cmd

    kb = KnowledgeBase(
        version=version,
        commands=commands,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generator_version=__version__,
        binaries_discovered=metadata.get("binaries_discovered", []),
        binary_versions=metadata.get("binary_versions", {}),
    )

    JsonWriter(version_dir).write(kb)
    MarkdownWriter(version_dir).write(kb)
    SearchIndexWriter(version_dir).write(kb)

    logger.info("Re-parse complete: %d commands", kb.total_commands)
    return 0


if __name__ == "__main__":
    sys.exit(main())
