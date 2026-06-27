"""Data models for the Ceph command knowledge base."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "and", "or", "not", "this", "that", "it", "its",
})


def extract_keywords(command_name: str, description: str) -> list[str]:
    """Extract searchable keywords from command name and description."""
    keywords: set[str] = set()
    for part in command_name.split():
        keywords.add(part.lower())
        if "-" in part:
            keywords.update(part.lower().split("-"))
    if description:
        for word in re.findall(r"\w+", description.lower()):
            if len(word) > 2 and word not in _STOP_WORDS:
                keywords.add(word)
    return sorted(keywords)


def make_entity_id(entity_type: str, name: str, version: str = "") -> str:
    """Generate a stable, deterministic entity ID.

    The ID is a short hash of the entity type + name + version.
    Same inputs always produce the same ID, regardless of when
    indexing happens.
    """
    key = f"{entity_type}:{name}:{version}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class ArgumentType(Enum):
    POSITIONAL = "positional"
    OPTIONAL = "optional"


@dataclass
class Argument:
    name: str
    description: str = ""
    required: bool = False
    arg_type: ArgumentType = ArgumentType.POSITIONAL
    value_type: str | None = None
    default: str | None = None
    choices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "arg_type": self.arg_type.value,
            "value_type": self.value_type,
            "default": self.default,
            "choices": self.choices,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Argument:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            required=data.get("required", False),
            arg_type=ArgumentType(data.get("arg_type", "positional")),
            value_type=data.get("value_type"),
            default=data.get("default"),
            choices=data.get("choices", []),
        )


@dataclass
class Flag:
    long_form: str | None = None
    short_form: str | None = None
    description: str = ""
    takes_value: bool = False
    value_name: str | None = None
    default: str | None = None
    choices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "long_form": self.long_form,
            "short_form": self.short_form,
            "description": self.description,
            "takes_value": self.takes_value,
            "value_name": self.value_name,
            "default": self.default,
            "choices": self.choices,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Flag:
        return cls(
            long_form=data.get("long_form"),
            short_form=data.get("short_form"),
            description=data.get("description", ""),
            takes_value=data.get("takes_value", False),
            value_name=data.get("value_name"),
            default=data.get("default"),
            choices=data.get("choices", []),
        )


@dataclass
class Command:
    name: str
    binary: str
    parts: list[str]
    description: str = ""
    usage: str | None = None
    synopsis: str | None = None
    arguments: list[Argument] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    subcommands: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    notes: str | None = None
    raw_help: str = ""
    discovery_path: str = ""
    keywords: list[str] = field(default_factory=list)
    deprecated: bool = False

    @property
    def entity_id(self) -> str:
        return make_entity_id("command", self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "binary": self.binary,
            "parts": self.parts,
            "description": self.description,
            "usage": self.usage,
            "synopsis": self.synopsis,
            "arguments": [a.to_dict() for a in self.arguments],
            "flags": [f.to_dict() for f in self.flags],
            "subcommands": self.subcommands,
            "aliases": self.aliases,
            "examples": self.examples,
            "notes": self.notes,
            "raw_help": self.raw_help,
            "discovery_path": self.discovery_path,
            "keywords": self.keywords,
            "deprecated": self.deprecated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Command:
        return cls(
            name=data["name"],
            binary=data["binary"],
            parts=data["parts"],
            description=data.get("description", ""),
            usage=data.get("usage"),
            synopsis=data.get("synopsis"),
            arguments=[Argument.from_dict(a) for a in data.get("arguments", [])],
            flags=[Flag.from_dict(f) for f in data.get("flags", [])],
            subcommands=data.get("subcommands", []),
            aliases=data.get("aliases", []),
            examples=data.get("examples", []),
            notes=data.get("notes"),
            raw_help=data.get("raw_help", ""),
            discovery_path=data.get("discovery_path", ""),
            keywords=data.get("keywords", []),
            deprecated=data.get("deprecated", False),
        )


@dataclass
class CephVersion:
    major: int
    minor: int
    patch: int
    release_name: str
    full_string: str

    def label(self) -> str:
        return f"ceph-{self.major}.{self.minor}.{self.patch}-{self.release_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "release_name": self.release_name,
            "full_string": self.full_string,
            "label": self.label(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CephVersion:
        return cls(
            major=data["major"],
            minor=data["minor"],
            patch=data["patch"],
            release_name=data["release_name"],
            full_string=data["full_string"],
        )


@dataclass
class ParseResult:
    """Intermediate result from a parser — what was extracted from help output."""

    description: str = ""
    usage: str | None = None
    synopsis: str | None = None
    arguments: list[Argument] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    subcommand_names: list[str] = field(default_factory=list)
    subcommand_descriptions: dict[str, str] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass
class ConfigOption:
    """A Ceph configuration parameter."""

    name: str
    type: str = ""
    level: str = ""
    default: str = ""
    desc: str = ""
    long_desc: str = ""
    can_update_at_runtime: bool = False
    services: list[str] = field(default_factory=list)
    min: str = ""
    max: str = ""
    enum_allowed: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    daemon_defaults: dict[str, str] = field(default_factory=dict)

    @property
    def entity_id(self) -> str:
        return make_entity_id("config", self.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "type": self.type,
            "level": self.level,
            "default": self.default,
            "desc": self.desc,
            "long_desc": self.long_desc,
            "can_update_at_runtime": self.can_update_at_runtime,
            "services": self.services,
            "min": self.min,
            "max": self.max,
            "enum_allowed": self.enum_allowed,
            "tags": self.tags,
            "flags": self.flags,
            "daemon_defaults": self.daemon_defaults,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigOption:
        return cls(
            name=data["name"],
            type=data.get("type", ""),
            level=data.get("level", ""),
            default=data.get("default", ""),
            desc=data.get("desc", ""),
            long_desc=data.get("long_desc", ""),
            can_update_at_runtime=data.get("can_update_at_runtime", False),
            services=data.get("services", []),
            min=data.get("min", ""),
            max=data.get("max", ""),
            enum_allowed=data.get("enum_allowed", []),
            tags=data.get("tags", []),
            flags=data.get("flags", []),
            daemon_defaults=data.get("daemon_defaults", {}),
        )


@dataclass
class KnowledgeBase:
    version: CephVersion
    commands: dict[str, Command] = field(default_factory=dict)
    configs: dict[str, ConfigOption] = field(default_factory=dict)
    generated_at: str = ""
    generator_version: str = ""
    binaries_discovered: list[str] = field(default_factory=list)
    binary_versions: dict[str, str] = field(default_factory=dict)

    @property
    def total_commands(self) -> int:
        return len(self.commands)

    @property
    def total_binaries(self) -> int:
        return len(self.binaries_discovered)

    @property
    def total_configs(self) -> int:
        return len(self.configs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version.to_dict(),
            "commands": {name: cmd.to_dict() for name, cmd in self.commands.items()},
            "configs": {name: cfg.to_dict() for name, cfg in self.configs.items()},
            "generated_at": self.generated_at,
            "generator_version": self.generator_version,
            "binaries_discovered": self.binaries_discovered,
            "binary_versions": self.binary_versions,
            "total_commands": self.total_commands,
            "total_configs": self.total_configs,
            "total_binaries": self.total_binaries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeBase:
        kb = cls(
            version=CephVersion.from_dict(data["version"]),
            generated_at=data.get("generated_at", ""),
            generator_version=data.get("generator_version", ""),
            binaries_discovered=data.get("binaries_discovered", []),
            binary_versions=data.get("binary_versions", {}),
        )
        for name, cmd_data in data.get("commands", {}).items():
            kb.commands[name] = Command.from_dict(cmd_data)
        for name, cfg_data in data.get("configs", {}).items():
            kb.configs[name] = ConfigOption.from_dict(cfg_data)
        return kb
