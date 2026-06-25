# Engineering Intelligence MCP Contract

Version: 1.0

This document defines the standard contract that every MCP in the Engineering Intelligence Platform must implement. It enables orchestrators to discover, query, and coordinate multiple specialized knowledge bases.

## Platform Vision

```
                    ┌──────────────────────┐
                    │    Orchestrator       │
                    │    Agent              │
                    └──┬───┬───┬───┬───┬───┘
                       │   │   │   │   │
          ┌────────────┘   │   │   │   └────────────┐
          ▼                ▼   │   ▼                ▼
    ┌───────────┐  ┌─────────┐│┌─────────┐  ┌───────────┐
    │ Command   │  │  Error  │││  Doc    │  │  Release  │
    │ KB MCP    │  │  KB MCP │││  KB MCP │  │  KB MCP   │
    └───────────┘  └─────────┘│└─────────┘  └───────────┘
                       ┌──────┘
                       ▼
                 ┌───────────┐
                 │  Config   │
                 │  KB MCP   │
                 └───────────┘
```

Each MCP is a standalone server that:
- Owns one domain of knowledge
- Exposes domain-specific tools (e.g., `verify_command`, `verify_config`)
- Implements the common contract below for discoverability and interoperability

## Mandatory Tools

Every MCP must expose these tools. They enable orchestrators to discover capabilities and check health without domain-specific knowledge.

### capabilities()

Returns machine-readable description of what this MCP provides.

```json
{
  "name": "Human-readable KB name",
  "description": "What this KB provides",
  "schema_version": "1.0",
  "entity_types": ["command", "config"],
  "operations": ["verify_command", "search_commands", "..."],
  "supported_versions": ["ceph-20.2.1-tentacle"],
  "entity_counts": {
    "commands": 1254,
    "configs": 2660
  }
}
```

Required fields: `name`, `schema_version`, `entity_types`, `operations`.

### health()

Returns operational status.

```json
{
  "status": "ok",
  "kb_loaded": true,
  "search_ready": true,
  "total_entities": 3914,
  "version": "ceph-20.2.1-tentacle",
  "schema_version": "1.0"
}
```

`status` must be one of: `"ok"`, `"degraded"`, `"error"`.

## Entity IDs

Every entity in the platform must have a stable, deterministic ID.

Requirements:
- Same entity always gets the same ID
- IDs are stable across re-indexing (if the entity hasn't changed)
- IDs are unique within an entity type
- Format: 16-character hex hash of `entity_type:name:version`

Example: `make_entity_id("command", "ceph osd pool create")` -> `"a3f7b2c1e9d84f60"`

Entity IDs enable cross-KB references. A Documentation KB can reference `command:a3f7b2c1e9d84f60` without knowing the command name or which KB owns it.

## Recommended Tools

These are not mandatory but should be implemented when applicable.

### search(query, filters)

Generic search across all entity types in this KB. Should delegate to domain-specific search implementations, not duplicate them.

### lookup(entity_id)

Retrieve a single entity by its stable ID. Returns the complete entity with metadata.

### related(entity_id)

Return entities related to the given entity. Relationship types are domain-specific but should use a common format:

```json
{
  "entity_id": "a3f7b2c1e9d84f60",
  "relationships": [
    {
      "type": "parent",
      "target_id": "b4e8c3d2f0a95e71",
      "target_type": "command",
      "target_kb": "command-kb"
    },
    {
      "type": "documentation",
      "target_id": "c5f9d4e3a1b06f82",
      "target_type": "doc_page",
      "target_kb": "doc-kb"
    }
  ]
}
```

### metadata(entity_id)

Return metadata for a specific entity, including provenance, confidence, and indexing information.

## Entity Schema

Every entity should include these common fields alongside domain-specific fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entity_id` | string | Yes | Stable deterministic ID |
| `entity_type` | string | Yes | e.g., "command", "config", "error", "doc" |
| `name` | string | Yes | Human-readable name |
| `description` | string | No | Brief description |
| `version` | string | No | Ceph version this applies to |
| `keywords` | list | No | Searchable keywords |
| `relationships` | list | No | Cross-entity references |

Domain-specific fields (flags, arguments, default values, etc.) are added by each KB.

## Response Format

All tools should return JSON. Error responses should use:

```json
{
  "error": "Description of what went wrong",
  "status": "error"
}
```

Success responses are domain-specific but should include the entity_id when returning entities.

## Implementing a New KB

To add a new Knowledge Base to the platform:

1. Create a new MCP server (Python, using the `mcp` SDK)
2. Implement `capabilities()` and `health()` as mandatory tools
3. Add domain-specific tools (e.g., `search_errors`, `lookup_doc`)
4. Use `make_entity_id()` for stable entity IDs
5. Include `entity_id` in all entity responses
6. Register the MCP in the orchestrator's configuration

### Example: Error Intelligence KB

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Ceph Error Intelligence KB")

@mcp.tool()
def capabilities():
    return {
        "name": "Ceph Error Intelligence KB",
        "schema_version": "1.0",
        "entity_types": ["error", "resolution"],
        "operations": ["search_errors", "lookup_error", "find_resolution", "capabilities", "health"],
        "supported_versions": ["ceph-20.2.1-tentacle"],
    }

@mcp.tool()
def search_errors(query: str):
    """Search for known Ceph errors and their resolutions."""
    ...

@mcp.tool()
def find_resolution(error_id: str):
    """Find resolution steps for a known error."""
    ...
```

## Orchestrator Discovery

An orchestrator discovers MCPs by:

1. Connecting to each configured MCP server
2. Calling `capabilities()` to learn what each MCP provides
3. Building a capability map: entity_type -> MCP
4. Routing queries to the appropriate MCP(s)

Example orchestrator logic:

```
User: "Why is recovery slow on my cluster?"

Orchestrator:
1. capabilities() on each MCP
2. Route to Error KB: search_errors("slow recovery")
3. Route to Config KB: search_config("recovery")
4. Route to Command KB: search_commands("recovery")
5. Aggregate results, let the LLM synthesize an answer
```

## Versioning

- `schema_version`: The contract version (this document). Currently `"1.0"`.
- KB version: The version of the indexed data (e.g., `"ceph-20.2.1-tentacle"`).
- These are independent. A KB can update its data without changing the schema version.

## Future Extensions

The following will be added to the contract when the corresponding KBs are built:

- Cross-KB relationship resolution (lookup entity by ID across all KBs)
- Event streaming (subscribe to KB updates)
- Batch operations (verify multiple entities in one call)
- Confidence scoring (how reliable is this entity's data)
- Provenance tracking (where did this data come from)

These will be added as optional capabilities, preserving backwards compatibility.
