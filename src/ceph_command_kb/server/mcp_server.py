"""MCP server for Ceph command verification and lookup.

Exposes tools that allow Cursor to verify commands, search for flags,
look up help text, and more — all backed by a pre-generated knowledge base.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

logger = logging.getLogger(__name__)

CEPH_ICON = Icon(
    src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0OCA0OCIgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQ4Ij48Y2lyY2xlIGN4PSIyNCIgY3k9IjI0IiByPSIyMiIgZmlsbD0iI0VGNTAzQSIvPjx0ZXh0IHg9IjI0IiB5PSIzMiIgZm9udC1mYW1pbHk9IkFyaWFsLHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMjAiIGZvbnQtd2VpZ2h0PSJib2xkIiBmaWxsPSJ3aGl0ZSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+QzwvdGV4dD48L3N2Zz4=",
    mimeType="image/svg+xml",
)

mcp = FastMCP(
    "Ceph Command Knowledge Base",
    instructions=(
        "Multi-version Ceph CLI knowledge base covering Ceph Squid 19.x (IBM Storage Ceph 8.x) "
        "and Ceph Tentacle 20.x (IBM Storage Ceph 9.x). "
        "Use this MCP when you need to: verify Ceph commands before generating them, "
        "check if flags or arguments are valid, look up config parameter defaults and constraints, "
        "search for commands by keyword, or review test scripts for correctness. "
        "Tools accept an optional 'version' parameter to target a specific Ceph release "
        "(e.g. 'squid', 'tentacle', '19', '20', '8.1', '9.1'). "
        "Always verify commands against this KB before writing Ceph automation or tests."
    ),
    icons=[CEPH_ICON],
)


class VersionData:
    """Holds loaded data for a single knowledge base version."""

    __slots__ = ("label", "kb_data", "search_index", "config_data", "commands_map", "kb_dir")

    def __init__(self, label: str, kb_data: dict, search_index: dict,
                 config_data: dict[str, dict], commands_map: dict[str, dict],
                 kb_dir: Path):
        self.label = label
        self.kb_data = kb_data
        self.search_index = search_index
        self.config_data = config_data
        self.commands_map = commands_map
        self.kb_dir = kb_dir


_versions: dict[str, VersionData] = {}
_default_version_label: str | None = None

# IBM Storage Ceph -> upstream Ceph mapping for flexible version resolution
_VERSION_ALIASES: dict[str, str] = {
    "8": "squid", "8.0": "squid", "8.1": "squid",
    "19": "squid", "19.2": "squid",
    "9": "tentacle", "9.0": "tentacle", "9.1": "tentacle",
    "20": "tentacle", "20.2": "tentacle",
}

# Backward-compat globals (point to default version)
_kb_data: dict | None = None
_search_index: dict | None = None
_config_data: dict | None = None
_kb_dir: Path | None = None
_commands_map_cache: dict[str, dict] | None = None


def _load_version(kb_path: Path) -> VersionData:
    """Load a single knowledge base version from disk."""
    commands_path = kb_path / "commands.json"
    index_path = kb_path / "search_index.json"
    configs_path = kb_path / "configs.json"

    if not commands_path.exists():
        raise FileNotFoundError(f"commands.json not found in {kb_path}")

    with open(commands_path) as f:
        kb_data = json.load(f)

    if index_path.exists():
        with open(index_path) as f:
            search_index = json.load(f)
    else:
        search_index = {}

    if configs_path.exists():
        with open(configs_path) as f:
            raw = json.load(f)
        config_data = {cfg["name"]: cfg for cfg in raw.get("configs", [])}
    else:
        config_data = {}

    commands_map = {cmd["name"]: cmd for cmd in kb_data.get("commands", [])}

    version_info = kb_data.get("version", {})
    label = version_info.get("label", kb_path.name)

    logger.info("Loaded version %s: %d commands, %d configs from %s",
                label, len(commands_map), len(config_data), kb_path)

    return VersionData(
        label=label, kb_data=kb_data, search_index=search_index,
        config_data=config_data, commands_map=commands_map, kb_dir=kb_path,
    )


def _load_knowledge_base(kb_path: Path) -> None:
    """Load a knowledge base version (backward-compat entry point for auto_update).

    Also scans sibling version dirs so auto-update picks up new versions.
    """
    global _kb_data, _search_index, _config_data, _kb_dir, _commands_map_cache, _default_version_label

    vd = _load_version(kb_path)
    _versions[vd.label] = vd

    # Also discover sibling version dirs (e.g. new version added via git pull)
    parent = kb_path.parent
    if parent.is_dir():
        for sibling in parent.iterdir():
            if sibling.is_dir() and (sibling / "commands.json").exists():
                sib_label = sibling.name
                if sib_label not in _versions:
                    try:
                        svd = _load_version(sibling)
                        _versions[svd.label] = svd
                    except Exception:
                        pass

    # Set default to latest version
    if _versions:
        _default_version_label = sorted(_versions.keys())[-1]

    # Update backward-compat globals to point at default version
    _set_compat_globals(_default_version_label or vd.label)


def _load_all_versions(knowledge_dir: Path) -> None:
    """Load every version directory found under the knowledge base root."""
    global _default_version_label

    if not knowledge_dir.is_dir():
        return

    version_dirs = sorted(
        (d for d in knowledge_dir.iterdir()
         if d.is_dir() and (d / "commands.json").exists()),
        key=lambda d: d.name,
    )

    for vdir in version_dirs:
        try:
            vd = _load_version(vdir)
            _versions[vd.label] = vd
        except Exception as e:
            logger.warning("Failed to load version from %s: %s", vdir, e)

    if _versions:
        # Default to the latest version (highest major.minor.patch)
        _default_version_label = sorted(_versions.keys())[-1]
        _set_compat_globals(_default_version_label)
        logger.info("Loaded %d versions, default: %s", len(_versions), _default_version_label)


def _set_compat_globals(label: str) -> None:
    """Update backward-compat module globals to point at a specific version."""
    global _kb_data, _search_index, _config_data, _kb_dir, _commands_map_cache
    vd = _versions.get(label)
    if vd:
        _kb_data = vd.kb_data
        _search_index = vd.search_index
        _config_data = vd.config_data
        _kb_dir = vd.kb_dir
        _commands_map_cache = vd.commands_map


def _resolve_version(version: str | None) -> VersionData | None:
    """Resolve a version hint to a loaded VersionData.

    Accepts: full label ('ceph-19.2.1-squid'), release name ('squid'),
    major version ('19'), IBM product version ('8.1'), or None (default).
    """
    if not _versions:
        return None

    if version is None:
        return _versions.get(_default_version_label or "")

    v = version.strip().lower()

    # Exact label match
    for label, vd in _versions.items():
        if v == label.lower():
            return vd

    # Release name match (e.g. 'squid', 'tentacle')
    for label, vd in _versions.items():
        release = vd.kb_data.get("version", {}).get("release_name", "").lower()
        if v == release:
            return vd

    # Alias lookup (IBM product versions, major versions)
    alias_release = _VERSION_ALIASES.get(v)
    if alias_release:
        for label, vd in _versions.items():
            release = vd.kb_data.get("version", {}).get("release_name", "").lower()
            if alias_release == release:
                return vd

    # Substring match on label
    for label, vd in _versions.items():
        if v in label.lower():
            return vd

    return _versions.get(_default_version_label or "")


def _version_notice() -> dict | None:
    """When multiple versions are loaded and no explicit version was specified,
    return a dict with a note about which version was used and alternatives.
    Returns None if only one version is loaded."""
    if len(_versions) <= 1:
        return None

    default_vd = _versions.get(_default_version_label or "")
    if not default_vd:
        return None

    vi = default_vd.kb_data.get("version", {})
    default_release = vi.get("release_name", "")
    default_major = vi.get("major", "")
    default_minor = vi.get("minor", "")

    other_versions = []
    for label, vd in sorted(_versions.items()):
        if label == _default_version_label:
            continue
        ovi = vd.kb_data.get("version", {})
        rel = ovi.get("release_name", "")
        maj = ovi.get("major", "")
        other_versions.append(f"{rel} ({maj}.x) -- use version=\"{rel}\"")

    return {
        "version_note": (
            f"Results shown for Ceph {default_major}.{default_minor} {default_release.title()} (default). "
            f"Other versions available: {', '.join(other_versions)}. "
            f"Specify the \'version\' parameter to query a different version."
        ),
        "version_used": _default_version_label,
    }


def _inject_version_notice(result: dict, version: str | None) -> dict:
    """If no version was explicitly specified and multiple versions exist,
    add a version_note to the result dict."""
    if version is None:
        notice = _version_notice()
        if notice:
            result.update(notice)
    return result


def _get_commands_map(version: str | None = None) -> dict[str, dict]:
    """Return commands keyed by name for fast lookup."""
    vd = _resolve_version(version)
    if vd:
        return vd.commands_map
    if _commands_map_cache is not None:
        return _commands_map_cache
    return {}


def _get_config_data(version: str | None = None) -> dict[str, dict]:
    """Return config data for a specific version."""
    vd = _resolve_version(version)
    if vd:
        return vd.config_data
    return _config_data or {}


def _get_search_index(version: str | None = None) -> dict:
    """Return search index for a specific version."""
    vd = _resolve_version(version)
    if vd:
        return vd.search_index
    return _search_index or {}


def _get_kb_dir(version: str | None = None) -> Path | None:
    """Return KB directory path for a specific version."""
    vd = _resolve_version(version)
    if vd:
        return vd.kb_dir
    return _kb_dir


@mcp.tool()
def find_command(command_name: str, version: str | None = None) -> str:
    """Look up a specific Ceph command by its exact full name.

    Use this when you know the full command name (e.g. 'ceph osd pool create')
    and want its complete metadata including arguments, flags, and usage.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    commands = _get_commands_map(version)
    cmd = commands.get(command_name)

    if cmd is None:
        close = [
            name for name in commands
            if command_name.lower() in name.lower()
        ][:5]
        result: dict[str, Any] = {"found": False, "command": command_name}
        if close:
            result["similar_commands"] = close
        return json.dumps(_inject_version_notice(result, version), indent=2)

    return json.dumps(_inject_version_notice({"found": True, "command": cmd}, version), indent=2)


