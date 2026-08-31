"""REST API must forward `version` the same way MCP tools do."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from ceph_command_kb.server import mcp_server, rest_api
from tests.conftest import write_mini_kb


@pytest.fixture
def rest_client(tmp_path):
    squid = tmp_path / "ceph-19.2.1-squid"
    tentacle = tmp_path / "ceph-20.2.1-tentacle"
    write_mini_kb(squid, major=19, minor=2, patch=1, release="squid",
                  extra_command="ceph squid only")
    write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle",
                  extra_command="ceph tentacle only")
    mcp_server._load_knowledge_base(tentacle)
    yield TestClient(rest_api.app)
    mcp_server._versions.clear()
    mcp_server._default_version_label = None


class TestRestVersion:
    def test_verify_command_honors_version(self, rest_client):
        squid = rest_client.post(
            "/api/verify_command",
            json={"command": "ceph squid only", "version": "squid"},
        ).json()
        tentacle = rest_client.post(
            "/api/verify_command",
            json={"command": "ceph squid only", "version": "tentacle"},
        ).json()
        assert squid["status"] == "VERIFIED"
        assert tentacle["status"] == "NOT_VERIFIED"

    def test_omitted_version_uses_default_latest(self, rest_client):
        result = rest_client.post(
            "/api/verify_command",
            json={"command": "ceph tentacle only"},
        ).json()
        assert result["status"] == "VERIFIED"

    def test_list_versions_get_and_post(self, rest_client):
        via_get = rest_client.get("/api/list_versions").json()
        via_post = rest_client.post("/api/list_versions").json()
        assert via_get["total_versions"] == 2
        assert via_post["total_versions"] == 2

    def test_search_commands_honors_version(self, rest_client):
        squid = rest_client.post(
            "/api/search_commands",
            json={"query": "ceph squid only", "version": "squid"},
        ).json()
        tentacle = rest_client.post(
            "/api/search_commands",
            json={"query": "ceph squid only", "version": "tentacle"},
        ).json()
        squid_names = [r["name"] for r in squid["results"]]
        tentacle_names = [r["name"] for r in tentacle["results"]]
        assert "ceph squid only" in squid_names
        assert "ceph squid only" not in tentacle_names

    def test_handlers_forward_version_kwarg(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[1] / "src/ceph_command_kb/server/rest_api.py").read_text()
        skip = {"handle_health", "handle_capabilities", "handle_list_versions"}
        handlers = [
            line.split("(")[0].replace("async def ", "").strip()
            for line in text.splitlines()
            if line.startswith("async def handle_")
        ]
        versioned = [h for h in handlers if h not in skip]
        assert len(versioned) == 17
        assert text.count("version=params.get(\"version\")") == 17
