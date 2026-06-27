"""Standalone REST API for non-MCP consumers.

Wraps the same tool functions used by the MCP server into standard
HTTP endpoints. Use this for custom LLM pipelines, scripts, CI/CD,
or any consumer that doesn't speak MCP.

Usage:
    python -m ceph_command_kb.server.rest_api
    python -m ceph_command_kb.server.rest_api --port 9090
    python -m ceph_command_kb.server.rest_api --kb-path knowledge/ceph-19.2.0-squid
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ceph_command_kb.server.mcp_server import (
    capabilities,
    find_binary,
    find_command,
    get_config_help,
    get_examples,
    get_help,
    get_raw_help,
    health,
    init_kb,
    list_configs_by_section,
    list_subcommands,
    list_versions,
    review_test,
    search_argument,
    search_commands,
    search_config,
    search_flag,
    search_keyword,
    validate_script,
    verify_command,
    verify_config,
)

logger = logging.getLogger(__name__)


def _parse_json(raw: str) -> dict:
    return json.loads(raw)


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


async def _get_params(request: Request, required: list[str]) -> dict | JSONResponse:
    """Parse JSON body and validate required keys. Returns params dict or error response."""
    try:
        params = await request.json()
    except Exception:
        return _error_response(400, "Invalid or missing JSON body")
    missing = [k for k in required if k not in params]
    if missing:
        return _error_response(400, f"Missing required field(s): {', '.join(missing)}")
    return params


async def handle_find_command(request: Request) -> JSONResponse:
    params = await _get_params(request, ["command_name"])
    if isinstance(params, JSONResponse):
        return params
    result = find_command(command_name=params["command_name"])
    return JSONResponse(_parse_json(result))


async def handle_verify_command(request: Request) -> JSONResponse:
    params = await _get_params(request, ["command"])
    if isinstance(params, JSONResponse):
        return params
    result = verify_command(
        command=params["command"],
        flags=params.get("flags"),
        arguments=params.get("arguments"),
    )
    return JSONResponse(_parse_json(result))


async def handle_search_commands(request: Request) -> JSONResponse:
    params = await _get_params(request, ["query"])
    if isinstance(params, JSONResponse):
        return params
    result = search_commands(
        query=params["query"],
        limit=params.get("limit", 20),
    )
    return JSONResponse(_parse_json(result))


async def handle_list_subcommands(request: Request) -> JSONResponse:
    params = await _get_params(request, ["command_prefix"])
    if isinstance(params, JSONResponse):
        return params
    result = list_subcommands(command_prefix=params["command_prefix"])
    return JSONResponse(_parse_json(result))


async def handle_search_flag(request: Request) -> JSONResponse:
    params = await _get_params(request, ["flag"])
    if isinstance(params, JSONResponse):
        return params
    result = search_flag(flag=params["flag"])
    return JSONResponse(_parse_json(result))


async def handle_search_argument(request: Request) -> JSONResponse:
    params = await _get_params(request, ["argument_name"])
    if isinstance(params, JSONResponse):
        return params
    result = search_argument(argument_name=params["argument_name"])
    return JSONResponse(_parse_json(result))


async def handle_get_help(request: Request) -> JSONResponse:
    params = await _get_params(request, ["command_name"])
    if isinstance(params, JSONResponse):
        return params
    result = get_help(command_name=params["command_name"])
    return JSONResponse(_parse_json(result))


async def handle_get_raw_help(request: Request) -> JSONResponse:
    params = await _get_params(request, ["command_name"])
    if isinstance(params, JSONResponse):
        return params
    raw = get_raw_help(command_name=params["command_name"])
    try:
        return JSONResponse(_parse_json(raw))
    except json.JSONDecodeError:
        return JSONResponse({"raw_help": raw})


async def handle_get_examples(request: Request) -> JSONResponse:
    params = await _get_params(request, ["command_name"])
    if isinstance(params, JSONResponse):
        return params
    result = get_examples(command_name=params["command_name"])
    return JSONResponse(_parse_json(result))


async def handle_list_versions(request: Request) -> JSONResponse:
    result = list_versions()
    return JSONResponse(_parse_json(result))


async def handle_find_binary(request: Request) -> JSONResponse:
    params = await _get_params(request, ["binary_name"])
    if isinstance(params, JSONResponse):
        return params
    result = find_binary(binary_name=params["binary_name"])
    return JSONResponse(_parse_json(result))


async def handle_search_keyword(request: Request) -> JSONResponse:
    params = await _get_params(request, ["keyword"])
    if isinstance(params, JSONResponse):
        return params
    result = search_keyword(keyword=params["keyword"])
    return JSONResponse(_parse_json(result))


async def handle_verify_config(request: Request) -> JSONResponse:
    params = await _get_params(request, [])
    if isinstance(params, JSONResponse):
        return params
    name = params.get("name") or params.get("config_name", "")
    if not name:
        return _error_response(400, "Missing required field: 'name' or 'config_name'")
    result = verify_config(name=name)
    return JSONResponse(_parse_json(result))


async def handle_search_config(request: Request) -> JSONResponse:
    params = await _get_params(request, [])
    if isinstance(params, JSONResponse):
        return params
    query = params.get("query") or params.get("keyword", "")
    if not query:
        return _error_response(400, "Missing required field: 'query' or 'keyword'")
    result = search_config(query=query, limit=params.get("limit", 20))
    return JSONResponse(_parse_json(result))


async def handle_get_config_help(request: Request) -> JSONResponse:
    params = await _get_params(request, [])
    if isinstance(params, JSONResponse):
        return params
    name = params.get("name") or params.get("config_name", "")
    if not name:
        return _error_response(400, "Missing required field: 'name' or 'config_name'")
    result = get_config_help(name=name)
    return JSONResponse(_parse_json(result))


async def handle_list_configs_by_section(request: Request) -> JSONResponse:
    params = await _get_params(request, ["section"])
    if isinstance(params, JSONResponse):
        return params
    result = list_configs_by_section(section=params["section"], limit=params.get("limit", 50))
    return JSONResponse(_parse_json(result))


async def handle_validate_script(request: Request) -> JSONResponse:
    params = await _get_params(request, ["script_content"])
    if isinstance(params, JSONResponse):
        return params
    result = validate_script(
        script_content=params["script_content"],
        script_type=params.get("script_type", "auto"),
    )
    return JSONResponse(_parse_json(result))


async def handle_review_test(request: Request) -> JSONResponse:
    params = await _get_params(request, ["script_content"])
    if isinstance(params, JSONResponse):
        return params
    result = review_test(
        script_content=params["script_content"],
        script_type=params.get("script_type", "auto"),
    )
    return JSONResponse(_parse_json(result))


async def handle_health(request: Request) -> JSONResponse:
    result = health()
    return JSONResponse(_parse_json(result))


async def handle_capabilities(request: Request) -> JSONResponse:
    result = capabilities()
    return JSONResponse(_parse_json(result))


routes = [
    Route("/health", handle_health, methods=["GET"]),
    Route("/api/capabilities", handle_capabilities, methods=["GET"]),
    Route("/api/find_command", handle_find_command, methods=["POST"]),
    Route("/api/verify_command", handle_verify_command, methods=["POST"]),
    Route("/api/search_commands", handle_search_commands, methods=["POST"]),
    Route("/api/list_subcommands", handle_list_subcommands, methods=["POST"]),
    Route("/api/search_flag", handle_search_flag, methods=["POST"]),
    Route("/api/search_argument", handle_search_argument, methods=["POST"]),
    Route("/api/get_help", handle_get_help, methods=["POST"]),
    Route("/api/get_raw_help", handle_get_raw_help, methods=["POST"]),
    Route("/api/get_examples", handle_get_examples, methods=["POST"]),
    Route("/api/list_versions", handle_list_versions, methods=["GET"]),
    Route("/api/find_binary", handle_find_binary, methods=["POST"]),
    Route("/api/search_keyword", handle_search_keyword, methods=["POST"]),
    Route("/api/verify_config", handle_verify_config, methods=["POST"]),
    Route("/api/search_config", handle_search_config, methods=["POST"]),
    Route("/api/get_config_help", handle_get_config_help, methods=["POST"]),
    Route("/api/list_configs_by_section", handle_list_configs_by_section, methods=["POST"]),
    Route("/api/validate_script", handle_validate_script, methods=["POST"]),
    Route("/api/review_test", handle_review_test, methods=["POST"]),
]

app = Starlette(routes=routes)


def run_rest_api(
    kb_path: str | Path | None = None,
    host: str = "0.0.0.0",
    port: int = 9090,
) -> None:
    init_kb(kb_path)
    logger.info("Starting REST API on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ceph Command KB REST API")
    parser.add_argument(
        "--kb-path",
        type=Path,
        default=None,
        help="Path to knowledge base version directory",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=9090,
        help="Port (default: 9090)",
    )
    args = parser.parse_args()
    run_rest_api(kb_path=args.kb_path, host=args.host, port=args.port)