@mcp.tool()
def verify_command(
    command: str,
    flags: list[str] | None = None,
    arguments: list[str] | None = None,
    version: str | None = None,
) -> str:
    """Verify that a Ceph command, its flags, and arguments are valid.

    Use this BEFORE generating any Ceph CLI command in automation or tests.
    Returns explicit verification status for the command and each flag/argument.
    Never guesses — returns NOT_VERIFIED if it cannot confirm.

    Args:
        command: The full command to verify, e.g. 'ceph osd pool create'
        flags: Optional list of flags to verify, e.g. ['--size', '--pg-num']
        arguments: Optional list of argument names to verify, e.g. ['pool', 'pg_num']
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    commands = _get_commands_map(version)
    cmd = commands.get(command)

    result: dict = {
        "command": command,
        "command_verified": cmd is not None,
    }

    if cmd is None:
        result["status"] = "NOT_VERIFIED"
        result["reason"] = f"Command '{command}' not found in knowledge base"
        close = [
            name for name in commands
            if command.lower() in name.lower()
        ][:5]
        if close:
            result["similar_commands"] = close
        return json.dumps(_inject_version_notice(result, version), indent=2)

    if flags:
        flag_results = {}
        known_flags = set()
        for f in cmd.get("flags", []):
            if f.get("short_form"):
                known_flags.add(f["short_form"])
            if f.get("long_form"):
                known_flags.add(f["long_form"])

        for flag in flags:
            flag_results[flag] = flag in known_flags

        result["flags_verified"] = flag_results
        all_flags_ok = all(flag_results.values())
    else:
        all_flags_ok = True

    if arguments:
        arg_results = {}
        known_args = {a["name"] for a in cmd.get("arguments", [])}
        for arg in arguments:
            arg_results[arg] = arg in known_args
        result["arguments_verified"] = arg_results
        all_args_ok = all(arg_results.values())
    else:
        all_args_ok = True

    if all_flags_ok and all_args_ok:
        result["status"] = "VERIFIED"
    else:
        result["status"] = "PARTIALLY_VERIFIED"
        result["reason"] = "Some flags or arguments could not be verified"

    result["usage"] = cmd.get("usage")
    result["description"] = cmd.get("description")

    return json.dumps(_inject_version_notice(result, version), indent=2)


@mcp.tool()
def search_commands(query: str, limit: int = 20, version: str | None = None) -> str:
    """Search for Ceph commands by name, description, or keyword.

    Use this when you're looking for a command but don't know the exact name.
    Searches across command names, descriptions, and keywords.

    Args:
        query: Search term (partial command name, keyword, or description fragment)
        limit: Maximum number of results to return (default 20)
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    commands = _get_commands_map(version)
    query_lower = query.lower()
    query_words = query_lower.split()

    scored: list[tuple[float, str, dict]] = []

    for name, cmd in commands.items():
        score = 0.0
        name_lower = name.lower()

        if query_lower == name_lower:
            score = 1000.0
        elif query_lower in name_lower:
            score = 80.0
        else:
            desc = (cmd.get("description") or "").lower()
            keywords = cmd.get("keywords", [])
            keyword_str = " ".join(keywords).lower()

            for word in query_words:
                if word in name_lower:
                    score += 30.0
                if word in desc:
                    score += 20.0
                if word in keyword_str:
                    score += 10.0

        if score > 0:
            scored.append((score, name, cmd))

    scored.sort(key=lambda x: (-x[0], x[1]))

    results = []
    for score, name, cmd in scored[:limit]:
        entry: dict[str, Any] = {
            "name": name,
            "binary": cmd.get("binary"),
            "description": cmd.get("description"),
            "usage": cmd.get("usage"),
            "has_subcommands": bool(cmd.get("subcommands")),
        }
        args = cmd.get("arguments", [])
        if args:
            entry["arguments"] = [
                {"name": a["name"], "required": a.get("required", False)}
                for a in args
            ]
        flags = cmd.get("flags", [])
        if flags:
            entry["flags"] = [
                f.get("long_form") or f.get("short_form")
                for f in flags
            ]
        entry["synopsis"] = cmd.get("synopsis")
        results.append(entry)

    return json.dumps(_inject_version_notice({"query": query, "total_results": len(results), "results": results}, version), indent=2)


