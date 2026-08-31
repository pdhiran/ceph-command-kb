# Development Guide

## Architecture

```
Generation (on Ceph node)          Serving (anywhere)
┌─────────────┐                    ┌─────────────────────┐
│ Discovery   │──> knowledge/ ──>  │ MCP Server (stdio)  │ ← Cursor
│ Engine      │    commands.json   │ MCP Server (SSE)    │ ← Claude Desktop, etc.
│ (safe: -h   │    configs.json    │ REST API            │ ← Scripts, CI/CD
│  only)      │    search_index    └─────────────────────┘
└─────────────┘    metadata.json
```

**Generation mode** runs on a Ceph node — discovers commands recursively by running only `-h`/`--help`/`help`. Safe on production clusters.

**Server mode** runs anywhere — loads pre-generated JSON files. No Ceph required.

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
│   ├── markdown_writer.py # One .md per command (opt-in via --docs)
│   ├── search_index.py    # search_index.json
│   ├── raw_help_writer.py # Raw help text files (opt-in via --docs)
│   └── config_loader.py   # TSV loader for config parameters
├── validation/
│   ├── extractor.py       # Extract Ceph commands from Python/shell/YAML
│   ├── validator.py       # 5-phase batch validation engine
│   ├── report.py          # Finding, CommandEntry, ValidationReport models
│   ├── cleanup_pairs.py   # 25 create-to-cleanup command mappings
│   └── risk_patterns.py   # 22 destructive command/flag patterns
└── server/
    ├── mcp_server.py      # MCP server (20 tools, 3 transports)
    ├── rest_api.py        # REST API (20 endpoints, default port 9090)
    └── auto_update.py     # git pull + .reload_trigger watcher
```

## Knowledge Base Structure

```
knowledge/
  ceph-19.2.1-squid/       # 1,164 commands, 2,409 configs
  ceph-20.2.1-tentacle/    # 1,254 commands, 2,660 configs
Each version directory: commands.json, configs.json, search_index.json, metadata.json.
raw_help/ and markdown/ are written only with --docs and are gitignored.
```

## REST API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server health + KB status |
| `/api/capabilities` | GET | Machine-readable tool/version catalog |
| `/api/verify_command` | POST | Verify a command exists (`version` optional) |
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

## Running as a Persistent Service

### systemd

```ini
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

### Docker

```bash
docker run -d -p 9090:9090 -v /path/to/knowledge:/app/knowledge ceph-command-kb
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
3. **Raw help is opt-in** — `generate_reference.py --docs` writes `raw_help/` (gitignored). Re-parse needs that local tree.
4. **Safe executor as single subprocess boundary** — All safety in one place.
5. **Version-specific output** — Multiple versions coexist. Never mix.
6. **Deterministic validation + LLM reasoning** — MCP tools provide verified facts. The LLM provides contextual reasoning (workflow analysis, QE practices). No brittle rule engine for what the LLM does better.

## Running Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

126 tests covering: models, executor safety, all 4 parsers, storage writers, MCP tools, REST `version` forwarding, auto-update / `--since`, command extraction, validation engine.

---

## Maintainer Guide

Canonical incremental rebuild (records `--since`, touches `.reload_trigger`): see [UPDATING.md](UPDATING.md) and `./update_index.sh`. `./update_kb.sh` only execs `./update_index.sh`.

### Regenerate Command KB

Run inside `cephadm shell --mount /path/to/ceph-command-kb:/mnt/ceph-command-kb`:

```bash
cd /mnt/ceph-command-kb
python3 generate_reference.py --verbose --force
python3 generate_reference.py --verbose --docs   # optional: also generate markdown + raw help
# or: ./update_index.sh 2026-08-01
```

`--since YYYY-MM-DD` does **not** skip commands. It stamps `metadata.json` and still runs full `--help` discovery.

### Capture Config Parameters

There is no `capture_config_reference.py` in this repo. Produce TSVs from a live cluster (`ceph --show-config-dump` / your capture pipeline), then:

```bash
python3 import_configs.py \
  --reference ceph_config_reference.tsv \
  --defaults ceph_config_all_defaults.tsv \
  --kb-dir knowledge/ceph-20.2.1-tentacle
```

Default `--kb-dir` is tentacle. For squid, pass `knowledge/ceph-19.2.1-squid`.

### Update from Manual Help Text

For tools where the parser doesn't fully extract metadata:

```bash
python3 update_from_help.py
```

### Re-parse with Improved Parsers

After fixing a parser, regenerate structured data from stored raw help (`raw_help/` is gitignored; needs a prior `--docs` generate):

```bash
python3 generate_reference.py --reparse --verbose
```

That rewrites **only** `sorted(knowledge/)[-1]` (tentacle today). `reparse_kb.py` is a tentacle-hardcoded leftover — do not use it as the generic path.
