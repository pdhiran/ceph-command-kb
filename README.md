# Ceph Command Knowledge Base

Production-grade system for discovering, documenting, and verifying Ceph CLI commands and configuration parameters. Exposes an MCP server and REST API so AI agents can verify commands, configs, and review test scripts before generating automation.

**Purpose:** Eliminate command and config hallucinations when writing Ceph QE automation.

## What's in the Knowledge Base

| Data | Count | Source |
|------|-------|--------|
| CLI commands | 1,254 | Auto-discovered from 11 binaries |
| Config parameters | 2,660 | `ceph config help` + `ceph config show-with-defaults` |
| Per-daemon defaults | 1,984 | mon, osd, mgr, mds daemon configs |
| Markdown docs | 1,254 | One per command |

## Architecture

```
Generation (on Ceph node)          Serving (anywhere)
┌─────────────┐                    ┌─────────────────────┐
│ Discovery   │──> knowledge/ ──>  │ MCP Server (stdio)  │ ← Cursor
│ Engine      │    commands.json   │ MCP Server (SSE)    │ ← Claude Desktop, Cline, etc.
│ (safe: -h   │    configs.json    │ REST API            │ ← Scripts, CI/CD, IBM Bob
│  only)      │    search_index    └─────────────────────┘
└─────────────┘    markdown/
                   raw_help/
```

### Two Runtime Modes

1. **Generation mode** — runs on a machine with Ceph installed. Discovers commands recursively, parses help output, writes structured output to disk.
2. **Server mode** — runs anywhere. Loads pre-generated knowledge base. No Ceph required.

### Safety

The discovery engine **never executes operational commands**. It only runs `-h`, `--help`, and `help`. Enforced at the `Executor` class level. Safe on production clusters.

## Quick Start

### Install

```bash
cd ceph-command-kb
pip install -e ".[dev]"
```

### Generate Knowledge Base

Run on a machine with Ceph installed (or inside `cephadm shell --mount`):

```bash
python generate_reference.py --verbose
python generate_reference.py --workers 8 --force
python generate_reference.py --resume          # Continue after interruption
python generate_reference.py --reparse         # Re-parse from stored raw help
```

### Import Config Parameters

```bash
# From reference TSV (ceph config help output)
python import_configs.py --reference ceph_config_reference.tsv

# From per-daemon defaults TSV (ceph config show-with-defaults)
python import_configs.py --defaults ceph_config_all_defaults.tsv

# Both merged
python import_configs.py --reference ref.tsv --defaults defaults.tsv
```

### Run Tests

```bash
python -m pytest tests/ -v
```

## Server Modes

### MCP Server (for AI agents)

```bash
# stdio — Cursor (default)
python -m ceph_command_kb.server.mcp_server --kb-path knowledge/ceph-20.2.1-tentacle

# SSE — Claude Desktop, Continue, Cline, Windsurf, IBM watsonx
python -m ceph_command_kb.server.mcp_server --transport sse --port 8080

# Streamable HTTP — newer MCP transport
python -m ceph_command_kb.server.mcp_server --transport streamable-http --port 8080
```

### REST API (for scripts, CI/CD, non-MCP agents)

```bash
python -m ceph_command_kb.server.rest_api --port 9090
```

## MCP Tools

### Command Verification (12 tools)

| Tool | Purpose |
|------|---------|
| `verify_command` | Verify command + flags + arguments exist |
| `find_command` | Look up a command by exact name |
| `search_commands` | Full-text search across names and descriptions |
| `list_subcommands` | List all subcommands under a prefix |
| `search_flag` | Find which commands accept a flag |
| `search_argument` | Find commands by argument name |
| `get_help` | Get parsed help metadata |
| `get_raw_help` | Get original help text |
| `get_examples` | Get usage examples |
| `list_versions` | List available KB versions |
| `find_binary` | List all commands for a binary |
| `search_keyword` | Search by keyword |

### Config Verification (4 tools)

