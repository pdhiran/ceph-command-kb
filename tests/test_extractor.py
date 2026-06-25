"""Tests for command extraction from scripts."""

from pathlib import Path

from ceph_command_kb.validation.extractor import extract_from_text

FIXTURES = Path(__file__).parent / "fixtures"


class TestShellExtraction:
    def test_extracts_ceph_commands(self):
        script = """#!/bin/bash
ceph osd pool create mypool 32
rbd create myimg --size 1024 --pool mypool
rados ls --pool mypool
"""
        cmds = extract_from_text(script, script_type="shell")
        assert len(cmds) == 3
        assert cmds[0].binary == "ceph"
        assert cmds[1].binary == "rbd"
        assert cmds[2].binary == "rados"

    def test_ignores_comments(self):
        script = """#!/bin/bash
# ceph osd pool create commented_pool 32
ceph osd pool create real_pool 32
"""
        cmds = extract_from_text(script, script_type="shell")
        assert len(cmds) == 1
        assert "real_pool" in cmds[0].raw

    def test_extracts_flags(self):
        script = "rbd create myimg --size 1024 --pool mypool --image-format 2"
        cmds = extract_from_text(script, script_type="shell")
        assert len(cmds) == 1
        assert "--size" in cmds[0].flags
        assert "--pool" in cmds[0].flags
        assert "--image-format" in cmds[0].flags

    def test_extracts_from_fixture(self):
        script = (FIXTURES / "sample_shell_test.sh").read_text()
        cmds = extract_from_text(script, script_type="shell")
        assert len(cmds) >= 5
        binaries = {c.binary for c in cmds}
        assert "ceph" in binaries
        assert "rbd" in binaries


class TestPythonExtraction:
    def test_extracts_shell_commands(self):
        script = '''
def test_pool(cluster):
    cluster.shell(cmd="ceph osd pool create testpool 32")
    cluster.shell(cmd="rbd create img --size 512 --pool testpool")
'''
        cmds = extract_from_text(script, script_type="python")
        assert len(cmds) >= 2
        assert any(c.binary == "ceph" for c in cmds)
        assert any(c.binary == "rbd" for c in cmds)

    def test_extracts_fstring_commands(self):
        script = '''
pool = "mypool"
cluster.shell(cmd=f"ceph osd pool create {pool} 32")
'''
        cmds = extract_from_text(script, script_type="python")
        assert len(cmds) >= 1
        assert cmds[0].binary == "ceph"

    def test_extracts_from_cephci_fixture(self):
        script = (FIXTURES / "sample_cephci_test.py").read_text()
        cmds = extract_from_text(script, script_type="python")
        assert len(cmds) >= 5
        binaries = {c.binary for c in cmds}
        assert "ceph" in binaries
        assert "rbd" in binaries


class TestAutoDetection:
    def test_detects_python(self):
        script = '''#!/usr/bin/env python3
import pytest
def test_foo():
    pass
'''
        cmds = extract_from_text(script, script_type="auto")
        assert isinstance(cmds, list)

    def test_detects_shell(self):
        script = "#!/bin/bash\nceph osd pool create test 32\n"
        cmds = extract_from_text(script, script_type="auto")
        assert len(cmds) == 1