@mcp.tool()
def list_subcommands(command_prefix: str, version: str | None = None) -> str:
    """List all subcommands under a given command prefix.

    Use this to explore the command tree, e.g. 'ceph osd' to see all osd subcommands.

    Args:
        command_prefix: The command prefix, e.g. 'ceph osd' or 'rbd'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    commands = _get_commands_map(version)
    cmd = commands.get(command_prefix)

    if cmd and cmd.get("subcommands"):
        subs = []
        for sub_name in sorted(cmd["subcommands"]):
            full_name = f"{command_prefix} {sub_name}"
            sub_cmd = commands.get(full_name, {})
            subs.append({
                "name": full_name,
                "description": sub_cmd.get("description", ""),
            })
        return json.dumps(_inject_version_notice({
            "command": command_prefix,
            "subcommands": subs,
        }, version), indent=2)

    prefix_lower = command_prefix.lower()
    children = []
    for name, c in sorted(commands.items()):
        if name.lower().startswith(prefix_lower + " "):
            children.append({
                "name": name,
                "description": c.get("description", ""),
            })

    return json.dumps(_inject_version_notice({
        "command": command_prefix,
        "subcommands": children,
    }, version), indent=2)


@mcp.tool()
def search_flag(flag: str, version: str | None = None) -> str:
    """Find which commands accept a specific flag.

    Use this to check if a flag is valid and which commands support it.

    Args:
        flag: The flag to search for, e.g. '--pool' or '-p'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    si = _get_search_index(version)
    if si and "by_flag" in si:
        commands = si["by_flag"].get(flag, [])
        return json.dumps(_inject_version_notice({
            "flag": flag,
            "found": bool(commands),
            "commands": commands,
        }, version), indent=2)

    commands_map = _get_commands_map(version)
    matching = []
    for name, cmd in commands_map.items():
        for f in cmd.get("flags", []):
            if f.get("short_form") == flag or f.get("long_form") == flag:
                matching.append(name)
                break

    return json.dumps(_inject_version_notice({
        "flag": flag,
        "found": bool(matching),
        "commands": sorted(matching),
    }, version), indent=2)


