"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import yaml

from ceph_command_kb.config import Config, DEFAULT_BINARIES


class TestConfigDefaults:
    def test_default_binaries(self):
        config = Config._defaults()
        names = [b.name for b in config.binaries]
        assert "ceph" in names
        assert "rbd" in names
        assert "rados" in names
        assert "cephadm" in names
        assert len(names) == len(DEFAULT_BINARIES)

    def test_default_values(self):
        config = Config._defaults()
        assert config.output_dir == "knowledge"
        assert config.workers == 4
        assert config.command_timeout == 10
        assert config.resume is False
        assert config.force is False


class TestConfigLoad:
    def test_load_from_yaml(self, tmp_path):
        config_data = {
            "binaries": ["ceph", "rbd"],
            "output_dir": "custom_output",
            "workers": 8,
            "log_level": "DEBUG",
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        config = Config.load(config_file)
        assert len(config.binaries) == 2
        assert config.output_dir == "custom_output"
        assert config.workers == 8
        assert config.log_level == "DEBUG"

    def test_load_missing_file_uses_defaults(self):
        config = Config.load(Path("/nonexistent/config.yaml"))
        assert len(config.binaries) == len(DEFAULT_BINARIES)

    def test_detailed_binary_config(self, tmp_path):
        config_data = {
            "binaries": [
                {"name": "ceph", "max_depth": 5, "parser": "ceph"},
                "rbd",
            ],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        config = Config.load(config_file)
        assert config.binaries[0].name == "ceph"
        assert config.binaries[0].max_depth == 5
        assert config.binaries[0].parser == "ceph"
        assert config.binaries[1].name == "rbd"


class TestConfigMergeCli:
    def test_cli_args_override(self):
        config = Config._defaults()
        config.merge_cli_args(
            output="custom",
            workers=16,
            resume=True,
            verbose=True,
        )
        assert config.output_dir == "custom"
        assert config.workers == 16
        assert config.resume is True
        assert config.log_level == "DEBUG"

    def test_none_args_dont_override(self):
        config = Config._defaults()
        config.merge_cli_args()
        assert config.output_dir == "knowledge"
        assert config.workers == 4
