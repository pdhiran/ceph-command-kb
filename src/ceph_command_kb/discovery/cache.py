"""Discovery cache for resume support and duplicate detection."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryCache:
    """Tracks discovered commands for resume and deduplication.

    State is persisted to disk so interrupted runs can continue
    from the last checkpoint.
    """

    visited: set[str] = field(default_factory=set)
    failed: dict[str, str] = field(default_factory=dict)
    _cache_path: Path | None = None

    @classmethod
    def load(cls, cache_dir: Path) -> DiscoveryCache:
        cache_path = cache_dir / "discovery_state.json"
        cache = cls(_cache_path=cache_path)

        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    state = json.load(f)
                cache.visited = set(state.get("visited", []))
                cache.failed = state.get("failed", {})
                logger.info(
                    "Loaded cache: %d visited, %d failed",
                    len(cache.visited),
                    len(cache.failed),
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load cache, starting fresh: %s", e)

        return cache

    def save(self) -> None:
        if self._cache_path is None:
            return

        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "visited": sorted(self.visited),
            "failed": self.failed,
        }
        with open(self._cache_path, "w") as f:
            json.dump(state, f, indent=2)

        logger.debug("Cache saved: %d visited, %d failed", len(self.visited), len(self.failed))

    def is_visited(self, command: str) -> bool:
        return command in self.visited

    def mark_visited(self, command: str) -> None:
        self.visited.add(command)

    def mark_failed(self, command: str, reason: str) -> None:
        self.failed[command] = reason

    def clear(self) -> None:
        self.visited.clear()
        self.failed.clear()
        if self._cache_path and self._cache_path.exists():
            self._cache_path.unlink()
