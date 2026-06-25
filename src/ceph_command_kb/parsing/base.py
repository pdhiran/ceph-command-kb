"""Abstract base parser interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ceph_command_kb.models import ParseResult


class BaseParser(ABC):
    """Base class for help output parsers.

    Each parser is responsible for extracting structured data from a
    specific help output format. Parsers should extract what they can
    and leave unrecognized fields as empty/None — partial parsing is
    always preferred over failing entirely.
    """

    @abstractmethod
    def parse(self, raw_help: str, command_parts: list[str] | None = None) -> ParseResult:
        """Parse raw help output into structured data.

        Args:
            raw_help: The raw text output from running a help command.
            command_parts: The command components, e.g. ["ceph", "osd", "pool"].
                Used by some parsers to contextualize the output.

        Returns:
            ParseResult with whatever fields could be extracted.
        """

    @abstractmethod
    def can_parse(self, raw_help: str) -> bool:
        """Heuristic check: can this parser handle the given output?

        Used by the registry for auto-detection when no explicit parser
        is configured for a binary.
        """