@mcp.tool()
def search_argument(argument_name: str, version: str | None = None) -> str:
    """Find which commands accept a specific argument.

    Use this to check if an argument name is valid and which commands use it.

    Args:
        argument_name: The argument name, e.g. 'pool' or 'image'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    si = _get_search_index(version)
    if si and "by_argument" in si:
        commands = si["by_argument"].get(argument_name, [])
        return json.dumps(_inject_version_notice({
            "argument": argument_name,
            "found": bool(commands),
            "commands": commands,
        }, version), indent=2)

    commands_map = _get_commands_map(version)
    matching = []
    for name, cmd in commands_map.items():
        for a in cmd.get("arguments", []):
            if a.get("name") == argument_name:
                matching.append(name)
                break

    return json.dumps(_inject_version_notice({
        "argument": argument_name,
        "found": bool(matching),
        "commands": sorted(matching),
    }, version), indent=2)


@mcp.tool()
def get_help(command_name: str, version: str | None = None) -> str:
    """Get the parsed help information for a specific command.

    Returns the full structured metadata including usage, description,
    arguments, flags, and examples.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    commands = _get_commands_map(version)
    cmd = commands.get(command_name)

    if cmd is None:
        return json.dumps(_inject_version_notice({"found": False, "command": command_name}, version), indent=2)

    return json.dumps(_inject_version_notice({
        "found": True,
        "name": cmd.get("name"),
        "binary": cmd.get("binary"),
        "description": cmd.get("description"),
        "usage": cmd.get("usage"),
        "synopsis": cmd.get("synopsis"),
        "arguments": cmd.get("arguments", []),
        "flags": cmd.get("flags", []),
        "subcommands": cmd.get("subcommands", []),
        "examples": cmd.get("examples", []),
        "notes": cmd.get("notes"),
    }, version), indent=2)


