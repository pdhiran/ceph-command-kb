"""Discovery cache for resume support and duplicate detection."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryCache:
    """Tracks discovered commands for resume and deduplication.

    State is persisted to disk so interrupted runs can continue
    from the last checkpoint. All operations are thread-safe.
    """

    visited: set[str] = field(default_factory=set)
    failed: dict[str, str] = field(default_factory=dict)
    _cache_path: Path | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

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
        with self._lock:
            state = {
                "visited": sorted(self.visited),
                "failed": dict(self.failed),
            }
        fd, tmp = tempfile.mkstemp(dir=self._cache_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self._cache_path)
        except BaseException:
            os.unlink(tmp)
            raise

        logger.debug("Cache saved: %d visited, %d failed", len(state["visited"]), len(state["failed"]))

    def is_visited(self, command: str) -> bool:
        with self._lock:
            return command in self.visited

    def mark_visited(self, command: str) -> None:
        with self._lock:
            self.visited.add(command)

    def mark_failed(self, command: str, reason: str) -> None:
        with self._lock:
            self.failed[command] = reason

    def clear(self) -> None:
        with self._lock:
            self.visited.clear()
            self.failed.clear()
        if self._cache_path and self._cache_path.exists():
            self._cache_path.unlink()
