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
    find_binary,
    find_command,
    get_examples,
    get_help,
    get_raw_help,
    init_kb,
    list_subcommands,
    list_versions,
    review_test,
    search_argument,
    search_commands,
    search_flag,
    search_keyword,
    validate_script,
    verify_command,
)

logger = logging.getLogger(__name__)


def _parse_json(raw: str) -> dict:
    return json.loads(raw)


async def handle_find_command(request: Request) -> JSONResponse:
    params = await request.json()
    result = find_command(command_name=params["command_name"])
    return JSONResponse(_parse_json(result))


async def handle_verify_command(request: Request) -> JSONResponse:
    params = await request.json()
    result = verify_command(
        command=params["command"],
        flags=params.get("flags"),
        arguments=params.get("arguments"),
    )
    return JSONResponse(_parse_json(result))


async def handle_search_commands(request: Request) -> JSONResponse:
    params = await request.json()
    result = search_commands(
        query=params["query"],
        limit=params.get("limit", 20),
    )
    return JSONResponse(_parse_json(result))


async def handle_list_subcommands(request: Request) -> JSONResponse:
    params = await request.json()
    result = list_subcommands(command_prefix=params["command_prefix"])
    return JSONResponse(_parse_json(result))


async def handle_search_flag(request: Request) -> JSONResponse:
    params = await request.json()
    result = search_flag(flag=params["flag"])
    return JSONResponse(_parse_json(result))


async def handle_search_argument(request: Request) -> JSONResponse:
    params = await request.json()
    result = search_argument(argument_name=params["argument_name"])
    return JSONResponse(_parse_json(result))


async def handle_get_help(request: Request) -> JSONResponse:
    params = await request.json()
    result = get_help(command_name=params["command_name"])
    return JSONResponse(_parse_json(result))


async def handle_get_raw_help(request: Request) -> JSONResponse:
    params = await request.json()
    raw = get_raw_help(command_name=params["command_name"])
    try:
        return JSONResponse(_parse_json(raw))
    except json.JSONDecodeError:
        return JSONResponse({"raw_help": raw})


async def handle_get_examples(request: Request) -> JSONResponse:
    params = await request.json()
    result = get_examples(command_name=params["command_name"])
    return JSONResponse(_parse_json(result))


async def handle_list_versions(request: Request) -> JSONResponse:
    result = list_versions()
    return JSONResponse(_parse_json(result))


async def handle_find_binary(request: Request) -> JSONResponse:
    params = await request.json()
    result = find_binary(binary_name=params["binary_name"])
    return JSONResponse(_parse_json(result))


async def handle_search_keyword(request: Request) -> JSONResponse:
    params = await request.json()
    result = search_keyword(keyword=params["keyword"])
    return JSONResponse(_parse_json(result))


async def handle_validate_script(request: Request) -> JSONResponse:
    params = await request.json()
    result = validate_script(
        script_content=params["script_content"],
        script_type=params.get("script_type", "auto"),
    )
    return JSONResponse(_parse_json(result))


async def handle_review_test(request: Request) -> JSONResponse:
    params = await request.json()
    result = review_test(
        script_content=params["script_content"],
        script_type=params.get("script_type", "auto"),
    )
    return JSONResponse(_parse_json(result))


async def handle_health(request: Request) -> JSONResponse:
    from ceph_command_kb.server.mcp_server import _kb_data
    return JSONResponse({
        "status": "ok",
        "kb_loaded": _kb_data is not None,
        "total_commands": len(_kb_data.get("commands", [])) if _kb_data else 0,
    })


routes = [
    Route("/health", handle_health, methods=["GET"]),
    Route("/api/find_command", handle_find_command, methods=["POST"]),
    Route("/api/verify_command", handle_verify_command, methods=["POST"]),
    Route("/api/search_commands", handle_search_commands, methods=["POST"]),
    Route("/api/list_subcommands", handle_list_subcommands, methods=["POST"]),
    Route("/api/search_flag", handle_search_flag, methods=["POST"]),
    Route("/api/search_argument", handle_search_argument, methods=["POST"]),
    Route("/api/get_help", handle_get_help, methods=["POST"]),
    Route("/api/get_raw_help", handle_get_raw_help, methods=["POST"]),
    Route("/api/get_examples", handle_get_examples, methods=["POST"]),
    Route("/api/list_versions", handle_list_versions, methods=["GET", "POST"]),
    Route("/api/find_binary", handle_find_binary, methods=["POST"]),
    Route("/api/search_keyword", handle_search_keyword, methods=["POST"]),
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