@mcp.tool()
def get_raw_help(command_name: str, version: str | None = None) -> str:
    """Get the original raw help text output for a command.

    Use this when the parsed data is insufficient and you need the
    exact text that the command's -h flag produced.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    kb_dir = _get_kb_dir(version)
    if kb_dir:
        filename = command_name.replace(" ", "-") + ".txt"
        raw_path = (kb_dir / "raw_help" / filename).resolve()
        if raw_path.is_relative_to((kb_dir / "raw_help").resolve()) and raw_path.exists():
            return raw_path.read_text(encoding="utf-8")

    commands = _get_commands_map(version)
    cmd = commands.get(command_name)
    if cmd and cmd.get("raw_help"):
        return cmd["raw_help"]

    return json.dumps({"found": False, "command": command_name})


@mcp.tool()
def get_examples(command_name: str, version: str | None = None) -> str:
    """Get usage examples for a specific command.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    commands = _get_commands_map(version)
    cmd = commands.get(command_name)

    if cmd is None:
        return json.dumps(_inject_version_notice({"found": False, "command": command_name}, version), indent=2)

    return json.dumps(_inject_version_notice({
        "found": True,
        "command": command_name,
        "examples": cmd.get("examples", []),
        "usage": cmd.get("usage"),
    }, version), indent=2)


@mcp.tool()
def list_versions() -> str:
    """List all available knowledge base versions.

    Use this to check which Ceph versions have been indexed.
    Returns version labels, command/config counts, and the default version.
    """
    versions = []
    for label, vd in sorted(_versions.items()):
        vi = vd.kb_data.get("version", {})
        versions.append({
            "label": label,
            "release_name": vi.get("release_name", ""),
            "full_string": vi.get("full_string", ""),
            "major": vi.get("major"),
            "minor": vi.get("minor"),
            "patch": vi.get("patch"),
            "total_commands": len(vd.commands_map),
            "total_configs": len(vd.config_data),
            "is_default": label == _default_version_label,
        })

    return json.dumps({
        "total_versions": len(versions),
        "default_version": _default_version_label,
        "versions": versions,
    }, indent=2)


@mcp.tool()
def find_binary(binary_name: str, version: str | None = None) -> str:
    """List all commands for a specific binary.

    Use this to see everything available under a binary like 'rbd' or 'rados'.

    Args:
        binary_name: The binary name, e.g. 'rbd', 'rados', 'cephadm'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    si = _get_search_index(version)
    if si and "by_binary" in si:
        commands = si["by_binary"].get(binary_name, [])
        return json.dumps(_inject_version_notice({
            "binary": binary_name,
            "found": bool(commands),
            "total_commands": len(commands),
            "commands": commands,
        }, version), indent=2)

    commands_map = _get_commands_map(version)
    matching = sorted(
        name for name, cmd in commands_map.items()
        if cmd.get("binary") == binary_name
    )

    return json.dumps(_inject_version_notice({
        "binary": binary_name,
        "found": bool(matching),
        "total_commands": len(matching),
        "commands": matching,
    }, version), indent=2)


@mcp.tool()
def search_keyword(keyword: str, version: str | None = None) -> str:
    """Search commands by keyword across all metadata.

    Searches through command names, descriptions, arguments, flags,
    and extracted keywords.

    Args:
        keyword: The keyword to search for, e.g. 'pool', 'snapshot', 'crush'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    si = _get_search_index(version)
    if si and "by_keyword" in si:
        commands = si["by_keyword"].get(keyword.lower(), [])
        if commands:
            return json.dumps(_inject_version_notice({
                "keyword": keyword,
                "found": True,
                "commands": commands,
            }, version), indent=2)

    return search_commands(keyword, version=version)


# ── Config verification tools ──────────────────────────────────────────


