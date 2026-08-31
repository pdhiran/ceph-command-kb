# Updating the command knowledge base

This is the maintainer help for **ceph-command-kb**. Agents and humans: use this page when rebuilding or refreshing the served index. Do not invent a different workflow.

Cursor does **not** need a restart after an index update. The MCP process hot-reloads `knowledge/` in-process, or (only if `.py` files changed) Cursor respawns the MCP subprocess.

## Canonical command

```bash
cd /path/to/ceph-command-kb
./update_index.sh                 # since yesterday of last success (1-day overlap), or last 1 day if first run
./update_index.sh 7               # last 7 days
./update_index.sh 2026-08-01      # explicit ISO date
./update_index.sh --reset         # clear .last_index_update
```

`./update_kb.sh` is a thin wrapper that execs `./update_index.sh`. Prefer `./update_index.sh`.

Must run on a host where Ceph binaries (`ceph`, `rbd`, …) are on `PATH`. After capture, copy `knowledge/<version>/` back into this git repo if you generated on a cluster node.

## What `./update_index.sh` does

1. Resolves `--since` (argument, `.last_index_update`, or yesterday).
2. Runs `python3 generate_reference.py --since DATE --verbose --force`.
3. Touches `.reload_trigger` in the repo root.
4. Writes `.last_index_update`.

Command `--help` has **no date filter**. `--since` is recorded in `metadata.json` (`updated_since`, `last_incremental_at`) and a **full rediscovery** runs (safe: only `-h` / `--help` / `help`). The date is a recorded window, not a filter of which commands are discovered.

After a successful `./update_index.sh`, `.last_index_update` stores **yesterday of the run date** (same 1-day overlap as ceph-issue-kb `update_index.sh`), not the ISO date you passed in.

## How the running MCP picks up the new index (no Cursor restart)

| Event | What the MCP does | Cursor |
|---|---|---|
| `./update_index.sh` finishes | Trigger watcher sees `.reload_trigger` (poll ~5s) and re-reads every `knowledge/*/commands.json` | Stays open |
| `git pull` of `knowledge/` only | Auto-update thread hot-reloads JSON in-process | Stays open |
| `git pull` of any `*.py` | MCP process `os._exit(0)`; Cursor respawns the subprocess with new code | Stays open |
| No git remote (local-only checkout) | Git pull is skipped; trigger watcher still runs | Stays open |

Disable with `--no-auto-update` on the MCP argv (also disables the trigger watcher). Interval: `--update-interval HOURS` (default 1; `0` = startup pull only, trigger still watched).

### Cursor MCP config

Leave auto-update on (default). Example stdio args:

```json
{
  "command": "python3",
  "args": ["-m", "ceph_command_kb.server.mcp_server", "--auto-update", "--update-interval", "1"]
}
```

To disable: `"--no-auto-update"`.

## Manual generate (same `--since` contract)

```bash
python3 generate_reference.py --since 2026-08-01 --verbose --force
python3 generate_reference.py --reparse --since 2026-08-01   # last sorted version dir only; needs raw_help/
touch .reload_trigger   # if MCP is already running
```

`--reparse` does **not** walk every version. It takes `sorted(knowledge/)[-1]` (currently tentacle). `knowledge/*/raw_help/` is gitignored, so a fresh clone cannot reparse until you have generated with `--docs` on that machine. `reparse_kb.py` is an older tentacle-only helper — prefer `generate_reference.py --reparse`.

Configs: `import_configs.py --kb-dir knowledge/<version>/` into `configs.json` (separate from command discovery). Default `--kb-dir` is `knowledge/ceph-20.2.1-tentacle`.

## Files that must stay untracked

`.reload_trigger` and `.last_index_update` are gitignored. Do not commit them.

## Troubleshooting

| Symptom | Check |
|---|---|
| MCP still serves old commands after rebuild | Confirm `.reload_trigger` was touched in **this** repo root; wait 5s; `health` / `capabilities` |
| `./update_index.sh` exits immediately | `ceph` not on PATH — generate on a cluster node, copy `knowledge/<version>/` into this repo, then `touch .reload_trigger` |
| Git pull never happens | No `git remote`; trigger path still works for local rebuilds |
| Cursor “MCP disconnected” briefly | Expected only after a `.py` pull; IDE respawns the process |
