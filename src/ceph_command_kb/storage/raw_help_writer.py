"""Raw help text writer — stores original help output verbatim."""

from __future__ import annotations

import logging
from pathlib import Path

from ceph_command_kb.models import KnowledgeBase

logger = logging.getLogger(__name__)


class RawHelpWriter:
    """Stores the raw help text for each command.

    This ensures the original output is always available even if
    the parser misses something. Useful for re-parsing with improved
    parsers without re-running discovery.
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir / "raw_help"

    def write(self, kb: KnowledgeBase) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)

        for cmd in sorted(kb.commands.values(), key=lambda c: c.name):
            filename = cmd.name.replace(" ", "-") + ".txt"
            path = self._output_dir / filename
            path.write_text(cmd.raw_help, encoding="utf-8")

        logger.info("Wrote %d raw help files to %s", len(kb.commands), self._output_dir)
