"""Background auto-updater — pulls latest changes from git on startup
and periodically thereafter.

Runs ``git pull --ff-only origin <branch>`` in a daemon thread so the
server starts instantly with whatever is on disk, then:

- If only knowledge base files changed → hot-reload commands/configs.
- If source code (.py) changed → ``os._exit(0)`` so Cursor restarts
  the MCP server process with the updated code.

A second daemon thread wakes up every *update_interval_hours* (default 1)
to repeat the check.

Every failure path logs a warning and returns — the server is never
blocked or crashed by this.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_periodic_stop: threading.Event | None = None

TRIGGER_NAME = ".reload_trigger"
TRIGGER_POLL_SECONDS = 5.0


def _find_repo_root(start: Path) -> Path | None:
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _has_remote(repo_dir: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "remote"],
            cwd=repo_dir, capture_output=True, text=True, timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _detect_default_branch(repo_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, cwd=str(repo_dir), timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip().replace("origin/", "")
    except Exception:
        pass
    return "main"


def _get_head_sha(repo_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _changed_files(repo_dir: Path, old_sha: str, new_sha: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", old_sha, new_sha],
            cwd=repo_dir, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except Exception:
        pass
    return []


def _git_pull(repo_dir: Path) -> tuple[bool, str]:
    branch = _detect_default_branch(repo_dir)
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only", "origin", branch],
            cwd=repo_dir, capture_output=True, text=True, timeout=120,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            stderr = result.stderr.strip()
            return False, f"git pull failed: {stderr or output}"
        if "Already up to date" in output:
            return False, "Already up to date"
        return True, output
    except subprocess.TimeoutExpired:
        return False, "git pull timed out"
    except Exception as exc:
        return False, f"git pull error: {exc}"


def _has_code_changes(files: list[str]) -> bool:
    return any(f.endswith(".py") for f in files)


def _has_kb_changes(files: list[str]) -> bool:
    return any(f.startswith("knowledge/") for f in files)


def _do_update(
    kb_path: Path,
    repo_root: Path,
    reload_fn: callable,
) -> None:
    try:
        old_sha = _get_head_sha(repo_root)
        changed, message = _git_pull(repo_root)

        if not changed:
            if "failed" in message.lower() or "error" in message.lower() or "timed out" in message.lower():
                logger.warning("Auto-update: %s", message)
            else:
                logger.info("Repository is up to date")
            return

        new_sha = _get_head_sha(repo_root)
        files = _changed_files(repo_root, old_sha, new_sha) if old_sha and new_sha else []

        if _has_code_changes(files):
            logger.info("Code changes detected, restarting MCP process (Cursor respawns it)")
            os._exit(0)
            return

        if _has_kb_changes(files) or not files:
            logger.info("Knowledge base updated, hot-reloading (no Cursor restart)")
            reload_fn(kb_path)

    except Exception as exc:
        logger.warning("Auto-update failed, continuing with existing data: %s", exc)


def _periodic_loop(
    kb_path: Path,
    repo_root: Path,
    reload_fn: callable,
    interval_seconds: float,
    stop_event: threading.Event,
) -> None:
    while not stop_event.wait(timeout=interval_seconds):
        _do_update(kb_path, repo_root, reload_fn)


def _trigger_mtime(repo_root: Path) -> float:
    try:
        return (repo_root / TRIGGER_NAME).stat().st_mtime
    except OSError:
        return 0.0


def _trigger_loop(
    kb_path: Path,
    repo_root: Path,
    reload_fn: callable,
    stop_event: threading.Event,
) -> None:
    last = _trigger_mtime(repo_root)
    while not stop_event.wait(timeout=TRIGGER_POLL_SECONDS):
        now = _trigger_mtime(repo_root)
        if now > last + 0.01:
            last = now
            logger.info("Reload trigger detected, hot-reloading knowledge base")
            try:
                reload_fn(kb_path)
            except Exception as exc:
                logger.warning("Trigger reload failed: %s", exc)


def _watch_root(kb_path: Path) -> Path:
    """Directory that holds ``.reload_trigger``. Does not require ``.git``.

    Version dir ``knowledge/ceph-*-*/`` → repo root. ``knowledge/`` → parent.
    """
    git = _find_repo_root(kb_path)
    if git is not None:
        return git
    path = kb_path.resolve()
    if (path / "commands.json").exists():
        return path.parent.parent
    if path.name == "knowledge":
        return path.parent
    return path


def start_auto_update(
    kb_path: Path,
    reload_fn: callable,
    *,
    update_interval_hours: float = 1,
) -> None:
    """Pull latest changes from git and hot-reload the KB in-process.

    ``./update_index.sh`` touches ``.reload_trigger``; a watcher thread
    picks that up within a few seconds so Cursor does not need a restart.
    Git pull of ``knowledge/`` also hot-reloads. A ``.py`` change exits
    the MCP subprocess so Cursor respawns it (the IDE itself stays open).
    """
    global _periodic_stop  # noqa: PLW0603

    if _periodic_stop is not None and not _periodic_stop.is_set():
        return

    git_root = _find_repo_root(kb_path)
    repo_root = _watch_root(kb_path)

    stop_event = threading.Event()
    _periodic_stop = stop_event

    if git_root is not None and _has_remote(git_root):
        thread = threading.Thread(
            target=_do_update,
            args=(kb_path, git_root, reload_fn),
            daemon=True,
            name="auto-update-startup",
        )
        thread.start()

        if update_interval_hours > 0:
            interval_seconds = update_interval_hours * 3600
            periodic = threading.Thread(
                target=_periodic_loop,
                args=(kb_path, git_root, reload_fn, interval_seconds, stop_event),
                daemon=True,
                name="auto-update-periodic",
            )
            periodic.start()

    trigger = threading.Thread(
        target=_trigger_loop,
        args=(kb_path, repo_root, reload_fn, stop_event),
        daemon=True,
        name="kb-reload-trigger",
    )
    trigger.start()


def stop_auto_update() -> None:
    global _periodic_stop  # noqa: PLW0603
    if _periodic_stop is not None:
        _periodic_stop.set()
        _periodic_stop = None
