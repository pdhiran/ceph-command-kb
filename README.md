# Ceph Command Knowledge Base

Verified knowledge base of Ceph CLI commands and config parameters. Ships **pre-generated JSON** — the MCP does not need a live cluster.

Indexed versions (on disk under `knowledge/`):

| Label | Release | IBM product | Typical use |
|-------|---------|-------------|-------------|
| `ceph-19.2.1-squid` | Squid 19.x | IBM Storage Ceph 8.x | 8.1 clusters |
| `ceph-20.2.1-tentacle` | Tentacle 20.x | IBM Storage Ceph 9.x | 9.1 clusters |

Use this MCP to **stop command hallucination**: verify a command, flag, argument, or config exists *before* writing automation or tests.

## For agents (read this first)

**Always pass `version`.** Accepted aliases: `squid`, `tentacle`, `8.1`, `9.1`, `19`, `20`. If the user did not name a version, **ask** (8.1/Squid vs 9.1/Tentacle). Do not silently default.

| Do | Do not |
|---|---|
| `verify_command` before emitting any `ceph`/`rbd`/`rados`/`cephadm` line | Invent flags or subcommands |
| `verify_config` before `ceph config set` | Assume a config name from memory |
| `review_test` on CephCI/python/shell/YAML that runs Ceph CLI | Use this KB for “how does stretch mode work?” — **ceph-doc-kb** |
| `search_commands` when `verify_command` returns `NOT_VERIFIED` | Use this KB for crashes/JIRA — **ceph-issue-kb** |

**Typical first calls**

1. Infer or ask version → pass it on every subsequent call.
2. `verify_command(command="ceph osd pool create", flags=["--size"], version="squid")`
3. If `NOT_VERIFIED`, `search_commands(query="...", version=...)` then retry.

Status values: `VERIFIED`, `PARTIALLY_VERIFIED`, `NOT_VERIFIED`. Never treat `NOT_VERIFIED` as “probably fine”.