@mcp.tool()
def verify_config(name: str, version: str | None = None) -> str:
    """Verify that a Ceph configuration parameter exists and is valid.

    Use this BEFORE setting any Ceph config in automation or tests.
    Returns the parameter's type, default value, description, and
    which daemons it applies to.

    Args:
        name: The config parameter name, e.g. 'osd_pool_default_size'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    config_data = _get_config_data(version)
    if not config_data:
        return json.dumps({"status": "NO_CONFIG_DATA", "reason": "Config knowledge base not loaded"})

    config_name = name
    cfg = config_data.get(config_name)
    if cfg is None:
        close = [
            key for key in config_data
            if config_name.lower() in key.lower()
        ][:10]
        result = {"config": config_name, "verified": False, "status": "NOT_FOUND"}
        if close:
            result["similar_configs"] = close
        return json.dumps(_inject_version_notice(result, version), indent=2)

    return json.dumps(_inject_version_notice({
        "config": config_name,
        "verified": True,
        "status": "VERIFIED",
        "type": cfg.get("type"),
        "level": cfg.get("level"),
        "default": cfg.get("default"),
        "desc": cfg.get("desc"),
        "long_desc": cfg.get("long_desc"),
        "can_update_at_runtime": cfg.get("can_update_at_runtime"),
        "services": cfg.get("services"),
        "min": cfg.get("min"),
        "max": cfg.get("max"),
        "enum_allowed": cfg.get("enum_allowed"),
        "daemon_defaults": cfg.get("daemon_defaults"),
    }, version), indent=2)


@mcp.tool()
def search_config(query: str, limit: int = 20, version: str | None = None) -> str:
    """Search for Ceph config parameters by name, description, or keyword.

    Use this when looking for a config option but not sure of the exact name.
    Pass the search term as the 'query' parameter (not 'keyword').

    Args:
        query: Search term (keyword, partial name, or description fragment), e.g. 'pool size', 'osd recovery', 'fast_ec'
        limit: Max results (default 20)
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    config_data = _get_config_data(version)
    if not config_data:
        return json.dumps({"query": query, "total_results": 0, "results": []})

    query_lower = query.lower()
    query_words = query_lower.split()

    scored: list[tuple[float, str, dict]] = []

    for name, cfg in config_data.items():
        score = 0.0
        name_lower = name.lower()

        if query_lower == name_lower:
            score = 1000.0
        elif query_lower in name_lower:
            score = 80.0
        else:
            desc = (cfg.get("desc") or "").lower()
            for word in query_words:
                if word in name_lower:
                    score += 30.0
                if word in desc:
                    score += 20.0

        if score > 0:
            scored.append((score, name, cfg))

    scored.sort(key=lambda x: (-x[0], x[1]))

    results = []
    for _, name, cfg in scored[:limit]:
        results.append({
            "name": name,
            "type": cfg.get("type"),
            "default": cfg.get("default"),
            "desc": cfg.get("desc"),
            "can_update_at_runtime": cfg.get("can_update_at_runtime"),
        })

    return json.dumps(_inject_version_notice({"query": query, "total_results": len(results), "results": results}, version), indent=2)


@mcp.tool()
def get_config_help(name: str, version: str | None = None) -> str:
    """Get full metadata for a Ceph config parameter.

    Returns type, default, description, constraints, daemon-specific
    defaults, and whether it can be changed at runtime.

    Args:
        name: The config parameter name, e.g. 'osd_pool_default_size'
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    config_data = _get_config_data(version)
    if not config_data:
        return json.dumps({"found": False, "config": name})

    cfg = config_data.get(name)
    if cfg is None:
        return json.dumps({"found": False, "config": name})

    return json.dumps(_inject_version_notice({"found": True, **cfg}, version), indent=2)


@mcp.tool()
def list_configs_by_section(section: str, limit: int = 50, version: str | None = None) -> str:
    """List all config parameters that belong to a section/prefix.

    Ceph config names are prefixed by subsystem, e.g. 'osd_', 'mon_',
    'rgw_', 'mds_'. Use this to explore all options for a subsystem.

    Args:
        section: The config name prefix, e.g. 'osd', 'mon', 'rgw', 'auth'
        limit: Max results (default 50)
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    config_data = _get_config_data(version)
    if not config_data:
        return json.dumps({"section": section, "total": 0, "configs": []})

    prefix = section.lower().rstrip("_") + "_"
    matching = []

    for name, cfg in sorted(config_data.items()):
        if name.lower().startswith(prefix):
            matching.append({
                "name": name,
                "type": cfg.get("type"),
                "default": cfg.get("default"),
                "desc": cfg.get("desc"),
            })

    return json.dumps(_inject_version_notice({
        "section": section,
        "total": len(matching),
        "configs": matching[:limit],
    }, version), indent=2)


# ── Test validation tools ──────────────────────────────────────────────


