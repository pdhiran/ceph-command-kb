"""Recursive command discovery engine.

Orchestrates the discovery of all commands for configured binaries
by recursively exploring subcommands through help output.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from ceph_command_kb import __version__
from ceph_command_kb.config import BinaryConfig, Config
from ceph_command_kb.discovery.cache import DiscoveryCache
from ceph_command_kb.discovery.executor import Executor
from ceph_command_kb.models import Command, KnowledgeBase, extract_keywords
from ceph_command_kb.parsing.registry import ParserRegistry
from ceph_command_kb.version import detect_binary_version, detect_ceph_version

logger = logging.getLogger(__name__)

NOT_A_SUBCOMMAND_PATTERNS = [
    re.compile(r"unrecognized\s+command", re.IGNORECASE),
    re.compile(r"unknown\s+command", re.IGNORECASE),
    re.compile(r"invalid\s+command", re.IGNORECASE),
    re.compile(r"no\s+such\s+command", re.IGNORECASE),
    re.compile(r"error:", re.IGNORECASE),
    re.compile(r"not\s+a\s+valid", re.IGNORECASE),
]


class DiscoveryEngine:
    """Discovers all commands for configured binaries.

    For each binary:
    1. Verifies the binary exists on PATH
    2. Runs `<binary> -h` and parses the output
    3. Extracts subcommand candidates from the parsed output
    4. Validates each candidate by running `<binary> <candidate> -h`
    5. Recurses into valid subcommands
    6. Collects all discovered Command objects

    Safety: Only help commands are ever executed (enforced by Executor).
    """

    def __init__(
        self,
        config: Config,
        executor: Executor | None = None,
        registry: ParserRegistry | None = None,
        cache: DiscoveryCache | None = None,
    ) -> None:
        self._config = config
        self._executor = executor or Executor(timeout=config.command_timeout)
        self._registry = registry or ParserRegistry()
        self._cache = cache or DiscoveryCache()
        self._commands: dict[str, Command] = {}

        HELP_PREFIX_BINARIES = {"rbd", "rados"}

        for bc in config.binaries:
            if bc.parser:
                self._registry.register_by_name(bc.name, bc.parser)
            if bc.name in HELP_PREFIX_BINARIES and not bc.help_prefix_mode:
                bc.help_prefix_mode = True

    def discover_all(self) -> KnowledgeBase:
        """Discover commands for all configured binaries.

        Returns a fully populated KnowledgeBase.
        """
        logger.info("Starting discovery for %d binaries", len(self._config.binaries))

        version = None
        try:
            version = detect_ceph_version(timeout=self._config.command_timeout)
        except (FileNotFoundError, RuntimeError) as e:
            logger.warning("Could not detect Ceph version: %s", e)

        binary_versions: dict[str, str] = {}
        discovered_binaries: list[str] = []

        with ThreadPoolExecutor(max_workers=self._config.workers) as pool:
            futures = {}
            for bc in self._config.binaries:
                if not self._executor.binary_exists(bc.name):
                    logger.warning("Binary not found, skipping: %s", bc.name)
                    continue

                bv = detect_binary_version(bc.name, timeout=self._config.command_timeout)
                if bv:
                    binary_versions[bc.name] = bv

                discovered_binaries.append(bc.name)
                future = pool.submit(self._discover_binary, bc)
                futures[future] = bc.name

            for future in as_completed(futures):
                binary = futures[future]
                try:
                    commands = future.result()
                    for cmd in commands:
                        self._commands[cmd.name] = cmd
                    logger.info(
                        "Discovered %d commands for %s",
                        len(commands),
                        binary,
                    )
                except Exception:
                    logger.exception("Discovery failed for %s", binary)

        self._cache.save()

        if version is None:
            from ceph_command_kb.models import CephVersion
            version = CephVersion(
                major=0, minor=0, patch=0,
                release_name="unknown",
                full_string="unknown",
            )

        kb = KnowledgeBase(
            version=version,
            commands=dict(self._commands),
            generated_at=datetime.now(timezone.utc).isoformat(),
            generator_version=__version__,
            binaries_discovered=discovered_binaries,
            binary_versions=binary_versions,
        )

        logger.info(
            "Discovery complete: %d commands from %d binaries",
            kb.total_commands,
            kb.total_binaries,
        )
        return kb

    def _discover_binary(self, bc: BinaryConfig) -> list[Command]:
        """Discover all commands for a single binary."""
        logger.info("Discovering commands for: %s", bc.name)
        parts = [bc.name]
        return self._discover_recursive(parts, bc, depth=0, parent_output=None)

    def _discover_recursive(
        self,
        parts: list[str],
        bc: BinaryConfig,
        depth: int,
        parent_output: str | None,
    ) -> list[Command]:
        command_name = " ".join(parts)

        if self._cache.is_visited(command_name):
            return []

        if depth > bc.max_depth:
            logger.debug("Max depth reached for %s", command_name)
            return []

        self._cache.mark_visited(command_name)

        help_output = self._try_help(parts, bc.help_flags)
        if help_output is None:
            self._cache.mark_failed(command_name, "all help flags failed")
            return []

        if parent_output and self._is_same_output(help_output, parent_output):
            if bc.help_prefix_mode and len(parts) > 1:
                prefix_output = self._try_help_prefix(parts[0], parts[1:])
                if prefix_output and not self._is_same_output(prefix_output, parent_output):
                    help_output = prefix_output
                else:
                    logger.debug("Output identical to parent, not a real subcommand: %s", command_name)
                    return []
            else:
                logger.debug("Output identical to parent, not a real subcommand: %s", command_name)
                return []

        if self._looks_like_error(help_output):
            logger.debug("Output looks like an error, skipping: %s", command_name)
            self._cache.mark_failed(command_name, "error in output")
            return []

        parser = self._registry.get_parser_for_output(bc.name, help_output)
        parse_result = parser.parse(help_output, command_parts=parts)

        discovery_path = " -> ".join(
            " ".join(parts[:i + 1]) for i in range(len(parts))
        )

        cmd = Command(
            name=command_name,
            binary=bc.name,
            parts=list(parts),
            description=parse_result.description,
            usage=parse_result.usage,
            synopsis=parse_result.synopsis,
            arguments=parse_result.arguments,
            flags=parse_result.flags,
            subcommands=[],
            aliases=parse_result.aliases,
            examples=parse_result.examples,
            notes=parse_result.notes,
            raw_help=help_output,
            discovery_path=discovery_path,
            keywords=self._extract_keywords(command_name, parse_result.description),
        )

        commands = [cmd]

        candidates = parse_result.subcommand_names
        if bc.explicit_subcommands is not None and depth == 0:
            candidates = bc.explicit_subcommands

        valid_subcommands: list[str] = []
        for sub in candidates:
            if sub in bc.ignore_subcommands:
                continue
            sub_parts = list(parts) + [sub]
            sub_commands = self._discover_recursive(
                sub_parts, bc, depth + 1, help_output
            )
            if sub_commands:
                valid_subcommands.append(sub)
                commands.extend(sub_commands)
            else:
                stub = self._make_stub_command(
                    sub, parts, bc, parse_result, help_output
                )
                if stub:
                    valid_subcommands.append(sub)
                    commands.append(stub)

        cmd.subcommands = valid_subcommands

        self._create_multiword_stubs(
            commands, parts, bc, parse_result, valid_subcommands
        )

        if depth % 5 == 0:
            self._cache.save()

        return commands

    @staticmethod
    def _make_stub_command(
        sub_name: str,
        parent_parts: list[str],
        bc: BinaryConfig,
        parse_result: "ParseResult",
        parent_help: str,
    ) -> Command | None:
        """Create a minimal Command entry from the parent's parsed info.

        Used when a subcommand is listed in the parent's help but has no
        dedicated help page (e.g., rados subcommands).
        """
        sub_desc = ""
        for full_name, desc in parse_result.subcommand_descriptions.items():
            words = full_name.split()
            if words and words[0] == sub_name:
                sub_desc = desc
                break

        if not sub_desc:
            return None

        full_parts = list(parent_parts) + [sub_name]
        full_name = " ".join(full_parts)

        return Command(
            name=full_name,
            binary=bc.name,
            parts=full_parts,
            description=sub_desc,
            raw_help=f"(Extracted from parent help: {' '.join(parent_parts)})",
            discovery_path=" -> ".join(
                " ".join(full_parts[:i + 1]) for i in range(len(full_parts))
            ),
            keywords=DiscoveryEngine._extract_keywords(full_name, sub_desc),
        )

    def _create_multiword_stubs(
        self,
        commands: list[Command],
        parent_parts: list[str],
        bc: BinaryConfig,
        parse_result: "ParseResult",
        already_discovered: list[str],
    ) -> None:
        """Create stub entries for multi-word commands listed in the parent help.

        For tools like rbd where the help lists 'mirror image demote',
        'mirror pool enable', etc., this creates entries for each full
        command name that wasn't already discovered via recursion.
        """
        discovered_names = {cmd.name for cmd in commands}

        for full_name, desc in parse_result.subcommand_descriptions.items():
            words = full_name.split()
            if len(words) <= 1:
                continue

            cmd_name = " ".join(parent_parts + words)
            if cmd_name in discovered_names or self._cache.is_visited(cmd_name):
                continue

            self._cache.mark_visited(cmd_name)
            cmd_parts = parent_parts + words

            stub = Command(
                name=cmd_name,
                binary=bc.name,
                parts=cmd_parts,
                description=desc,
                raw_help=f"(Extracted from parent help: {' '.join(parent_parts)})",
                discovery_path=" -> ".join(
                    " ".join(cmd_parts[:i + 1]) for i in range(len(cmd_parts))
                ),
                keywords=self._extract_keywords(cmd_name, desc),
            )
            commands.append(stub)
            discovered_names.add(cmd_name)

    def _try_help(self, parts: list[str], help_flags: list[str]) -> str | None:
        """Try each help flag until one produces output."""
        for flag in help_flags:
            try:
                result = self._executor.run_help(parts, help_flag=flag)
                output = result.output.strip()
                if output:
                    return output
            except Exception as e:
                logger.debug(
                    "Help flag %s failed for %s: %s",
                    flag, " ".join(parts), e,
                )
        return None

    def _try_help_prefix(self, binary: str, subcommand_parts: list[str]) -> str | None:
        """Try `<binary> help <subcommand>` format (used by rbd, rados)."""
        try:
            result = self._executor.run_help_prefix(binary, subcommand_parts)
            output = result.output.strip()
            if output and result.success:
                return output
        except Exception as e:
            logger.debug(
                "Prefix help failed for %s help %s: %s",
                binary, " ".join(subcommand_parts), e,
            )
        return None

    @staticmethod
    def _is_same_output(output: str, parent_output: str) -> bool:
        """Check if two help outputs are effectively identical."""
        return output.strip() == parent_output.strip()

    @staticmethod
    def _looks_like_error(output: str) -> bool:
        """Check if the output contains error indicators."""
        for pattern in NOT_A_SUBCOMMAND_PATTERNS:
            if pattern.search(output):
                return True
        return False

    @staticmethod
    def _extract_keywords(command_name: str, description: str) -> list[str]:
        return extract_keywords(command_name, description)
