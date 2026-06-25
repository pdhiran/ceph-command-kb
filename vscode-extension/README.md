# Ceph Command KB VS Code Extension

VS Code extension that integrates the Ceph Command Knowledge Base for inline command verification, search, and script review. Works with IBM watsonx Code Assistant (Bob) and any VS Code workflow.

## Features

- **Command Search**: Search and insert verified Ceph commands directly into your code
- **Command Verification**: Select a command and verify it against the knowledge base
- **Script Review**: Comprehensive review of test scripts for invalid commands, missing cleanup, and risks
- **Config Verification**: Verify Ceph configuration parameters with type, default, and constraints
- **Inline Diagnostics**: Auto-verify scripts on save with red/yellow squiggly lines for issues
- **Status Bar**: Shows KB connection status and command count

## Prerequisites

The Ceph Command KB REST API must be running:

```bash
cd ceph-command-kb
pip install -e .
python3 -m ceph_command_kb.server.rest_api --port 9090
```

## Installation

### From Source

```bash
cd ceph-command-kb/vscode-extension
npm install
code --install-extension .
```

### Package and Install

```bash
cd ceph-command-kb/vscode-extension
npm install
npm install -g vsce
vsce package
code --install-extension ceph-command-kb-vscode-0.1.0.vsix
```

## Usage

### Search and Insert Commands

1. Press `Cmd+Alt+C` (Mac) / `Ctrl+Alt+C` (Windows/Linux)
2. Enter search query (e.g., "nfs cluster", "rbd mirror", "osd pool")
3. Select a command from the results
4. Command is inserted at your cursor position

### Verify Selected Command

1. Select a Ceph command in your editor
2. Press `Cmd+Alt+V` (Mac) / `Ctrl+Alt+V` (Windows/Linux)
3. Get instant feedback: verified or not found with similar suggestions

### Review Entire Script

1. Open a test script (Python, Shell, YAML)
2. Command Palette (`Cmd+Shift+P`) -> `Ceph KB: Review Script`
3. View findings in the "Ceph KB Review" output channel

### Verify Config Parameter

1. Command Palette -> `Ceph KB: Verify Config`
2. Enter config name (e.g., `osd_pool_default_size`)
3. View type, default value, min/max, description

### Auto-Verify on Save

Enable in VS Code settings:

```json
{
  "ceph-kb.autoVerify": true
}
```

Scripts are automatically checked on save with inline diagnostics.

## Keyboard Shortcuts

| Action | Mac | Windows/Linux |
|--------|-----|---------------|
| Search Commands | `Cmd+Alt+C` | `Ctrl+Alt+C` |
| Verify Command | `Cmd+Alt+V` | `Ctrl+Alt+V` |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `ceph-kb.apiUrl` | `http://localhost:9090` | Ceph Command KB REST API URL |
| `ceph-kb.autoVerify` | `false` | Automatically verify scripts on save |

## Using with IBM watsonx Code Assistant (Bob)

1. Bob generates Ceph commands -> you get AI-generated code
2. Verify with `Cmd+Alt+V` -> instant validation against the KB
3. Search for correct commands with `Cmd+Alt+C` if needed
4. Review full scripts via Command Palette -> `Ceph KB: Review Script`
5. Enable auto-verify to catch issues as you save

## Status Bar

| Display | Meaning |
|---------|---------|
| `Ceph KB (1254 cmds)` | Connected, KB loaded |
| `Ceph KB (offline)` | REST API not running |

Click the status bar item to open command search.
