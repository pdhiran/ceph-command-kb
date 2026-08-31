"""Mock workflows: git-pull hot-reload, .py → process exit, .reload_trigger, update_index.sh."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ceph_command_kb.server.auto_update import (
    _do_update,
    _find_repo_root,
    _has_kb_changes,
    _trigger_loop,
    start_auto_update,
    stop_auto_update,
)

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _cleanup_auto_update():
    yield
    stop_auto_update()


class TestHelpers:
    def test_finds_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert _find_repo_root(nested) == tmp_path

    def test_kb_change_detection(self):
        assert _has_kb_changes(["knowledge/ceph-20.2.1-tentacle/commands.json"])
        assert not _has_kb_changes(["README.md"])


class TestDoUpdate:
    def test_knowledge_pull_hot_reloads(self, tmp_path):
        reload_fn = MagicMock()
        with (
            patch("ceph_command_kb.server.auto_update._git_pull", return_value=(True, "Updated")),
            patch("ceph_command_kb.server.auto_update._get_head_sha", side_effect=["aaa", "bbb"]),
            patch(
                "ceph_command_kb.server.auto_update._changed_files",
                return_value=["knowledge/ceph-20.2.1-tentacle/commands.json"],
            ),
            patch("ceph_command_kb.server.auto_update.os._exit") as mock_exit,
        ):
            _do_update(tmp_path, tmp_path, reload_fn)
        reload_fn.assert_called_once_with(tmp_path)
        mock_exit.assert_not_called()

    def test_empty_file_list_still_reloads(self, tmp_path):
        reload_fn = MagicMock()
        with (
            patch("ceph_command_kb.server.auto_update._git_pull", return_value=(True, "Updated")),
            patch("ceph_command_kb.server.auto_update._get_head_sha", side_effect=["aaa", "bbb"]),
            patch("ceph_command_kb.server.auto_update._changed_files", return_value=[]),
            patch("ceph_command_kb.server.auto_update.os._exit") as mock_exit,
        ):
            _do_update(tmp_path, tmp_path, reload_fn)
        reload_fn.assert_called_once()
        mock_exit.assert_not_called()

    def test_python_change_exits_process(self, tmp_path):
        reload_fn = MagicMock()
        with (
            patch("ceph_command_kb.server.auto_update._git_pull", return_value=(True, "Updated")),
            patch("ceph_command_kb.server.auto_update._get_head_sha", side_effect=["aaa", "bbb"]),
            patch(
                "ceph_command_kb.server.auto_update._changed_files",
                return_value=["src/ceph_command_kb/server/mcp_server.py"],
            ),
            patch("ceph_command_kb.server.auto_update.os._exit") as mock_exit,
        ):
            _do_update(tmp_path, tmp_path, reload_fn)
        mock_exit.assert_called_once_with(0)
        reload_fn.assert_not_called()

    def test_already_up_to_date_skips_reload(self, tmp_path):
        reload_fn = MagicMock()
        with patch(
            "ceph_command_kb.server.auto_update._git_pull",
            return_value=(False, "Already up to date"),
        ):
            _do_update(tmp_path, tmp_path, reload_fn)
        reload_fn.assert_not_called()

    def test_exception_does_not_propagate(self, tmp_path):
        with patch(
            "ceph_command_kb.server.auto_update._git_pull",
            side_effect=RuntimeError("boom"),
        ):
            _do_update(tmp_path, tmp_path, MagicMock())


class TestTriggerLoop:
    def test_touch_trigger_reloads_without_git(self, tmp_path):
        reload_fn = MagicMock()
        stop = threading.Event()
        with patch("ceph_command_kb.server.auto_update.TRIGGER_POLL_SECONDS", 0.05):
            t = threading.Thread(
                target=_trigger_loop,
                args=(tmp_path, tmp_path, reload_fn, stop),
                daemon=True,
            )
            t.start()
            time.sleep(0.08)
            (tmp_path / ".reload_trigger").write_text("1")
            deadline = time.time() + 2.0
            while time.time() < deadline and not reload_fn.called:
                time.sleep(0.05)
            stop.set()
            t.join(timeout=1)
        reload_fn.assert_called()


class TestStartAutoUpdate:
    def test_no_git_still_watches_trigger(self, tmp_path):
        knowledge = tmp_path / "knowledge" / "ceph-20.2.1-tentacle"
        knowledge.mkdir(parents=True)
        (knowledge / "commands.json").write_text("{}")
        with patch("ceph_command_kb.server.auto_update._has_remote", return_value=False):
            start_auto_update(knowledge, MagicMock(), update_interval_hours=0)
        time.sleep(0.05)
        names = [t.name for t in threading.enumerate()]
        assert "kb-reload-trigger" in names

    def test_no_remote_still_starts_trigger(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("ceph_command_kb.server.auto_update._has_remote", return_value=False):
            start_auto_update(tmp_path, MagicMock(), update_interval_hours=0)
        time.sleep(0.05)
        names = [t.name for t in threading.enumerate()]
        assert "kb-reload-trigger" in names


class TestUpdateIndexScript:
    def test_script_touches_reload_trigger(self):
        text = (REPO / "update_index.sh").read_text()
        assert "touch .reload_trigger" in text
        assert "generate_reference.py" in text

    def test_wrapper_execs_update_index(self):
        text = (REPO / "update_kb.sh").read_text()
        assert "update_index.sh" in text

    def test_reset_clears_tracker(self, tmp_path):
        script = tmp_path / "update_index.sh"
        script.write_text((REPO / "update_index.sh").read_text())
        script.chmod(0o755)
        (tmp_path / ".last_index_update").write_text("2026-01-01\n")
        subprocess.run([str(script), "--reset"], cwd=tmp_path, check=True)
        assert not (tmp_path / ".last_index_update").exists()

    def test_updating_md_documents_canonical_command(self):
        text = (REPO / "UPDATING.md").read_text()
        assert "./update_index.sh" in text
        assert ".reload_trigger" in text
        assert "Cursor" in text


def _write_mini_kb(dest: Path, *, major: int, minor: int, patch: int,
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


class TestLoadKnowledgeBase:
    """Hot-reload must re-read every version dir, including ones already in memory."""

    @pytest.fixture(autouse=True)
    def _reset_versions(self):
        from ceph_command_kb.server import mcp_server
        yield
        mcp_server._versions.clear()
        mcp_server._default_version_label = None

    def test_reload_picks_up_all_versions_and_new_json(self, tmp_path):
        from ceph_command_kb.server import mcp_server

        squid = tmp_path / "ceph-19.2.1-squid"
        tentacle = tmp_path / "ceph-20.2.1-tentacle"
        _write_mini_kb(squid, major=19, minor=2, patch=1, release="squid")
        _write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle")

        mcp_server._load_knowledge_base(tentacle)
        assert set(mcp_server._versions) == {
            "ceph-19.2.1-squid",
            "ceph-20.2.1-tentacle",
        }
        assert "ceph auth dump-keys" not in mcp_server._versions["ceph-20.2.1-tentacle"].commands_map

        _write_mini_kb(
            tentacle, major=20, minor=2, patch=1, release="tentacle",
            extra_command="ceph auth dump-keys",
        )
        mcp_server._load_knowledge_base(tentacle)

        assert set(mcp_server._versions) == {
            "ceph-19.2.1-squid",
            "ceph-20.2.1-tentacle",
        }
        assert "ceph auth dump-keys" in mcp_server._versions["ceph-20.2.1-tentacle"].commands_map
        assert "ceph osd ls" in mcp_server._versions["ceph-19.2.1-squid"].commands_map

    def test_reload_does_not_empty_versions_mid_load(self, tmp_path):
        from ceph_command_kb.server import mcp_server

        squid = tmp_path / "ceph-19.2.1-squid"
        tentacle = tmp_path / "ceph-20.2.1-tentacle"
        _write_mini_kb(squid, major=19, minor=2, patch=1, release="squid")
        _write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle")
        mcp_server._load_knowledge_base(tentacle)

        seen: list[int] = []
        orig = mcp_server._load_version

        def spy(path):
            seen.append(len(mcp_server._versions))
            return orig(path)

        with patch.object(mcp_server, "_load_version", side_effect=spy):
            mcp_server._load_knowledge_base(tentacle)

        assert seen
        assert all(n >= 2 for n in seen), f"KB was empty mid-reload: {seen}"

    def test_failed_reload_keeps_previous_versions(self, tmp_path):
        from ceph_command_kb.server import mcp_server

        squid = tmp_path / "ceph-19.2.1-squid"
        tentacle = tmp_path / "ceph-20.2.1-tentacle"
        _write_mini_kb(squid, major=19, minor=2, patch=1, release="squid")
        _write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle")
        mcp_server._load_knowledge_base(tentacle)
        before = set(mcp_server._versions)

        mcp_server._load_knowledge_base(tmp_path / "does-not-exist")

        assert set(mcp_server._versions) == before
