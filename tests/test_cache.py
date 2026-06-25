"""Tests for the discovery cache."""

from pathlib import Path

from ceph_command_kb.discovery.cache import DiscoveryCache


class TestDiscoveryCache:
    def test_mark_and_check_visited(self):
        cache = DiscoveryCache()
        assert not cache.is_visited("ceph osd ls")
        cache.mark_visited("ceph osd ls")
        assert cache.is_visited("ceph osd ls")

    def test_mark_failed(self):
        cache = DiscoveryCache()
        cache.mark_failed("bad command", "not found")
        assert "bad command" in cache.failed
        assert cache.failed["bad command"] == "not found"

    def test_clear(self):
        cache = DiscoveryCache()
        cache.mark_visited("test")
        cache.mark_failed("test2", "err")
        cache.clear()
        assert len(cache.visited) == 0
        assert len(cache.failed) == 0

    def test_save_and_load(self, tmp_path):
        cache = DiscoveryCache(_cache_path=tmp_path / "discovery_state.json")
        cache.mark_visited("ceph osd ls")
        cache.mark_visited("ceph osd tree")
        cache.mark_failed("ceph bad", "unknown")
        cache.save()

        loaded = DiscoveryCache.load(tmp_path)
        assert loaded.is_visited("ceph osd ls")
        assert loaded.is_visited("ceph osd tree")
        assert "ceph bad" in loaded.failed

    def test_load_empty_dir(self, tmp_path):
        cache = DiscoveryCache.load(tmp_path)
        assert len(cache.visited) == 0
        assert len(cache.failed) == 0
