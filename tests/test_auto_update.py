"""Mock workflows: git-pull hot-reload, .py → process exit, .reload_trigger, update_index.sh, --since."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ceph_command_kb.server.auto_update import (
    _do_update,
    _find_repo_root,
    _git_pull,
    _has_kb_changes,
    _trigger_loop,
    start_auto_update,
    stop_auto_update,
)
from tests.conftest import write_mini_kb

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
    def test_git_pull_uses_ff_only(self, tmp_path):
        completed = MagicMock(returncode=0, stdout="Updating aaa..bbb\nFast-forward\n", stderr="")
        with (
            patch("ceph_command_kb.server.auto_update._detect_default_branch", return_value="main"),
            patch("ceph_command_kb.server.auto_update.subprocess.run", return_value=completed) as mock_run,
        ):
            changed, _ = _git_pull(tmp_path)
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["git", "pull", "--ff-only", "origin", "main"]
        assert changed is True

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
        """os._exit(0) then return — mocked _exit must not fall through to reload."""
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

    def test_touch_trigger_reloads_real_commands_json(self, tmp_path):
        from ceph_command_kb.server import mcp_server

        mcp_server._versions.clear()
        mcp_server._default_version_label = None
        vdir = tmp_path / "knowledge" / "ceph-20.2.1-tentacle"
        write_mini_kb(vdir, major=20, minor=2, patch=1, release="tentacle")
        mcp_server._load_knowledge_base(vdir)
        assert "ceph auth dump-keys" not in mcp_server._versions["ceph-20.2.1-tentacle"].commands_map

        try:
            with patch("ceph_command_kb.server.auto_update.TRIGGER_POLL_SECONDS", 0.05):
                start_auto_update(vdir, mcp_server._load_knowledge_base, update_interval_hours=0)
                time.sleep(0.08)
                names = [t.name for t in threading.enumerate()]
                assert "kb-reload-trigger" in names
                assert "auto-update-startup" not in names
                write_mini_kb(
                    vdir, major=20, minor=2, patch=1, release="tentacle",
                    extra_command="ceph auth dump-keys",
                )
                (tmp_path / ".reload_trigger").write_text("1")
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    vd = mcp_server._versions.get("ceph-20.2.1-tentacle")
                    if vd and "ceph auth dump-keys" in vd.commands_map:
                        break
                    time.sleep(0.05)
            assert "ceph auth dump-keys" in mcp_server._versions["ceph-20.2.1-tentacle"].commands_map
        finally:
            mcp_server._versions.clear()
            mcp_server._default_version_label = None


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
        assert "auto-update-startup" not in names
        assert "auto-update-periodic" not in names

    def test_no_remote_still_starts_trigger(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("ceph_command_kb.server.auto_update._has_remote", return_value=False):
            start_auto_update(tmp_path, MagicMock(), update_interval_hours=0)
        time.sleep(0.05)
        names = [t.name for t in threading.enumerate()]
        assert "kb-reload-trigger" in names
        assert "auto-update-startup" not in names
        assert "auto-update-periodic" not in names


def _stubbed_update_index(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    script = tmp_path / "update_index.sh"
    script.write_text((REPO / "update_index.sh").read_text())
    script.chmod(0o755)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "ceph").write_text("#!/bin/sh\nexit 0\n")
    (bindir / "ceph").chmod(0o755)
    (bindir / "python3").write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$0.argv\"\nexit 0\n"
    )
    (bindir / "python3").chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    return script, env, bindir / "python3.argv"


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

    def test_invalid_date_exits_2_before_ceph_check(self, tmp_path):
        script = tmp_path / "update_index.sh"
        script.write_text((REPO / "update_index.sh").read_text())
        script.chmod(0o755)
        env = {**os.environ, "PATH": "/usr/bin:/bin"}
        r = subprocess.run(
            [str(script), "not-a-date"],
            cwd=tmp_path, env=env, capture_output=True, text=True,
        )
        assert r.returncode == 2
        assert "invalid date" in r.stderr.lower()
        assert "ceph" not in r.stderr.lower()

    def test_days_vs_iso_vs_last_file(self, tmp_path):
        script, env, argv_path = _stubbed_update_index(tmp_path)

        r = subprocess.run(
            [str(script), "7"], cwd=tmp_path, env=env, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        argv = argv_path.read_text().splitlines()
        expect_7 = (date.today() - timedelta(days=7)).isoformat()
        assert argv[:5] == ["generate_reference.py", "--since", expect_7, "--verbose", "--force"]

        r = subprocess.run(
            [str(script), "2026-08-01"], cwd=tmp_path, env=env, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        argv = argv_path.read_text().splitlines()
        assert argv[1:3] == ["--since", "2026-08-01"]

        (tmp_path / ".last_index_update").write_text("2026-03-15\n")
        r = subprocess.run(
            [str(script)], cwd=tmp_path, env=env, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        argv = argv_path.read_text().splitlines()
        assert argv[1:3] == ["--since", "2026-03-15"]

    def test_last_index_update_file_is_yesterday_of_run(self, tmp_path):
        script, env, _ = _stubbed_update_index(tmp_path)
        r = subprocess.run(
            [str(script), "2026-08-01"], cwd=tmp_path, env=env, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        expected = (date.today() - timedelta(days=1)).isoformat()
        assert (tmp_path / ".last_index_update").read_text().strip() == expected
        assert (tmp_path / ".reload_trigger").exists()

    def test_updating_md_documents_canonical_command(self):
        text = (REPO / "UPDATING.md").read_text()
        assert "./update_index.sh" in text
        assert ".reload_trigger" in text
        assert "Cursor" in text
        assert "yesterday of the run date" in text
        assert "1-day overlap" in text
        assert "--no-auto-update" in text
        assert "also disables the trigger watcher" in text

    def test_readme_auto_update_and_ports(self):
        text = (REPO / "README.md").read_text()
        assert "--no-auto-update" in text
        assert "disables **both**" in text
        assert "--port 8081" in text
        assert "--port 9090" in text
        assert "full rediscovery" in text
        assert "1-day overlap" in text
        assert "yesterday of the run date" in text

    def test_last_index_update_writes_yesterday(self):
        text = (REPO / "update_index.sh").read_text()
        assert 'date -v-1d +%Y-%m-%d > "$LAST_RUN_FILE"' in text
        assert "1-day overlap" in text

    def test_mcp_help_no_auto_update_kills_trigger(self):
        r = subprocess.run(
            ["python3", "-m", "ceph_command_kb.server.mcp_server", "--help"],
            cwd=REPO, capture_output=True, text=True, check=True,
        )
        compact = " ".join(r.stdout.split()).lower()
        assert "--no-auto-update" in r.stdout
        assert "8081" in r.stdout
        assert "disables both" in compact
        assert "trigger" in compact

    def test_no_auto_update_skips_start_auto_update(self):
        text = (REPO / "src/ceph_command_kb/server/mcp_server.py").read_text()
        guard = text.split("if args.auto_update:")[1].split("run_server(")[0]
        assert "start_auto_update" in guard
        after = text.split("if args.auto_update:")[0]
        assert "start_auto_update(" not in after

    def test_no_auto_update_does_not_start_git_or_trigger(self, tmp_path):
        from ceph_command_kb.server import mcp_server

        with (
            patch("ceph_command_kb.server.auto_update.start_auto_update") as start,
            patch.object(mcp_server, "run_server"),
        ):
            mcp_server.main(["--no-auto-update", "--kb-path", str(tmp_path)])
        start.assert_not_called()

    def test_auto_update_default_starts(self, tmp_path):
        from ceph_command_kb.server import mcp_server

        with (
            patch("ceph_command_kb.server.auto_update.start_auto_update") as start,
            patch.object(mcp_server, "run_server"),
            patch.object(mcp_server, "_find_latest_kb", return_value=tmp_path),
        ):
            mcp_server.main([])
        start.assert_called_once()
        assert start.call_args[0][0] == tmp_path
        assert start.call_args[0][1] is mcp_server._load_knowledge_base
        assert start.call_args.kwargs["update_interval_hours"] == 1

    def test_vscode_command_ids_match(self):
        import json as json_mod

        pkg = json_mod.loads((REPO / "vscode-extension/package.json").read_text())
        ids = [c["command"] for c in pkg["contributes"]["commands"]]
        assert ids == [
            "ceph-cmd-kb.verifyCommand",
            "ceph-cmd-kb.searchCommands",
            "ceph-cmd-kb.verifyConfig",
            "ceph-cmd-kb.reviewScript",
            "ceph-cmd-kb.insertCommand",
        ]
        js = (REPO / "vscode-extension/extension.js").read_text()
        for cid in ids:
            assert f"registerCommand('{cid}'" in js
        for event in pkg["activationEvents"]:
            assert event.removeprefix("onCommand:") in ids


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
        write_mini_kb(squid, major=19, minor=2, patch=1, release="squid")
        write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle")

        mcp_server._load_knowledge_base(tentacle)
        assert set(mcp_server._versions) == {
            "ceph-19.2.1-squid",
            "ceph-20.2.1-tentacle",
        }
        assert "ceph auth dump-keys" not in mcp_server._versions["ceph-20.2.1-tentacle"].commands_map

        write_mini_kb(
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
        write_mini_kb(squid, major=19, minor=2, patch=1, release="squid")
        write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle")
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
        write_mini_kb(squid, major=19, minor=2, patch=1, release="squid")
        write_mini_kb(tentacle, major=20, minor=2, patch=1, release="tentacle")
        mcp_server._load_knowledge_base(tentacle)
        before = set(mcp_server._versions)

        mcp_server._load_knowledge_base(tmp_path / "does-not-exist")

        assert set(mcp_server._versions) == before


class TestSinceDelta:
    """--since records a window; it does not date-filter command --help."""

    def test_invalid_date_exits_1(self):
        r = subprocess.run(
            ["python3", str(REPO / "generate_reference.py"), "--since", "not-a-date"],
            cwd=REPO, capture_output=True, text=True,
        )
        assert r.returncode == 1
        assert "YYYY-MM-DD" in r.stderr

    def test_help_says_full_rediscovery(self):
        r = subprocess.run(
            ["python3", str(REPO / "generate_reference.py"), "--help"],
            cwd=REPO, capture_output=True, text=True, check=True,
        )
        help_text = r.stdout.lower()
        assert "no date filter" in help_text or "full rediscovery" in help_text
        assert "updated_since" in help_text

    def test_stamp_records_window(self, tmp_path):
        import importlib.util
        import json as json_mod

        spec = importlib.util.spec_from_file_location(
            "generate_reference", REPO / "generate_reference.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        (tmp_path / "metadata.json").write_text('{"total_commands": 1}\n')
        mod._stamp_updated_since(tmp_path, "2026-08-01")
        data = json_mod.loads((tmp_path / "metadata.json").read_text())
        assert data["updated_since"] == "2026-08-01"
        assert "last_incremental_at" in data
        assert data["total_commands"] == 1

    def test_since_does_not_skip_discover_all(self):
        text = (REPO / "generate_reference.py").read_text()
        main = text.split("def main()")[1].split("def _reparse")[0]
        assert "kb = engine.discover_all()" in main
        assert "_stamp_updated_since" in main
        before_discover = main.split("engine.discover_all()")[0]
        assert "if args.since" not in before_discover.split("if args.reparse")[-1]
        assert "discover_all(since" not in text
        engine = (REPO / "src/ceph_command_kb/discovery/engine.py").read_text()
        assert "since" not in engine.lower()
