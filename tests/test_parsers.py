"""Tests for help output parsers."""

import pytest

from ceph_command_kb.parsing.argparse_parser import ArgparseParser
from ceph_command_kb.parsing.boost_parser import BoostParser
from ceph_command_kb.parsing.ceph_parser import CephParser
from ceph_command_kb.parsing.generic_parser import GenericParser
from ceph_command_kb.parsing.registry import ParserRegistry


class TestCephParser:
    def test_extracts_subcommands(self, ceph_help_text):
        parser = CephParser()
        result = parser.parse(ceph_help_text, command_parts=["ceph"])

        assert "auth" in result.subcommand_names
        assert "osd" in result.subcommand_names
        assert "pg" in result.subcommand_names
        assert "config" in result.subcommand_names
        assert "crash" in result.subcommand_names

    def test_extracts_osd_subcommands(self, ceph_help_text):
        parser = CephParser()
        result = parser.parse(ceph_help_text, command_parts=["ceph"])
        assert "osd" in result.subcommand_names

    def test_can_parse_detection(self, ceph_help_text):
        parser = CephParser()
        assert parser.can_parse(ceph_help_text)

    def test_does_not_match_boost_format(self, rbd_help_text):
        parser = CephParser()
        assert not parser.can_parse(rbd_help_text)


class TestBoostParser:
    def test_extracts_subcommands(self, rbd_help_text):
        parser = BoostParser()
        result = parser.parse(rbd_help_text, command_parts=["rbd"])

        assert "bench" in result.subcommand_names
        assert "create" in result.subcommand_names
        assert "clone" in result.subcommand_names
        assert "snap" in result.subcommand_names
        assert "mirror" in result.subcommand_names
        assert "ls" not in result.subcommand_names or "list" in result.subcommand_names

    def test_extracts_flags(self, rbd_help_text):
        parser = BoostParser()
        result = parser.parse(rbd_help_text, command_parts=["rbd"])

        flag_longs = {f.long_form for f in result.flags if f.long_form}
        assert "--pool" in flag_longs or "-p" in {f.short_form for f in result.flags}

    def test_extracts_description(self, rbd_help_text):
        parser = BoostParser()
        result = parser.parse(rbd_help_text, command_parts=["rbd"])
        assert "RADOS block device" in result.description or "RBD" in result.description

    def test_can_parse_detection(self, rbd_help_text):
        parser = BoostParser()
        assert parser.can_parse(rbd_help_text)

    def test_does_not_match_argparse(self, cephadm_help_text):
        parser = BoostParser()
        assert not parser.can_parse(cephadm_help_text)


class TestArgparseParser:
    def test_extracts_subcommands(self, cephadm_help_text):
        parser = ArgparseParser()
        result = parser.parse(cephadm_help_text, command_parts=["cephadm"])

        assert "bootstrap" in result.subcommand_names
        assert "shell" in result.subcommand_names
        assert "deploy" in result.subcommand_names
        assert "ls" in result.subcommand_names

    def test_extracts_flags(self, cephadm_help_text):
        parser = ArgparseParser()
        result = parser.parse(cephadm_help_text, command_parts=["cephadm"])

        flag_longs = {f.long_form for f in result.flags if f.long_form}
        assert "--image" in flag_longs
        assert "--docker" in flag_longs
        assert "--verbose" in flag_longs

    def test_extracts_description(self, cephadm_help_text):
        parser = ArgparseParser()
        result = parser.parse(cephadm_help_text, command_parts=["cephadm"])
        assert "daemon" in result.description.lower() or "ceph" in result.description.lower()

    def test_can_parse_detection(self, cephadm_help_text):
        parser = ArgparseParser()
        assert parser.can_parse(cephadm_help_text)


class TestGenericParser:
    def test_always_can_parse(self):
        parser = GenericParser()
        assert parser.can_parse("anything goes here")
        assert parser.can_parse("")

    def test_extracts_flags_from_standard_format(self):
        parser = GenericParser()
        text = """usage: tool [options]

Options:
  -v, --verbose          Enable verbose output
  -o, --output FILE      Output file path
  -h, --help             Show help
"""
        result = parser.parse(text)
        flag_longs = {f.long_form for f in result.flags}
        assert "--verbose" in flag_longs
        assert "--output" in flag_longs


class TestParserRegistry:
    def test_default_mappings(self):
        registry = ParserRegistry()
        assert isinstance(registry.get_parser("ceph"), CephParser)
        assert isinstance(registry.get_parser("rbd"), BoostParser)
        assert isinstance(registry.get_parser("rados"), BoostParser)
        assert isinstance(registry.get_parser("cephadm"), ArgparseParser)
        assert isinstance(registry.get_parser("ceph-volume"), ArgparseParser)

    def test_unknown_binary_returns_fallback(self):
        registry = ParserRegistry()
        parser = registry.get_parser("unknown-tool")
        assert isinstance(parser, GenericParser)

    def test_register_custom_parser(self):
        registry = ParserRegistry()
        registry.register_by_name("my-tool", "argparse")
        assert isinstance(registry.get_parser("my-tool"), ArgparseParser)

    def test_auto_detect_boost(self, rbd_help_text):
        registry = ParserRegistry()
        parser = registry.get_parser_for_output("unknown-tool", rbd_help_text)
        assert isinstance(parser, BoostParser)

    def test_auto_detect_argparse(self, cephadm_help_text):
        registry = ParserRegistry()
        parser = registry.get_parser_for_output("unknown-tool", cephadm_help_text)
        assert isinstance(parser, ArgparseParser)
