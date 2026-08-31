"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def ceph_help_text() -> str:
    return (FIXTURES_DIR / "ceph_h.txt").read_text()


@pytest.fixture
def rbd_help_text() -> str:
    return (FIXTURES_DIR / "rbd_h.txt").read_text()


@pytest.fixture
def cephadm_help_text() -> str:
    return (FIXTURES_DIR / "cephadm_h.txt").read_text()


def write_mini_kb(dest: Path, *, major: int, minor: int, patch: int,
                  release: str, extra_command: str | None = None) -> None:
    from ceph_command_kb.models import CephVersion, Command, KnowledgeBase
    from ceph_command_kb.storage.json_writer import JsonWriter

    kb = KnowledgeBase(
        version=CephVersion(major, minor, patch, release, f"ceph version {major}.{minor}.{patch} {release}"),
        generated_at="2026-08-01T00:00:00Z",
        generator_version="0.1.0",
        binaries_discovered=["ceph"],
        binary_versions={"ceph": f"{major}.{minor}.{patch}"},
    )
    kb.commands["ceph osd ls"] = Command(
        name="ceph osd ls",
        binary="ceph",
        parts=["ceph", "osd", "ls"],
        description="list osds",
        keywords=["ceph", "osd", "ls"],
    )
    if extra_command:
        kb.commands[extra_command] = Command(
            name=extra_command,
            binary="ceph",
            parts=extra_command.split(),
            description="extra",
            keywords=extra_command.split(),
        )
    JsonWriter(dest).write(kb)
