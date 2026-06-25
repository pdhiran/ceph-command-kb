"""Tests for the batch validation engine."""

import json
from pathlib import Path

import pytest

from ceph_command_kb.models import Command, Flag
from ceph_command_kb.validation.validator import Validator

FIXTURES = Path(__file__).parent / "fixtures"


def _make_commands_map():
    """Build a minimal commands map for testing."""
    cmds = {}
    for name, desc, flags in [
        ("ceph osd pool create", "create pool", [
            Flag(long_form="--size", takes_value=True),
            Flag(long_form="--pg-num", takes_value=True),
        ]),
        ("ceph osd pool delete", "delete pool", [
            Flag(long_form="--yes-i-really-really-mean-it"),
        ]),
        ("ceph osd pool application enable", "enable application", []),
        ("ceph health", "show health", []),
        ("ceph -s", "", []),
        ("rbd create", "create image", [
            Flag(long_form="--size", takes_value=True),
            Flag(long_form="--pool", takes_value=True),
            Flag(long_form="--image-format", takes_value=True),
        ]),
        ("rbd rm", "remove image", [
            Flag(long_form="--pool", takes_value=True),
        ]),
        ("rbd mirror pool enable", "enable mirroring", []),
        ("rbd mirror image enable", "enable image mirroring", []),
        ("rbd mirror image demote", "demote image", []),
        ("rbd mirror image promote", "promote image", [
            Flag(long_form="--force"),
        ]),
        ("rbd mirror image status", "show status", []),
        ("rbd bench", "run benchmark", [
            Flag(long_form="--io-type", takes_value=True),
            Flag(long_form="--io-size", takes_value=True),
        ]),
        ("rados ls", "list objects", [
            Flag(long_form="--pool", takes_value=True),
        ]),
    ]:
        cmd_data = Command(
            name=name, binary=name.split()[0], parts=name.split(),
            description=desc, flags=flags,
        ).to_dict()
        cmds[name] = cmd_data
    return cmds


@pytest.fixture
def validator():
    return Validator(_make_commands_map())


class TestCommandVerification:
    def test_valid_commands_verified(self, validator):
        script = "ceph osd pool create mypool 32\nrbd create img --size 1024"
        report = validator.validate(script, script_type="shell")
        assert report.verified_commands >= 2

    def test_invalid_command_flagged(self, validator):
        script = "ceph nonexistent command here"
        report = validator.validate(script, script_type="shell")
        errors = [f for f in report.findings if f.phase == "command_verify"]
        assert len(errors) >= 1

    def test_unknown_flag_detected(self, validator):
        script = "ceph osd pool create mypool --nonexistent-flag 5"
        report = validator.validate(script, script_type="shell")
        flag_findings = [f for f in report.findings if f.phase == "flag_check"]
        assert len(flag_findings) >= 1


class TestCleanupValidation:
    def test_missing_cleanup_detected(self, validator):
        script = "ceph osd pool create mypool 32"
        report = validator.validate(script, script_type="shell")
        cleanup = [f for f in report.findings if f.phase == "cleanup"]
        assert len(cleanup) >= 1

    def test_cleanup_present_no_warning(self, validator):
        script = """ceph osd pool create mypool 32
ceph osd pool delete mypool mypool --yes-i-really-really-mean-it"""
        report = validator.validate(script, script_type="shell")
        cleanup = [f for f in report.findings if f.phase == "cleanup"]
        assert len(cleanup) == 0


class TestRiskDetection:
    def test_destructive_command_flagged(self, validator):
        script = "ceph osd pool delete mypool mypool --yes-i-really-really-mean-it"
        report = validator.validate(script, script_type="shell")
        risks = [f for f in report.findings if f.phase == "risk"]
        assert len(risks) >= 1

    def test_force_flag_warned(self, validator):
        script = "rbd mirror image promote pool/img --force"
        report = validator.validate(script, script_type="shell")
        risks = [f for f in report.findings if f.phase == "risk"]
        assert any("force" in r.message.lower() for r in risks)


class TestDuplicateDetection:
    def test_duplicate_detected(self, validator):
        script = """rbd create img --size 1024 --pool mypool
rbd create img --size 1024 --pool mypool"""
        report = validator.validate(script, script_type="shell")
        dupes = [f for f in report.findings if f.phase == "duplicate"]
        assert len(dupes) >= 1

    def test_health_checks_not_flagged(self, validator):
        script = """ceph health
ceph health
ceph health"""
        report = validator.validate(script, script_type="shell")
        dupes = [f for f in report.findings if f.phase == "duplicate"]
        assert len(dupes) == 0


class TestFullReport:
    def test_report_structure(self, validator):
        script = (FIXTURES / "sample_shell_test.sh").read_text()
        report = validator.validate(script, script_type="shell")
        d = report.to_dict()
        assert "total_commands" in d
        assert "verified_commands" in d
        assert "summary" in d
        assert "findings" in d
        assert "command_map" in d

    def test_cephci_fixture(self, validator):
        script = (FIXTURES / "sample_cephci_test.py").read_text()
        report = validator.validate(script, script_type="python")
        assert report.total_commands >= 5
        cleanup = [f for f in report.findings if f.phase == "cleanup"]
        assert len(cleanup) >= 1