@mcp.tool()
def validate_script(script_content: str, script_type: str = "auto", version: str | None = None) -> str:
    """Quick validation of a test script against the Ceph command knowledge base.

    Extracts all Ceph commands from the script and verifies each one exists
    in the knowledge base. Reports unknown commands, invalid flags, and
    basic issues.

    Use this for a fast check before running tests. For a full engineering
    review, use review_test() instead.

    Args:
        script_content: The full text content of the test script.
        script_type: Script language — "python", "shell", "yaml", or "auto" (detect).
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    from ceph_command_kb.validation.validator import Validator

    commands = _get_commands_map(version)
    if not commands:
        return json.dumps({"error": "Knowledge base not loaded"})

    validator = Validator(commands)
    report = validator.validate(script_content, script_type=script_type)

    result = {
        "total_commands": report.total_commands,
        "verified": report.verified_commands,
        "unverified": report.unverified_commands,
        "errors": report.error_count,
        "warnings": report.warning_count,
        "findings": [f.to_dict() for f in report.findings if f.severity in ("error", "warning")],
    }
    return json.dumps(_inject_version_notice(result, version), indent=2)


@mcp.tool()
def review_test(script_content: str, script_type: str = "auto", version: str | None = None) -> str:
    """Full deterministic review of a Ceph test script.

    Runs all validation phases:
    1. Command verification — every command checked against the KB
    2. Flag/argument validation — unknown flags detected
    3. Cleanup validation — resources created without cleanup
    4. Risk analysis — destructive commands and force flags
    5. Duplicate detection — repeated identical commands

    Returns a comprehensive structured report. For contextual analysis
    (workflow ordering, QE practices, prerequisites), use the report
    as input to your own reasoning.

    Args:
        script_content: The full text content of the test script.
        script_type: Script language — "python", "shell", "yaml", or "auto" (detect).
        version: Ceph version to query. Accepts 'squid', 'tentacle', '8.1', '9.1', '19', '20'. If omitted, uses default (latest) and the response notes which version was used.
    """
    from ceph_command_kb.validation.validator import Validator

    commands = _get_commands_map(version)
    if not commands:
        return json.dumps({"error": "Knowledge base not loaded"})

    validator = Validator(commands)
    report = validator.validate(script_content, script_type=script_type)

    return json.dumps(_inject_version_notice(report.to_dict(), version), indent=2)


# ── Platform contract tools ────────────────────────────────────────────

SCHEMA_VERSION = "1.0"


@mcp.tool()
def capabilities() -> str:
    """Return machine-readable capabilities of this knowledge base.

    Used by orchestrators and agents for automatic capability discovery.
    Every MCP in the Engineering Intelligence Platform exposes this tool.
    """
    version_summaries = []
    total_cmds = 0
    total_cfgs = 0
    for label, vd in sorted(_versions.items()):
        n_cmds = len(vd.commands_map)
        n_cfgs = len(vd.config_data)
        total_cmds += n_cmds
        total_cfgs += n_cfgs
        version_summaries.append({
            "label": label,
            "commands": n_cmds,
            "configs": n_cfgs,
        })

    return json.dumps({
        "name": "Ceph Command Knowledge Base",
        "description": "Multi-version Ceph CLI commands, config parameters, and test validation",
        "schema_version": SCHEMA_VERSION,
        "entity_types": ["command", "config"],
        "operations": [
            "verify_command", "find_command", "search_commands",
            "list_subcommands", "search_flag", "search_argument",
            "get_help", "get_raw_help", "get_examples",
            "find_binary", "search_keyword",
            "verify_config", "search_config", "get_config_help",
            "list_configs_by_section",
            "validate_script", "review_test",
            "list_versions", "capabilities", "health",
        ],
        "supported_versions": [v["label"] for v in version_summaries],
        "default_version": _default_version_label,
        "entity_counts": {
            "commands": total_cmds,
            "configs": total_cfgs,
        },
        "versions": version_summaries,
    }, indent=2)


@mcp.tool()
def health() -> str:
    """Return operational health status of this knowledge base.

    Includes whether the index is loaded, entity counts, and readiness.
    Every MCP in the Engineering Intelligence Platform exposes this tool.
    """
    total_cmds = sum(len(vd.commands_map) for vd in _versions.values())
    total_cfgs = sum(len(vd.config_data) for vd in _versions.values())
    kb_loaded = bool(_versions) and total_cmds > 0

    version_health = []
    for label, vd in sorted(_versions.items()):
        version_health.append({
            "label": label,
            "commands": len(vd.commands_map),
            "configs": len(vd.config_data),
            "search_ready": bool(vd.search_index),
        })

    return json.dumps({
        "status": "ok" if kb_loaded else "degraded",
        "kb_loaded": kb_loaded,
        "total_versions": len(_versions),
        "default_version": _default_version_label,
        "total_commands": total_cmds,
        "total_configs": total_cfgs,
        "schema_version": SCHEMA_VERSION,
        "versions": version_health,
    }, indent=2)


SUPPORTED_TRANSPORTS = ("stdio", "sse", "streamable-http")


def _silence_stderr_logging() -> None:
    """Suppress all logging to stderr for stdio transport.

    Cursor classifies any stderr output as [error] in the MCP output panel,
    making the server appear broken even when healthy.
    """
    logging.disable(logging.CRITICAL)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.root.addHandler(logging.NullHandler())


def init_kb(kb_path: str | Path | None = None) -> None:
    """Load the knowledge base. Called before starting any transport.

    If kb_path is a specific version directory, loads just that version.
    If kb_path is None, discovers and loads ALL versions under the knowledge/ root.
    """
    if kb_path is not None:
        _load_knowledge_base(Path(kb_path))
        return

    knowledge_root = _find_knowledge_root()
    if knowledge_root is not None:
        _load_all_versions(knowledge_root)
    else:
        logger.warning(
            "No knowledge base found. Server will start but tools will return empty results. "
            "Run generate_reference.py first to create a knowledge base."
        )


def run_server(
    kb_path: str | Path | None = None,
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8080,
) -> None:
    """Start the MCP server with the specified transport.

    Args:
        kb_path: Path to the knowledge base version directory.
        transport: Transport mode — "stdio", "sse", or "streamable-http".
        host: Bind address for HTTP transports (default: 0.0.0.0).
        port: Port for HTTP transports (default: 8080).
    """
    if transport not in SUPPORTED_TRANSPORTS:
        raise ValueError(
            f"Unknown transport {transport!r}. "
            f"Supported: {SUPPORTED_TRANSPORTS}"
        )

    if transport == "stdio":
        _silence_stderr_logging()

    init_kb(kb_path)

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        logger.info("Starting MCP server (SSE transport) on %s:%d", host, port)
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")
    elif transport == "streamable-http":
        logger.info("Starting MCP server (Streamable HTTP) on %s:%d", host, port)
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")


def _find_knowledge_root() -> Path | None:
    """Find the knowledge base root directory containing version subdirectories.

    Searches CWD first, then falls back to the project root
    (relative to this source file) so the server works regardless
    of which directory it's launched from.
    """
    candidates = [
        Path("knowledge"),
        Path(__file__).resolve().parent.parent.parent.parent / "knowledge",
    ]
    for knowledge_dir in candidates:
        if not knowledge_dir.is_dir():
            continue
        has_versions = any(
            d.is_dir() and (d / "commands.json").exists()
            for d in knowledge_dir.iterdir()
        )
        if has_versions:
            return knowledge_dir
    return None


def _find_latest_kb() -> Path | None:
    """Find the most recently generated knowledge base (single version).

    Kept for backward compat with auto_update and CLI --kb-path.
    """
    knowledge_root = _find_knowledge_root()
    if knowledge_root is None:
        return None
    version_dirs = sorted(
        (d for d in knowledge_root.iterdir()
         if d.is_dir() and (d / "commands.json").exists()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return version_dirs[0] if version_dirs else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ceph Command KB MCP Server")
    parser.add_argument(
        "--kb-path",
        type=Path,
        default=None,
        help="Path to knowledge base version directory",
    )
    parser.add_argument(
        "--transport", "-t",
        choices=SUPPORTED_TRANSPORTS,
        default="stdio",
        help="Transport mode: stdio (Cursor), sse (HTTP/SSE for MCP clients), "
             "streamable-http (HTTP for MCP clients). Default: stdio",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for HTTP transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Port for HTTP transports (default: 8080)",
    )
    parser.add_argument(
        "--auto-update",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Auto-pull latest changes from git on startup (default: enabled)",
    )
    parser.add_argument(
        "--update-interval",
        type=float,
        default=1,
        metavar="HOURS",
        help="Hours between periodic update checks (default: 1, 0=disable periodic)",
    )
    args = parser.parse_args()

    if args.auto_update:
        resolved_kb = args.kb_path or _find_latest_kb()
        if resolved_kb is not None:
            from ceph_command_kb.server.auto_update import start_auto_update
            start_auto_update(
                Path(resolved_kb),
                _load_knowledge_base,
                update_interval_hours=args.update_interval,
            )

    run_server(
        kb_path=args.kb_path,
        transport=args.transport,
        host=args.host,
        port=args.port,
    )
