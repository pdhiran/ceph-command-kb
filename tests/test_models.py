"""Tests for data models."""

from ceph_command_kb.models import (
    Argument,
    ArgumentType,
    CephVersion,
    Command,
    Flag,
    KnowledgeBase,
)


class TestArgument:
    def test_to_dict_roundtrip(self):
        arg = Argument(
            name="pool",
            description="Pool name",
            required=True,
            arg_type=ArgumentType.POSITIONAL,
            value_type="str",
            default=None,
            choices=["replicated", "erasure"],
        )
        data = arg.to_dict()
        restored = Argument.from_dict(data)
        assert restored.name == "pool"
        assert restored.required is True
        assert restored.choices == ["replicated", "erasure"]
        assert restored.arg_type == ArgumentType.POSITIONAL

    def test_defaults(self):
        arg = Argument(name="test")
        assert arg.description == ""
        assert arg.required is False
        assert arg.choices == []


class TestFlag:
    def test_to_dict_roundtrip(self):
        flag = Flag(
            long_form="--pool-size",
            short_form="-s",
            description="Pool size",
            takes_value=True,
            value_name="<size>",
        )
        data = flag.to_dict()
        restored = Flag.from_dict(data)
        assert restored.long_form == "--pool-size"
        assert restored.short_form == "-s"
        assert restored.takes_value is True


class TestCommand:
    def test_to_dict_roundtrip(self):
        cmd = Command(
            name="ceph osd pool create",
            binary="ceph",
            parts=["ceph", "osd", "pool", "create"],
            description="create pool",
            arguments=[Argument(name="pool", required=True)],
            flags=[Flag(long_form="--size")],
            subcommands=[],
            raw_help="test help",
        )
        data = cmd.to_dict()
        restored = Command.from_dict(data)
        assert restored.name == "ceph osd pool create"
        assert restored.binary == "ceph"
        assert len(restored.arguments) == 1
        assert len(restored.flags) == 1

    def test_defaults(self):
        cmd = Command(name="test", binary="test", parts=["test"])
        assert cmd.description == ""
        assert cmd.subcommands == []
        assert cmd.deprecated is False


class TestCephVersion:
    def test_label(self):
        v = CephVersion(
            major=19, minor=2, patch=3,
            release_name="squid",
            full_string="ceph version 19.2.3 squid",
        )
        assert v.label() == "ceph-19.2.3-squid"

    def test_to_dict_roundtrip(self):
        v = CephVersion(
            major=18, minor=2, patch=0,
            release_name="reef",
            full_string="ceph version 18.2.0 reef",
        )
        data = v.to_dict()
        restored = CephVersion.from_dict(data)
        assert restored.major == 18
        assert restored.release_name == "reef"


class TestKnowledgeBase:
    def test_total_counts(self):
        kb = KnowledgeBase(
            version=CephVersion(0, 0, 0, "test", "test"),
            binaries_discovered=["ceph", "rbd"],
        )
        kb.commands["ceph osd ls"] = Command(
            name="ceph osd ls", binary="ceph", parts=["ceph", "osd", "ls"],
        )
        kb.commands["rbd ls"] = Command(
            name="rbd ls", binary="rbd", parts=["rbd", "ls"],
        )
        assert kb.total_commands == 2
        assert kb.total_binaries == 2

    def test_to_dict_roundtrip(self):
        kb = KnowledgeBase(
            version=CephVersion(19, 0, 0, "squid", "test"),
            generated_at="2025-01-01T00:00:00",
            generator_version="0.1.0",
            binaries_discovered=["ceph"],
            binary_versions={"ceph": "19.0.0"},
        )
        kb.commands["ceph status"] = Command(
            name="ceph status", binary="ceph", parts=["ceph", "status"],
            description="show cluster status",
        )
        data = kb.to_dict()
        restored = KnowledgeBase.from_dict(data)
        assert restored.total_commands == 1
        assert "ceph status" in restored.commands
