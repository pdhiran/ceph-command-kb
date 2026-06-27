"""Tests for MCP server tools."""

import json
from pathlib import Path

import pytest

from ceph_command_kb.models import (
    Argument,
    CephVersion,
    Command,
    Flag,
    KnowledgeBase,
)
from ceph_command_kb.server import mcp_server
from ceph_command_kb.storage.json_writer import JsonWriter
from ceph_command_kb.storage.search_index import SearchIndexWriter


@pytest.fixture
def kb_dir(tmp_path):
    """Create a temporary knowledge base for testing."""
    version = CephVersion(19, 2, 0, "squid", "ceph version 19.2.0 squid")
    kb = KnowledgeBase(
        version=version,
        generated_at="2025-01-01T00:00:00Z",
        generator_version="0.1.0",
        binaries_discovered=["ceph", "rbd"],
        binary_versions={"ceph": "19.2.0"},
    )
    kb.commands["ceph osd pool create"] = Command(
        name="ceph osd pool create",
        binary="ceph",
        parts=["ceph", "osd", "pool", "create"],
        description="create pool",
        usage="ceph osd pool create <pool>",
        arguments=[Argument(name="pool", required=True)],
        flags=[Flag(long_form="--size", takes_value=True, description="Pool size")],
        subcommands=[],
        keywords=["ceph", "osd", "pool", "create"],
    )
    kb.commands["ceph osd pool delete"] = Command(
        name="ceph osd pool delete",
        binary="ceph",
        parts=["ceph", "osd", "pool", "delete"],
        description="delete pool",
        keywords=["ceph", "osd", "pool", "delete"],
    )
    kb.commands["ceph osd ls"] = Command(
        name="ceph osd ls",
        binary="ceph",
        parts=["ceph", "osd", "ls"],
        description="show all OSD ids",
        keywords=["ceph", "osd", "ls", "show"],
    )
    kb.commands["rbd create"] = Command(
        name="rbd create",
        binary="rbd",
        parts=["rbd", "create"],
        description="Create an empty rbd image",
        flags=[Flag(long_form="--size", takes_value=True)],
        keywords=["rbd", "create", "image"],
    )

    JsonWriter(tmp_path).write(kb)
    SearchIndexWriter(tmp_path).write(kb)
    return tmp_path


@pytest.fixture(autouse=True)
def load_kb(kb_dir):
    mcp_server._load_knowledge_base(kb_dir)
    yield
    mcp_server._kb_data = None
    mcp_server._search_index = None
    mcp_server._kb_dir = None
    mcp_server._commands_map_cache = None
    mcp_server._config_data = None


class TestFindCommand:
    def test_found(self):
        result = json.loads(mcp_server.find_command("ceph osd pool create"))
        assert result["found"] is True
        assert result["command"]["name"] == "ceph osd pool create"

    def test_not_found_with_suggestions(self):
        result = json.loads(mcp_server.find_command("ceph osd pool"))
        assert result["found"] is False
        assert "similar_commands" in result


class TestVerifyCommand:
    def test_verified(self):
        result = json.loads(mcp_server.verify_command("ceph osd pool create"))
        assert result["status"] == "VERIFIED"
        assert result["command_verified"] is True

    def test_not_verified(self):
        result = json.loads(mcp_server.verify_command("ceph nonexistent command"))
        assert result["status"] == "NOT_VERIFIED"
        assert result["command_verified"] is False

    def test_verify_with_valid_flags(self):
        result = json.loads(mcp_server.verify_command(
            "ceph osd pool create",
            flags=["--size"],
        ))
        assert result["status"] == "VERIFIED"
        assert result["flags_verified"]["--size"] is True

    def test_verify_with_invalid_flags(self):
        result = json.loads(mcp_server.verify_command(
            "ceph osd pool create",
            flags=["--nonexistent"],
        ))
        assert result["status"] == "PARTIALLY_VERIFIED"
        assert result["flags_verified"]["--nonexistent"] is False

    def test_verify_with_arguments(self):
        result = json.loads(mcp_server.verify_command(
            "ceph osd pool create",
            arguments=["pool"],
        ))
        assert result["status"] == "VERIFIED"
        assert result["arguments_verified"]["pool"] is True


class TestSearchCommands:
    def test_exact_match(self):
        result = json.loads(mcp_server.search_commands("ceph osd pool create"))
        assert result["total_results"] >= 1
        assert result["results"][0]["name"] == "ceph osd pool create"

    def test_partial_match(self):
        result = json.loads(mcp_server.search_commands("pool"))
        assert result["total_results"] >= 2

    def test_no_results(self):
        result = json.loads(mcp_server.search_commands("xyznonexistent"))
        assert result["total_results"] == 0


class TestListSubcommands:
    def test_by_prefix(self):
        result = json.loads(mcp_server.list_subcommands("ceph osd"))
        subs = result["subcommands"]
        names = [s["name"] for s in subs]
        assert "ceph osd ls" in names
        assert "ceph osd pool create" in names or "ceph osd pool delete" in names


class TestSearchFlag:
    def test_found(self):
        result = json.loads(mcp_server.search_flag("--size"))
        assert result["found"] is True
        assert "ceph osd pool create" in result["commands"]

    def test_not_found(self):
        result = json.loads(mcp_server.search_flag("--nonexistent"))
        assert result["found"] is False


class TestFindBinary:
    def test_found(self):
        result = json.loads(mcp_server.find_binary("rbd"))
        assert result["found"] is True
        assert "rbd create" in result["commands"]

    def test_not_found(self):
        result = json.loads(mcp_server.find_binary("nonexistent"))
        assert result["found"] is False
