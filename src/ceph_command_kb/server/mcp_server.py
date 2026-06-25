"""MCP server for Ceph command verification and lookup.

Exposes tools that allow Cursor to verify commands, search for flags,
look up help text, and more — all backed by a pre-generated knowledge base.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Ceph Command Knowledge Base",
    instructions=(
        "Authoritative knowledge base of Ceph CLI commands. "
        "Use this to verify commands, flags, arguments, and syntax "
        "before generating Ceph automation or tests."
    ),
)

_kb_data: dict | None = None
_search_index: dict | None = None
_config_data: dict | None = None
_kb_dir: Path | None = None


def _load_knowledge_base(kb_path: Path) -> None:
    """Load the knowledge base, search index, and configs from disk."""
    global _kb_data, _search_index, _config_data, _kb_dir

    commands_path = kb_path / "commands.json"
    index_path = kb_path / "search_index.json"
    configs_path = kb_path / "configs.json"

    if not commands_path.exists():
        raise FileNotFoundError(f"commands.json not found in {kb_path}")

    with open(commands_path) as f:
        _kb_data = json.load(f)

    if index_path.exists():
        with open(index_path) as f:
            _search_index = json.load(f)
    else:
        _search_index = {}

    if configs_path.exists():
        with open(configs_path) as f:
            raw = json.load(f)
        _config_data = {cfg["name"]: cfg for cfg in raw.get("configs", [])}
        logger.info("Loaded %d config options", len(_config_data))
    else:
        _config_data = {}

    _kb_dir = kb_path
    total = len(_kb_data.get("commands", []))
    logger.info("Loaded knowledge base: %d commands from %s", total, kb_path)


def _get_commands_map() -> dict[str, dict]:
    """Return commands keyed by name for fast lookup."""
    if _kb_data is None:
        return {}
    if "_commands_map" not in _kb_data:
        _kb_data["_commands_map"] = {
            cmd["name"]: cmd for cmd in _kb_data.get("commands", [])
        }
    return _kb_data["_commands_map"]


@mcp.tool()
def find_command(command_name: str) -> str:
    """Look up a specific Ceph command by its exact full name.

    Use this when you know the full command name (e.g. 'ceph osd pool create')
    and want its complete metadata including arguments, flags, and usage.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
    """
    commands = _get_commands_map()
    cmd = commands.get(command_name)

    if cmd is None:
        close = [
            name for name in commands
            if command_name.lower() in name.lower()
        ][:5]
        result = {"found": False, "command": command_name}
        if close:
            result["similar_commands"] = close
        return json.dumps(result, indent=2)

    return json.dumps({"found": True, "command": cmd}, indent=2)


@mcp.tool()
def verify_command(
    command: str,
    flags: list[str] | None = None,
    arguments: list[str] | None = None,
) -> str:
    """Verify that a Ceph command, its flags, and arguments are valid.

    Use this BEFORE generating any Ceph CLI command in automation or tests.
    Returns explicit verification status for the command and each flag/argument.
    Never guesses — returns NOT_VERIFIED if it cannot confirm.

    Args:
        command: The full command to verify, e.g. 'ceph osd pool create'
        flags: Optional list of flags to verify, e.g. ['--size', '--pg-num']
        arguments: Optional list of argument names to verify, e.g. ['pool', 'pg_num']
    """
    commands = _get_commands_map()
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
        return json.dumps(result, indent=2)

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

    if cmd is not None and all_flags_ok and all_args_ok:
        result["status"] = "VERIFIED"
    else:
        result["status"] = "PARTIALLY_VERIFIED"
        result["reason"] = "Some flags or arguments could not be verified"

    result["usage"] = cmd.get("usage")
    result["description"] = cmd.get("description")

    return json.dumps(result, indent=2)


@mcp.tool()
def search_commands(query: str, limit: int = 20) -> str:
    """Search for Ceph commands by name, description, or keyword.

    Use this when you're looking for a command but don't know the exact name.
    Searches across command names, descriptions, and keywords.

    Args:
        query: Search term (partial command name, keyword, or description fragment)
        limit: Maximum number of results to return (default 20)
    """
    commands = _get_commands_map()
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
        results.append({
            "name": name,
            "binary": cmd.get("binary"),
            "description": cmd.get("description"),
            "has_subcommands": bool(cmd.get("subcommands")),
        })

    return json.dumps({"query": query, "total_results": len(results), "results": results}, indent=2)


@mcp.tool()
def list_subcommands(command_prefix: str) -> str:
    """List all subcommands under a given command prefix.

    Use this to explore the command tree, e.g. 'ceph osd' to see all osd subcommands.

    Args:
        command_prefix: The command prefix, e.g. 'ceph osd' or 'rbd'
    """
    commands = _get_commands_map()
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
        return json.dumps({
            "command": command_prefix,
            "subcommands": subs,
        }, indent=2)

    prefix_lower = command_prefix.lower()
    children = []
    for name, c in sorted(commands.items()):
        if name.lower().startswith(prefix_lower + " "):
            children.append({
                "name": name,
                "description": c.get("description", ""),
            })

    return json.dumps({
        "command": command_prefix,
        "subcommands": children,
    }, indent=2)


@mcp.tool()
def search_flag(flag: str) -> str:
    """Find which commands accept a specific flag.

    Use this to check if a flag is valid and which commands support it.

    Args:
        flag: The flag to search for, e.g. '--pool' or '-p'
    """
    if _search_index and "by_flag" in _search_index:
        commands = _search_index["by_flag"].get(flag, [])
        return json.dumps({
            "flag": flag,
            "found": bool(commands),
            "commands": commands,
        }, indent=2)

    commands_map = _get_commands_map()
    matching = []
    for name, cmd in commands_map.items():
        for f in cmd.get("flags", []):
            if f.get("short_form") == flag or f.get("long_form") == flag:
                matching.append(name)
                break

    return json.dumps({
        "flag": flag,
        "found": bool(matching),
        "commands": sorted(matching),
    }, indent=2)


@mcp.tool()
def search_argument(argument_name: str) -> str:
    """Find which commands accept a specific argument.

    Use this to check if an argument name is valid and which commands use it.

    Args:
        argument_name: The argument name, e.g. 'pool' or 'image'
    """
    if _search_index and "by_argument" in _search_index:
        commands = _search_index["by_argument"].get(argument_name, [])
        return json.dumps({
            "argument": argument_name,
            "found": bool(commands),
            "commands": commands,
        }, indent=2)

    commands_map = _get_commands_map()
    matching = []
    for name, cmd in commands_map.items():
        for a in cmd.get("arguments", []):
            if a.get("name") == argument_name:
                matching.append(name)
                break

    return json.dumps({
        "argument": argument_name,
        "found": bool(matching),
        "commands": sorted(matching),
    }, indent=2)


@mcp.tool()
def get_help(command_name: str) -> str:
    """Get the parsed help information for a specific command.

    Returns the full structured metadata including usage, description,
    arguments, flags, and examples.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
    """
    commands = _get_commands_map()
    cmd = commands.get(command_name)

    if cmd is None:
        return json.dumps({"found": False, "command": command_name}, indent=2)

    return json.dumps({
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
    }, indent=2)


@mcp.tool()
def get_raw_help(command_name: str) -> str:
    """Get the original raw help text output for a command.

    Use this when the parsed data is insufficient and you need the
    exact text that the command's -h flag produced.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
    """
    if _kb_dir:
        filename = command_name.replace(" ", "-") + ".txt"
        raw_path = _kb_dir / "raw_help" / filename
        if raw_path.exists():
            return raw_path.read_text(encoding="utf-8")

    commands = _get_commands_map()
    cmd = commands.get(command_name)
    if cmd and cmd.get("raw_help"):
        return cmd["raw_help"]

    return json.dumps({"found": False, "command": command_name})


@mcp.tool()
def get_examples(command_name: str) -> str:
    """Get usage examples for a specific command.

    Args:
        command_name: The full command name, e.g. 'ceph osd pool create'
    """
    commands = _get_commands_map()
    cmd = commands.get(command_name)

    if cmd is None:
        return json.dumps({"found": False, "command": command_name}, indent=2)

    return json.dumps({
        "found": True,
        "command": command_name,
        "examples": cmd.get("examples", []),
        "usage": cmd.get("usage"),
    }, indent=2)


@mcp.tool()
def list_versions() -> str:
    """List all available knowledge base versions.

    Use this to check which Ceph versions have been indexed.
    """
    if _kb_data and "version" in _kb_data:
        return json.dumps({
            "versions": [_kb_data["version"]],
        }, indent=2)

    return json.dumps({"versions": []}, indent=2)


@mcp.tool()
def find_binary(binary_name: str) -> str:
    """List all commands for a specific binary.

    Use this to see everything available under a binary like 'rbd' or 'rados'.

    Args:
        binary_name: The binary name, e.g. 'rbd', 'rados', 'cephadm'
    """
    if _search_index and "by_binary" in _search_index:
        commands = _search_index["by_binary"].get(binary_name, [])
        return json.dumps({
            "binary": binary_name,
            "found": bool(commands),
            "total_commands": len(commands),
            "commands": commands,
        }, indent=2)

    commands_map = _get_commands_map()
    matching = sorted(
        name for name, cmd in commands_map.items()
        if cmd.get("binary") == binary_name
    )

    return json.dumps({
        "binary": binary_name,
        "found": bool(matching),
        "total_commands": len(matching),
        "commands": matching,
    }, indent=2)


@mcp.tool()
def search_keyword(keyword: str) -> str:
    """Search commands by keyword across all metadata.

    Searches through command names, descriptions, arguments, flags,
    and extracted keywords.

    Args:
        keyword: The keyword to search for, e.g. 'pool', 'snapshot', 'crush'
    """
    if _search_index and "by_keyword" in _search_index:
        commands = _search_index["by_keyword"].get(keyword.lower(), [])
        if commands:
            return json.dumps({
                "keyword": keyword,
                "found": True,
                "commands": commands,
            }, indent=2)

    return search_commands(keyword)


# ── Config verification tools ──────────────────────────────────────────


@mcp.tool()
def verify_config(config_name: str) -> str:
    """Verify that a Ceph configuration parameter exists and is valid.

    Use this BEFORE setting any Ceph config in automation or tests.
    Returns the parameter's type, default value, description, and
    which daemons it applies to.

    Args:
        config_name: The config parameter name, e.g. 'osd_pool_default_size'
    """
    if not _config_data:
        return json.dumps({"status": "NO_CONFIG_DATA", "reason": "Config knowledge base not loaded"})

    cfg = _config_data.get(config_name)
    if cfg is None:
        close = [
            name for name in _config_data
            if config_name.lower() in name.lower()
        ][:10]
        result = {"config": config_name, "verified": False, "status": "NOT_FOUND"}
        if close:
            result["similar_configs"] = close
        return json.dumps(result, indent=2)

    return json.dumps({
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
    }, indent=2)


@mcp.tool()
def search_config(query: str, limit: int = 20) -> str:
    """Search for Ceph config parameters by name, description, or keyword.

    Use this when looking for a config option but not sure of the exact name.

    Args:
        query: Search term, e.g. 'pool size', 'osd recovery', 'auth'
        limit: Max results (default 20)
    """
    if not _config_data:
        return json.dumps({"query": query, "total_results": 0, "results": []})

    query_lower = query.lower()
    query_words = query_lower.split()

    scored: list[tuple[float, str, dict]] = []

    for name, cfg in _config_data.items():
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

    return json.dumps({"query": query, "total_results": len(results), "results": results}, indent=2)


@mcp.tool()
def get_config_help(config_name: str) -> str:
    """Get full metadata for a Ceph config parameter.

    Returns type, default, description, constraints, daemon-specific
    defaults, and whether it can be changed at runtime.

    Args:
        config_name: The config parameter name, e.g. 'osd_pool_default_size'
    """
    if not _config_data:
        return json.dumps({"found": False, "config": config_name})

    cfg = _config_data.get(config_name)
    if cfg is None:
        return json.dumps({"found": False, "config": config_name})

    return json.dumps({"found": True, **cfg}, indent=2)


@mcp.tool()
def list_configs_by_section(section: str, limit: int = 50) -> str:
    """List all config parameters that belong to a section/prefix.

    Ceph config names are prefixed by subsystem, e.g. 'osd_', 'mon_',
    'rgw_', 'mds_'. Use this to explore all options for a subsystem.

    Args:
        section: The config name prefix, e.g. 'osd', 'mon', 'rgw', 'auth'
        limit: Max results (default 50)
    """
    if not _config_data:
        return json.dumps({"section": section, "total": 0, "configs": []})

    prefix = section.lower().rstrip("_") + "_"
    matching = []

    for name, cfg in sorted(_config_data.items()):
        if name.lower().startswith(prefix):
            matching.append({
                "name": name,
                "type": cfg.get("type"),
                "default": cfg.get("default"),
                "desc": cfg.get("desc"),
            })

    return json.dumps({
        "section": section,
        "total": len(matching),
        "configs": matching[:limit],
    }, indent=2)


# ── Test validation tools ──────────────────────────────────────────────


@mcp.tool()
def validate_script(script_content: str, script_type: str = "auto") -> str:
    """Quick validation of a test script against the Ceph command knowledge base.

    Extracts all Ceph commands from the script and verifies each one exists
    in the knowledge base. Reports unknown commands, invalid flags, and
    basic issues.

    Use this for a fast check before running tests. For a full engineering
    review, use review_test() instead.

    Args:
        script_content: The full text content of the test script.
        script_type: Script language — "python", "shell", "yaml", or "auto" (detect).
    """
    from ceph_command_kb.validation.validator import Validator

    commands = _get_commands_map()
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
    return json.dumps(result, indent=2)


@mcp.tool()
def review_test(script_content: str, script_type: str = "auto") -> str:
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
    """
    from ceph_command_kb.validation.validator import Validator

    commands = _get_commands_map()
    if not commands:
        return json.dumps({"error": "Knowledge base not loaded"})

    validator = Validator(commands)
    report = validator.validate(script_content, script_type=script_type)

    return json.dumps(report.to_dict(), indent=2)


SUPPORTED_TRANSPORTS = ("stdio", "sse", "streamable-http")


def init_kb(kb_path: str | Path | None = None) -> None:
    """Load the knowledge base. Called before starting any transport."""
    if kb_path is None:
        kb_path = _find_latest_kb()

    if kb_path is not None:
        _load_knowledge_base(Path(kb_path))
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

    init_kb(kb_path)

    if transport == "stdio":
        logger.info("Starting MCP server (stdio transport)")
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


def _find_latest_kb() -> Path | None:
    """Find the most recently generated knowledge base."""
    knowledge_dir = Path("knowledge")
    if not knowledge_dir.exists():
        return None

    version_dirs = sorted(
        (d for d in knowledge_dir.iterdir() if d.is_dir() and (d / "commands.json").exists()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    if version_dirs:
        return version_dirs[0]
    return None


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
    args = parser.parse_args()
    run_server(
        kb_path=args.kb_path,
        transport=args.transport,
        host=args.host,
        port=args.port,
    )
