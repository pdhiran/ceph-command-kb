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
