# Ceph Command Knowledge Base

Verified knowledge base of **1,254 Ceph CLI commands** and **2,660 config parameters** for Ceph 20.2.1 (Tentacle). Ships pre-generated — no Ceph cluster needed to use.

Exposes an MCP server and REST API so AI agents can verify commands, configs, and review test scripts before generating automation. Eliminates command hallucinations.

## Setup

### 1. Clone and install

```bash
git clone https://github.com/pdhiran/ceph-command-kb.git
cd ceph-command-kb
pip install -e .
```

### 2. Connect your agent

Choose the integration that matches your agent:

---

**Cursor** — add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ceph-cmd-kb": {
      "command": "python3",
      "args": ["-m", "ceph_command_kb.server.mcp_server", "--kb-path", "/path/to/ceph-command-kb/knowledge/ceph-20.2.1-tentacle"],
      "cwd": "/path/to/ceph-command-kb"
    }
  }
}
```

Restart Cursor. The MCP server starts automatically.

---

**Claude Desktop** — start the server, then add to `claude_desktop_config.json`:

```bash
python -m ceph_command_kb.server.mcp_server --transport sse --port 8080
```

```json
{
  "mcpServers": {
    "ceph-cmd-kb": { "url": "http://localhost:8080/sse" }
  }
}
```

---

**Continue / Cline / Windsurf** — start the server and point to the SSE endpoint:

```bash
python -m ceph_command_kb.server.mcp_server --transport sse --port 8080
```

Connect to `http://localhost:8080/sse` in the tool's MCP settings.

---

**IBM watsonx / IBM Bob / LangChain / CrewAI / CI pipelines** — use the REST API:

```bash
python -m ceph_command_kb.server.rest_api --host 0.0.0.0 --port 9090
```

```bash
# Verify a command
curl -X POST http://localhost:9090/api/verify_command \
  -H "Content-Type: application/json" \
  -d '{"command": "ceph osd pool create"}'

# Verify a config parameter
curl -X POST http://localhost:9090/api/verify_config \
  -H "Content-Type: application/json" \
  -d '{"name": "osd_pool_default_size"}'

# Search commands
curl -X POST http://localhost:9090/api/search_commands \
  -H "Content-Type: application/json" \
  -d '{"query": "nfs cluster create"}'

# Review a test script
curl -X POST http://localhost:9090/api/review_test \
  -H "Content-Type: application/json" \
  -d '{"script_content": "ceph osd pool create mypool 32\nrbd create img --size 1024"}'

# Health check
curl http://localhost:9090/health
```

**Additional integration guides:**
- [VS Code Extension](vscode-extension/) — Inline command verification, search, and script review for VS Code / Bob users
- [BOB_INTEGRATION_GUIDE.md](BOB_INTEGRATION_GUIDE.md) — REST API integration guide with deployment options
- [examples/bob_agent_integration.py](examples/bob_agent_integration.py) — Ready-to-use Python client and LangChain/CrewAI tools

### 3. Use it

Once connected, agents automatically verify Ceph commands against the KB. You can also ask directly:

- *"Verify the command `ceph osd pool create --size 3`"*
- *"What rbd commands are available for mirroring?"*
- *"Show me the default value of `osd_pool_default_size`"*
- *"Review this test file for issues"*

## Available Tools

### Command Verification (12 tools)

| Tool | Purpose |
|------|---------|
| `verify_command` | Verify command + flags + arguments exist |
| `find_command` | Look up a command by exact name |
| `search_commands` | Search across names and descriptions |
| `list_subcommands` | List subcommands under a prefix |
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
| `verify_config` | Verify config exists, get type/default/constraints |
| `search_config` | Search config parameters by name or description |
| `get_config_help` | Get full config metadata |
| `list_configs_by_section` | List all configs for a subsystem (e.g., `osd`, `rgw`) |

### Test Validation (2 tools)

| Tool | Purpose |
|------|---------|
| `validate_script` | Quick check — extract and verify commands |
| `review_test` | Full review — verification, flags, cleanup, risk, duplicates |

## Supported Ceph Binaries

ceph, rbd, rados, cephadm, ceph-volume, ceph-authtool, ceph-bluestore-tool, ceph-objectstore-tool, crushtool, monmaptool, osdmaptool

## Further Documentation

- [Development Guide](DEVELOPMENT.md) — architecture, project structure, adding binaries, design decisions, maintainer guide
