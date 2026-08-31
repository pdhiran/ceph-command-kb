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
