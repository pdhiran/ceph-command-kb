"""Tests for storage writers."""

import json
from pathlib import Path

from ceph_command_kb.models import (
    Argument,
    CephVersion,
    Command,
    Flag,
    KnowledgeBase,
)
from ceph_command_kb.storage.json_writer import JsonWriter
from ceph_command_kb.storage.markdown_writer import MarkdownWriter
from ceph_command_kb.storage.raw_help_writer import RawHelpWriter
from ceph_command_kb.storage.search_index import SearchIndexWriter


def _make_kb() -> KnowledgeBase:
    version = CephVersion(19, 2, 0, "squid", "ceph version 19.2.0 squid")
    kb = KnowledgeBase(
        version=version,
        generated_at="2025-01-01T00:00:00Z",
        generator_version="0.1.0",
        binaries_discovered=["ceph"],
        binary_versions={"ceph": "19.2.0"},
    )
    kb.commands["ceph osd pool create"] = Command(
        name="ceph osd pool create",
        binary="ceph",
        parts=["ceph", "osd", "pool", "create"],
        description="create pool",
        usage="ceph osd pool create <pool> [<pg_num>]",
        arguments=[
            Argument(name="pool", required=True),
            Argument(name="pg_num", required=False),
        ],
        flags=[Flag(long_form="--size", takes_value=True)],
        subcommands=[],
        raw_help="ceph osd pool create help text here",
        keywords=["ceph", "osd", "pool", "create"],
    )
    kb.commands["ceph osd ls"] = Command(
        name="ceph osd ls",
        binary="ceph",
        parts=["ceph", "osd", "ls"],
        description="show all OSD ids",
        raw_help="ceph osd ls help text",
        keywords=["ceph", "osd", "ls"],
    )
    return kb


class TestJsonWriter:
    def test_writes_commands_json(self, tmp_path):
        kb = _make_kb()
        writer = JsonWriter(tmp_path)
        writer.write(kb)

        data = json.loads((tmp_path / "commands.json").read_text())
        assert data["total_commands"] == 2
        assert len(data["commands"]) == 2

    def test_writes_metadata_json(self, tmp_path):
        kb = _make_kb()
        writer = JsonWriter(tmp_path)
        writer.write(kb)

        data = json.loads((tmp_path / "metadata.json").read_text())
        assert data["total_commands"] == 2
        assert "parse_quality" in data
        assert data["parse_quality"]["description_coverage_pct"] == 100.0


class TestMarkdownWriter:
    def test_writes_markdown_files(self, tmp_path):
        kb = _make_kb()
        writer = MarkdownWriter(tmp_path)
        writer.write(kb)

        md_dir = tmp_path / "markdown"
        assert (md_dir / "ceph-osd-pool-create.md").exists()
        assert (md_dir / "ceph-osd-ls.md").exists()

    def test_markdown_content(self, tmp_path):
        kb = _make_kb()
        writer = MarkdownWriter(tmp_path)
        writer.write(kb)

        content = (tmp_path / "markdown" / "ceph-osd-pool-create.md").read_text()
        assert "# ceph osd pool create" in content
        assert "create pool" in content
        assert "## Arguments" in content
        assert "## Flags" in content
        assert "## Raw Help Output" in content


class TestRawHelpWriter:
    def test_writes_raw_help_files(self, tmp_path):
        kb = _make_kb()
        writer = RawHelpWriter(tmp_path)
        writer.write(kb)

        raw_dir = tmp_path / "raw_help"
        assert (raw_dir / "ceph-osd-pool-create.txt").exists()
        content = (raw_dir / "ceph-osd-pool-create.txt").read_text()
        assert "help text here" in content


class TestSearchIndexWriter:
    def test_writes_search_index(self, tmp_path):
        kb = _make_kb()
        writer = SearchIndexWriter(tmp_path)
        writer.write(kb)

        data = json.loads((tmp_path / "search_index.json").read_text())
        assert "by_command" in data
        assert "by_binary" in data
        assert "by_flag" in data
        assert "by_argument" in data
        assert "by_keyword" in data

    def test_index_by_command(self, tmp_path):
        kb = _make_kb()
        writer = SearchIndexWriter(tmp_path)
        writer.write(kb)

        data = json.loads((tmp_path / "search_index.json").read_text())
        assert "ceph osd pool create" in data["by_command"]
        assert "ceph osd ls" in data["by_command"]

    def test_index_by_flag(self, tmp_path):
        kb = _make_kb()
        writer = SearchIndexWriter(tmp_path)
        writer.write(kb)

        data = json.loads((tmp_path / "search_index.json").read_text())
        assert "--size" in data["by_flag"]
        assert "ceph osd pool create" in data["by_flag"]["--size"]

    def test_index_by_argument(self, tmp_path):
        kb = _make_kb()
        writer = SearchIndexWriter(tmp_path)
        writer.write(kb)

        data = json.loads((tmp_path / "search_index.json").read_text())
        assert "pool" in data["by_argument"]