The index is only as fresh as the last `generate_reference.py` run on a live cluster. New CLI (for example recently added auth/cipher commands) will be missing until that version is rediscovered — see [Updating the knowledge base](#updating-the-knowledge-base). Absence from this KB means “not indexed”, not “absent from the product”.

## Ceph Engineering Intelligence Platform

| MCP | Cursor key | Use when | SSE | REST |
|-----|------------|----------|-----|------|
| **ceph-cmd-kb** | `ceph-cmd-kb` | Verify CLI, flags, configs, review scripts | 8081 | 9090 |
| **ceph-doc-kb** | `ceph-doc-kb` | How-to, architecture, IBM procedures | 8082 | 8100 |
| **ceph-issue-kb** | `ceph-issue-kb` | Known bugs, workarounds, stacktraces | 8083 | 8200 |
| **ceph-prio-hub** | `ceph-prio-hub` | Customer prio-list / L3 tracking | 8080 | — |
| **cephci-kb** | `cephci-kb` | CephCI code, tests, workflows | 8084 | — |

Combined SSE config:

```json
{
  "mcpServers": {
    "ceph-cmd-kb": { "url": "http://localhost:8081/sse", "transport": "sse" },
    "ceph-doc-kb": { "url": "http://localhost:8082/sse", "transport": "sse" },
    "ceph-issue-kb": { "url": "http://localhost:8083/sse", "transport": "sse" },
    "ceph-prio-hub": { "url": "http://localhost:8080/sse", "transport": "sse" },
    "cephci-kb": { "url": "http://localhost:8084/sse", "transport": "sse" }
  }
}
```

## Setup

```bash
git clone https://github.com/pdhiran/ceph-command-kb.git
cd ceph-command-kb
pip install -e .
```

No Ceph cluster is required to **serve**. A cluster is required only to **rebuild** the index.

## Incorporate into an agent

### Cursor (stdio)

```json
{
  "mcpServers": {
    "ceph-cmd-kb": {
      "command": "python3",
      "args": ["-m", "ceph_command_kb.server.mcp_server"],
      "cwd": "/path/to/ceph-command-kb"
    }
  }
}
```

The server auto-discovers every `knowledge/ceph-*-*/` directory that contains `commands.json`. `--kb-path` is optional (a version dir or the knowledge root); sibling versions in that tree are still loaded. Omit it unless you need to point at a non-default tree.

Restart Cursor after editing `mcp.json`.

### SSE

```bash
python3 -m ceph_command_kb.server.mcp_server --transport sse --host 0.0.0.0 --port 8081
```

Point Claude Desktop (`claude_desktop_config.json`), Bob (`.bob/mcp.json`), Continue/Cline/Windsurf at `http://localhost:8081/sse`.

### REST (LangChain, CrewAI, CI)

```bash
python3 -m ceph_command_kb.server.rest_api --host 0.0.0.0 --port 9090
```

```bash
curl -X POST http://localhost:9090/api/verify_command \
  -H "Content-Type: application/json" \
  -d '{"command": "ceph osd pool create", "version": "squid"}'

curl -X POST http://localhost:9090/api/verify_config \
  -H "Content-Type: application/json" \
  -d '{"name": "osd_pool_default_size", "version": "tentacle"}'

curl http://localhost:9090/health
```

Python client and LangChain wrappers: [examples/bob_agent_integration.py](examples/bob_agent_integration.py). Full REST table: [BOB_INTEGRATION_GUIDE.md](BOB_INTEGRATION_GUIDE.md). VS Code extension: [vscode-extension/](vscode-extension/).

## Tool catalog

Every command/config tool takes optional `version`. Omit only when the conversation already pinned a version.

### Commands

| Tool | Args | When to call |
|------|------|----------------|
| `verify_command` | `command`, optional `flags[]`, `arguments[]`, `version` | Before writing any CLI. Returns VERIFIED / PARTIALLY_VERIFIED / NOT_VERIFIED plus similar names on miss. |
| `find_command` | `command_name`, `version` | Exact full name lookup (`ceph osd pool create`) |
| `search_commands` | `query`, `limit=20`, `version` | Unknown name; keyword or partial |
| `list_subcommands` | `command_prefix`, `version` | Explore tree (`ceph osd`, `rbd`) |
| `search_flag` | `flag` (`--pool` or `-p`), `version` | Which commands accept this flag |
| `search_argument` | `argument_name`, `version` | Which commands use this argument |
| `get_help` | `command_name`, `version` | Parsed metadata |
| `get_raw_help` | `command_name`, `version` | Original help text |
| `get_examples` | `command_name`, `version` | Usage examples from help |
| `find_binary` | `binary_name`, `version` | All commands under `rbd` / `rados` / `cephadm` / … |
| `search_keyword` | `keyword`, `version` | Broader than `search_commands` |
| `list_versions` | (none) | Labels, counts, default version |

### Configs

| Tool | Args | When to call |
|------|------|----------------|
| `verify_config` | `name`, `version` | Before `ceph config set`. Returns type, default, min/max, `can_update_at_runtime`, services. |
| `search_config` | `query` (not `keyword`), `limit=20`, `version` | Unknown parameter name |
| `get_config_help` | `name`, `version` | Full metadata blob |
| `list_configs_by_section` | `section` (`osd`, `mon`, `rgw`, `auth`, …), `limit=50`, `version` | Explore a subsystem |

### Test validation

| Tool | Args | When to call |
|------|------|----------------|
| `validate_script` | `script_content`, `script_type=auto`, `version` | Fast extract-and-verify |
| `review_test` | `script_content`, `script_type=auto`, `version` | Full report: commands, flags, missing cleanup, destructive ops, duplicates. Then apply your own workflow/QE reasoning. |

Also: `capabilities`, `health`.

### Agent workflow: generating a test snippet

1. Pin version.
2. `verify_command` for every CLI line (include flags).
3. `verify_config` for every config name.
4. After drafting the file, `review_test(script_content=<full file>)`.
5. Present automated findings, then contextual analysis (ordering, cleanup, health checks).

### Agent workflow: unknown command

1. `verify_command` → `NOT_VERIFIED`
2. `search_commands` / `list_subcommands`
3. If still missing: say it is not in this KB version; check **ceph-doc-kb** `find_docs_for_command` and/or rebuild from a live cluster.

## Supported binaries

`ceph`, `rbd`, `rados`, `cephadm`, `ceph-volume`, `ceph-authtool`, `ceph-bluestore-tool`, `ceph-objectstore-tool`, `crushtool`, `monmaptool`, `osdmaptool`

## Updating the knowledge base

Same `--since YYYY-MM-DD` contract as `python index_issues.py --since DATE`.

Command `--help` has **no date filter**. `--since` records the delta window in `metadata.json` (`updated_since`, `last_incremental_at`) and runs a **full rediscovery** from live binaries (safe: only `-h` / `--help` / `help`).

Must run on a node where those binaries are on `PATH` (cluster admin / cephadm shell host). Copy `knowledge/<version>/` back into this repo afterward.

```bash
# On a cluster node, from this repo (or a checkout of it)
python3 generate_reference.py --since 2026-08-01 --verbose --force

# Canonical wrapper (last-run tracker + .reload_trigger for in-process MCP reload)
./update_index.sh                 # last run, or last 1 day
./update_index.sh 7
./update_index.sh 2026-08-01
./update_index.sh --reset

# Re-parse stored raw_help/*.txt without a cluster
python3 generate_reference.py --reparse --since 2026-08-01
```

Full maintainer help (hot-reload, git auto-update, no Cursor restart): [UPDATING.md](UPDATING.md).

Other generate flags: `--resume`, `--force`, `--workers N`, `--output DIR`, `--docs` (also write markdown + raw help), `--config config.yaml`.

Config parameters are imported separately via `import_configs.py` (TSV from `ceph --show-config-dump` / project pipeline) into `knowledge/<version>/configs.json`.

## Architecture

```
Live cluster (optional, generate only)
  DiscoveryEngine runs `<binary> -h` recursively
        │
        ▼
 knowledge/ceph-19.2.1-squid/{commands,configs,search_index,metadata}.json
 knowledge/ceph-20.2.1-tentacle/...
        │
        ▼
 MCP (stdio/SSE) / REST  — no Ceph required
```

Generation never runs mutating cluster commands. See [DEVELOPMENT.md](DEVELOPMENT.md) for parsers, validation phases, and project layout.

## Development

```bash
pip install -e ".[dev]"
pytest
```
