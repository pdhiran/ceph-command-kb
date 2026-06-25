"""Configuration loading and validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_BINARIES = [
    "ceph",
    "rados",
    "rbd",
    "cephadm",
    "ceph-volume",
    "ceph-authtool",
    "ceph-bluestore-tool",
    "ceph-objectstore-tool",
    "cephfs-shell",
    "crushtool",
    "monmaptool",
    "osdmaptool",
]

DEFAULT_HELP_FLAGS = ["-h", "--help", "help"]


@dataclass
class BinaryConfig:
    name: str
    help_flags: list[str] = field(default_factory=lambda: list(DEFAULT_HELP_FLAGS))
    ignore_subcommands: list[str] = field(default_factory=list)
    explicit_subcommands: list[str] | None = None
    parser: str | None = None
    max_depth: int = 10
    help_prefix_mode: bool = False


@dataclass
class Config:
    binaries: list[BinaryConfig] = field(default_factory=list)
    output_dir: str = "knowledge"
    version_label: str | None = None
    log_level: str = "INFO"
    log_file: str | None = None
    workers: int = 4
    command_timeout: int = 10
    resume: bool = False
    force: bool = False
    cache_dir: str = ".cache"

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        if path is not None and path.exists():
            logger.info("Loading config from %s", path)
            with open(path) as f:
                raw = yaml.safe_load(f) or {}
            return cls._from_raw(raw)

        logger.info("No config file provided or found, using defaults")
        return cls._defaults()

    @classmethod
    def _defaults(cls) -> Config:
        return cls(
            binaries=[BinaryConfig(name=b) for b in DEFAULT_BINARIES],
        )

    @classmethod
    def _from_raw(cls, raw: dict[str, Any]) -> Config:
        binaries_raw = raw.get("binaries", DEFAULT_BINARIES)
        binaries = []
        for entry in binaries_raw:
            if isinstance(entry, str):
                binaries.append(BinaryConfig(name=entry))
            elif isinstance(entry, dict):
                binaries.append(BinaryConfig(
                    name=entry["name"],
                    help_flags=entry.get("help_flags", list(DEFAULT_HELP_FLAGS)),
                    ignore_subcommands=entry.get("ignore_subcommands", []),
                    explicit_subcommands=entry.get("explicit_subcommands"),
                    parser=entry.get("parser"),
                    max_depth=entry.get("max_depth", 10),
                    help_prefix_mode=entry.get("help_prefix_mode", False),
                ))

        return cls(
            binaries=binaries,
            output_dir=raw.get("output_dir", "knowledge"),
            version_label=raw.get("version_label"),
            log_level=raw.get("log_level", "INFO"),
            log_file=raw.get("log_file"),
            workers=raw.get("workers", 4),
            command_timeout=raw.get("command_timeout", 10),
            resume=raw.get("resume", False),
            force=raw.get("force", False),
            cache_dir=raw.get("cache_dir", ".cache"),
        )

    def merge_cli_args(
        self,
        *,
        output: str | None = None,
        workers: int | None = None,
        resume: bool | None = None,
        force: bool | None = None,
        verbose: bool = False,
        log_level: str | None = None,
    ) -> None:
        """Overlay CLI arguments onto the loaded config. CLI args take precedence."""
        if output is not None:
            self.output_dir = output
        if workers is not None:
            self.workers = workers
        if resume is not None:
            self.resume = resume
        if force is not None:
            self.force = force
        if verbose:
            self.log_level = "DEBUG"
        elif log_level is not None:
            self.log_level = log_level