| Tool | Purpose |
|------|---------|
| `verify_config` | Verify a config parameter exists, get type/default/constraints |
| `search_config` | Search config parameters by name or description |
| `get_config_help` | Get full metadata for a config parameter |
| `list_configs_by_section` | List all configs with a prefix (e.g., `osd`, `rgw`) |

### Test Validation (2 tools)

| Tool | Purpose |
|------|---------|
| `validate_script` | Quick check — extract commands and verify against KB |
| `review_test` | Full review — command verification, flag validation, cleanup pairing, risk detection, duplicate detection |

## Integrating with AI Agents

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ceph-kb": {
      "command": "python3",
      "args": ["-m", "ceph_command_kb.server.mcp_server", "--kb-path", "/path/to/knowledge/ceph-20.2.1-tentacle"],
      "cwd": "/path/to/ceph-command-kb"
    }
  }
}
```

### Claude Desktop

Start the SSE server, then add to `claude_desktop_config.json`:

```bash
python -m ceph_command_kb.server.mcp_server --transport sse --port 8080
```

```json
{
  "mcpServers": {
    "ceph-kb": {
      "url": "http://localhost:8080/sse"
    }
  }
}
```

### Continue, Cline, Windsurf

These MCP-compatible editors connect to the SSE or Streamable HTTP endpoint. Start the server and configure the endpoint URL (`http://host:8080/sse` or `http://host:8080/mcp`) in each tool's MCP settings.

### IBM watsonx Orchestrate / IBM Bob

IBM's agent platforms can integrate via the REST API or MCP:

**Option A — REST API (simplest):**

```bash
# Start the REST API on a host accessible to your IBM agents
python -m ceph_command_kb.server.rest_api --host 0.0.0.0 --port 9090
```

IBM Bob agents call the REST endpoints as HTTP tool actions:

```
POST http://your-host:9090/api/verify_command
POST http://your-host:9090/api/search_commands
POST http://your-host:9090/api/review_test
POST http://your-host:9090/api/verify_config
GET  http://your-host:9090/health
```

**Option B — MCP over HTTP (if supported):**

```bash
python -m ceph_command_kb.server.mcp_server --transport sse --host 0.0.0.0 --port 8080
```

Connect watsonx agents to `http://your-host:8080/sse` as an MCP tool provider.

### LangChain / LangGraph

Use the REST API as a custom tool:

```python
import requests

def verify_ceph_command(command: str, flags: list[str] = None) -> dict:
    response = requests.post("http://localhost:9090/api/verify_command", json={
        "command": command,
        "flags": flags,
    })
    return response.json()
```

### CrewAI / AutoGen / Custom Agents

Any agent framework that supports HTTP tool calling can use the REST API. Each endpoint accepts JSON POST and returns structured JSON.

### CI/CD Pipelines

Validate test scripts as a CI step:

```bash
# Start server in background
python -m ceph_command_kb.server.rest_api --port 9090 &

# Validate a test file
curl -s -X POST http://localhost:9090/api/review_test \
  -H "Content-Type: application/json" \
  -d "{\"script_content\": \"$(cat tests/my_test.py)\"}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); sys.exit(1 if r.get('summary',{}).get('errors',0) > 0 else 0)"
```

### Running as a Persistent Service

For team-wide access, run the server as a systemd service or container:

```bash
# Systemd example
[Unit]
Description=Ceph Command KB API
After=network.target

[Service]
ExecStart=/usr/bin/python3 -m ceph_command_kb.server.rest_api --host 0.0.0.0 --port 9090
WorkingDirectory=/opt/ceph-command-kb
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Docker example
docker run -d -p 9090:9090 -v /path/to/knowledge:/app/knowledge ceph-command-kb
```

