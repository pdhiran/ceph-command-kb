"""Parser registry — maps binaries to their appropriate parser."""

from __future__ import annotations

import logging
from typing import Type

from ceph_command_kb.parsing.argparse_parser import ArgparseParser
from ceph_command_kb.parsing.base import BaseParser
from ceph_command_kb.parsing.boost_parser import BoostParser
from ceph_command_kb.parsing.ceph_parser import CephParser
from ceph_command_kb.parsing.generic_parser import GenericParser

logger = logging.getLogger(__name__)

DEFAULT_BINARY_PARSERS: dict[str, Type[BaseParser]] = {
    "ceph": CephParser,
    "rbd": BoostParser,
    "rados": BoostParser,
    "cephadm": ArgparseParser,
    "ceph-volume": ArgparseParser,
    "cephfs-shell": ArgparseParser,
    "ceph-authtool": GenericParser,
    "ceph-bluestore-tool": GenericParser,
    "ceph-objectstore-tool": GenericParser,
    "crushtool": GenericParser,
    "monmaptool": GenericParser,
    "osdmaptool": GenericParser,
}


class ParserRegistry:
    """Maps binary names to parser instances.

    Supports explicit registration, config overrides, and auto-detection
    as a fallback.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}
        self._auto_detect_chain: list[BaseParser] = [
            BoostParser(),
            ArgparseParser(),
            CephParser(),
        ]
        self._fallback = GenericParser()

        for binary, parser_cls in DEFAULT_BINARY_PARSERS.items():
            self._parsers[binary] = parser_cls()

    def register(self, binary: str, parser: BaseParser) -> None:
        self._parsers[binary] = parser

    def register_by_name(self, binary: str, parser_name: str) -> None:
        """Register a parser by its class name (for config-driven registration)."""
        name_map: dict[str, Type[BaseParser]] = {
            "ceph": CephParser,
            "argparse": ArgparseParser,
            "boost": BoostParser,
            "generic": GenericParser,
        }
        parser_cls = name_map.get(parser_name.lower())
        if parser_cls is None:
            logger.warning(
                "Unknown parser name %r for binary %r, using generic",
                parser_name,
                binary,
            )
            parser_cls = GenericParser
        self._parsers[binary] = parser_cls()

    def get_parser(self, binary: str) -> BaseParser:
        """Get the parser for a binary.

        Priority:
        1. Explicitly registered parser for this binary
        2. Auto-detection fallback
        """
        if binary in self._parsers:
            return self._parsers[binary]

        logger.debug("No explicit parser for %r, will use auto-detection at parse time", binary)
        return self._fallback

    def get_parser_for_output(self, binary: str, raw_help: str) -> BaseParser:
        """Get the best parser for a given help output, with auto-detection.

        Tries the registered parser first, then falls back to auto-detection
        based on the output content.
        """
        if binary in self._parsers:
            return self._parsers[binary]

        for parser in self._auto_detect_chain:
            if parser.can_parse(raw_help):
                logger.debug("Auto-detected %s for binary %r", type(parser).__name__, binary)
                return parser

        logger.debug("No parser matched for %r, using GenericParser", binary)
        return self._fallback
