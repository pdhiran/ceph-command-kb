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

**Claude Desktop / Continue / Cline / Windsurf / IBM Bob** — all connect via SSE:

```bash
python -m ceph_command_kb.server.mcp_server --transport sse --host 0.0.0.0 --port 8081
```

Configure your agent to connect to `http://localhost:8081/sse`:

```json
{
  "mcpServers": {
    "ceph-cmd-kb": {
      "url": "http://localhost:8081/sse",
      "transport": "sse"
    }
  }
}
```

For Claude Desktop: add to `claude_desktop_config.json`. For Bob: add to `.bob/mcp.json`. For Continue/Cline/Windsurf: use the MCP settings UI.

---

**LangChain / CrewAI / CI pipelines / custom scripts** — use the REST API:

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

## Running All Ceph MCPs Together

Three specialized MCPs work together as the Ceph Engineering Intelligence Platform:

| MCP | Purpose | SSE Port | Repo |
|-----|---------|----------|------|
| **ceph-cmd-kb** | Commands, configs, test validation | 8081 | [ceph-command-kb](https://github.com/pdhiran/ceph-command-kb) |
| **ceph-doc-kb** | Documentation search, code examples | 8082 | [ceph-doc-kb](https://github.com/pdhiran/ceph-document-kb) |
| **ceph-issue-kb** | Known issues, workarounds, fixes | 8083 | [ceph-issue-kb](https://github.com/pdhiran/ceph-issue-kb) |

Start all three for SSE clients (Bob, Claude Desktop, etc.):

```bash
python -m ceph_command_kb.server.mcp_server --transport sse --port 8081 &
python -m ceph_doc_kb.server.mcp_server --transport sse --port 8082 &
python -m ceph_issue_kb.server.mcp_server --transport sse --port 8083 &
```

Combined agent config (`.bob/mcp.json`, `claude_desktop_config.json`, etc.):

```json
{
  "mcpServers": {
    "ceph-cmd-kb": { "url": "http://localhost:8081/sse", "transport": "sse" },
    "ceph-doc-kb": { "url": "http://localhost:8082/sse", "transport": "sse" },
    "ceph-issue-kb": { "url": "http://localhost:8083/sse", "transport": "sse" }
  }
}
```

Agents call whichever MCP has the right tools — the LLM decides automatically.

## Further Documentation

- [Development Guide](DEVELOPMENT.md) — architecture, project structure, adding binaries, design decisions, maintainer guide