## REST API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server health + KB status |
| `/api/verify_command` | POST | Verify a command exists |
| `/api/find_command` | POST | Look up command by name |
| `/api/search_commands` | POST | Search commands |
| `/api/list_subcommands` | POST | List subcommands |
| `/api/search_flag` | POST | Search by flag |
| `/api/search_argument` | POST | Search by argument |
| `/api/get_help` | POST | Get parsed help |
| `/api/get_raw_help` | POST | Get raw help text |
| `/api/get_examples` | POST | Get examples |
| `/api/list_versions` | GET/POST | List KB versions |
| `/api/find_binary` | POST | List commands for a binary |
| `/api/search_keyword` | POST | Search by keyword |
| `/api/verify_config` | POST | Verify a config parameter |
| `/api/search_config` | POST | Search config parameters |
| `/api/get_config_help` | POST | Get config metadata |
| `/api/list_configs_by_section` | POST | List configs by prefix |
| `/api/validate_script` | POST | Quick script validation |
| `/api/review_test` | POST | Full test review |

## Output Structure

```
knowledge/ceph-20.2.1-tentacle/
  commands.json          # 1,254 commands with full metadata
  configs.json           # 2,660 config parameters with types, defaults, descriptions
  search_index.json      # Optimized lookup (37,000+ keyword entries)
  metadata.json          # Version, stats, parse quality metrics
  generation.log         # Discovery and parsing log
  markdown/              # 1,254 Markdown files (one per command)
  raw_help/              # 1,254 raw help text files
```

## Project Structure

```
src/ceph_command_kb/
├── models.py              # Command, ConfigOption, Flag, Argument, KnowledgeBase
├── config.py              # YAML configuration loading
├── version.py             # Ceph version detection
├── log.py                 # Logging setup
├── discovery/
│   ├── engine.py          # Recursive discovery orchestrator
│   ├── executor.py        # Safe subprocess runner (ONLY -h/--help/help)
│   └── cache.py           # Resume state and deduplication
├── parsing/
│   ├── base.py            # Abstract parser interface
│   ├── ceph_parser.py     # Ceph native format
│   ├── argparse_parser.py # Python argparse output
│   ├── boost_parser.py    # boost::program_options / rados custom format
│   ├── generic_parser.py  # Fallback best-effort parser
│   └── registry.py        # Binary-to-parser mapping
├── storage/
│   ├── json_writer.py     # commands.json, metadata.json
│   ├── markdown_writer.py # One .md per command
│   ├── search_index.py    # search_index.json
│   ├── raw_help_writer.py # Raw help text files
│   └── config_loader.py   # TSV loader for config parameters
├── validation/
│   ├── extractor.py       # Extract Ceph commands from Python/shell/YAML
│   ├── validator.py       # 5-phase batch validation engine
│   ├── report.py          # Finding, CommandEntry, ValidationReport models
│   ├── cleanup_pairs.py   # 25 create-to-cleanup command mappings
│   └── risk_patterns.py   # 22 destructive command/flag patterns
└── server/
    ├── mcp_server.py      # MCP server (18 tools, 3 transports)
    └── rest_api.py        # REST API (20 endpoints)
```

## Adding New Binaries

Add to `config.yaml` — no code changes required:

```yaml
binaries:
  - my-new-tool                    # Uses auto-detection
  - name: my-custom-tool           # With explicit config
    parser: argparse               # ceph, argparse, boost, generic
    help_flags: ["--help"]
    max_depth: 5
    help_prefix_mode: true         # Use "<binary> help <subcmd>" format
```

The architecture supports any CLI tool. Adding `kubectl`, `podman`, `systemctl`, etc. requires only configuration.

## Design Decisions

1. **Flat command map** — `dict[str, Command]` keyed by full name. O(1) lookup.
2. **Parser registry** — Binary-to-parser mapping with auto-detection fallback.
3. **Raw help always stored** — Re-parse with improved parsers without re-running discovery.
4. **Safe executor as single subprocess boundary** — All safety in one place.
5. **Version-specific output** — Multiple versions coexist. Never mix.
6. **Deterministic validation + LLM reasoning** — MCP tools provide verified facts (command existence, flag validity). The LLM provides contextual reasoning (workflow analysis, QE practices). No brittle rule engine for what the LLM does better.
