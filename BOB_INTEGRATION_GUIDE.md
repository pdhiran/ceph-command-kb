# Integrating Ceph Command KB with Bob Agents

This guide explains how to integrate the Ceph Command Knowledge Base MCP tool with Bob agents (IBM watsonx Code Assistant or similar AI coding assistants).

## Overview

The Ceph Command KB provides three integration methods:
1. **MCP Server (stdio)** - For IDE integrations like Cursor
2. **MCP Server (SSE)** - For Claude Desktop and similar tools
3. **REST API** - For Bob agents, LangChain, CrewAI, CI/CD pipelines, and custom integrations

**For Bob agents, use the REST API integration.**

## Architecture

```
┌─────────────────┐
│   Bob Agent     │
│  (watsonx CAI)  │
└────────┬────────┘
         │ HTTP/REST
         ↓
┌─────────────────────────┐
│ Ceph Command KB         │
│ REST API Server         │
│ (Port 9090)             │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────┐
│ Knowledge Base          │
│ - 1,254 commands        │
│ - 2,660 config params   │
│ - Search indices        │
└─────────────────────────┘
```

## Setup Instructions

### 1. Install the Ceph Command KB

```bash
# Clone the repository
git clone https://github.com/pdhiran/ceph-command-kb.git
cd ceph-command-kb

# Install dependencies
pip install -e .
```

### 2. Start the REST API Server

```bash
# Start on default port 9090
python -m ceph_command_kb.server.rest_api

# Or specify custom host/port
python -m ceph_command_kb.server.rest_api --host 0.0.0.0 --port 9090

# Or specify a different Ceph version
python -m ceph_command_kb.server.rest_api --kb-path knowledge/ceph-19.2.0-squid
```

The server will start and be available at `http://localhost:9090`

### 3. Verify the Server is Running

```bash
curl http://localhost:9090/health
```

Expected response:
```json
{
  "status": "healthy",
  "kb_loaded": true,
  "commands_count": 1254,
  "configs_count": 2660
}
```

## Integration with Bob Agents

### Option A: Direct HTTP Calls from Bob

Bob agents can make direct HTTP requests to the REST API endpoints. Here's how to configure Bob to use the service:

#### Example: Python Integration

```python
import requests
import json

class CephCommandKB:
    def __init__(self, base_url="http://localhost:9090"):
        self.base_url = base_url
    
    def verify_command(self, command, flags=None, arguments=None):
        """Verify a Ceph command exists and is valid."""
        response = requests.post(
            f"{self.base_url}/api/verify_command",
            json={
                "command": command,
                "flags": flags,
                "arguments": arguments
            }
        )
        return response.json()
    
    def search_commands(self, query, limit=20):
        """Search for Ceph commands."""
        response = requests.post(
            f"{self.base_url}/api/search_commands",
            json={"query": query, "limit": limit}
        )
        return response.json()
    
    def verify_config(self, name):
        """Verify a Ceph config parameter."""
        response = requests.post(
            f"{self.base_url}/api/verify_config",
            json={"name": name}
        )
        return response.json()
    
    def review_test(self, script_content):
        """Review a test script for issues."""
        response = requests.post(
            f"{self.base_url}/api/review_test",
            json={"script_content": script_content}
        )
        return response.json()

# Usage in Bob agent
kb = CephCommandKB()

# Verify a command before generating code
result = kb.verify_command("ceph osd pool create mypool 32")
if result["valid"]:
    print("Command is valid!")
else:
    print(f"Issues: {result['issues']}")

# Search for commands
results = kb.search_commands("nfs cluster create")
print(f"Found {len(results['commands'])} matching commands")

# Review a test script
script = """
ceph osd pool create mypool 32
rbd create img --size 1024
"""
review = kb.review_test(script)
print(f"Review: {review}")
```

### Option B: LangChain Tool Integration

```python
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType
from langchain.llms import OpenAI
import requests

def verify_ceph_command(command: str) -> str:
    """Verify a Ceph command against the knowledge base."""
    response = requests.post(
        "http://localhost:9090/api/verify_command",
        json={"command": command}
    )
    return str(response.json())

def search_ceph_commands(query: str) -> str:
    """Search for Ceph commands."""
    response = requests.post(
        "http://localhost:9090/api/search_commands",
        json={"query": query, "limit": 10}
    )
    return str(response.json())

# Create LangChain tools
tools = [
    Tool(
        name="VerifyCephCommand",
        func=verify_ceph_command,
        description="Verify a Ceph command exists and is valid. Input should be the full command string."
    ),
    Tool(
        name="SearchCephCommands",
        func=search_ceph_commands,
        description="Search for Ceph commands by keyword or description. Input should be a search query."
    )
]

# Initialize agent with tools
llm = OpenAI(temperature=0)
agent = initialize_agent(
    tools,
    llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Use the agent
result = agent.run("Find commands for creating NFS clusters in Ceph")
```

### Option C: CrewAI Integration

```python
from crewai import Agent, Task, Crew
from crewai_tools import tool
import requests

@tool("Verify Ceph Command")
def verify_ceph_command(command: str) -> str:
    """Verify a Ceph command against the knowledge base."""
    response = requests.post(
        "http://localhost:9090/api/verify_command",
        json={"command": command}
    )
    return str(response.json())

@tool("Review Ceph Test Script")
def review_ceph_test(script: str) -> str:
    """Review a Ceph test script for issues."""
    response = requests.post(
        "http://localhost:9090/api/review_test",
        json={"script_content": script}
    )
    return str(response.json())

# Create specialized agent
ceph_expert = Agent(
    role='Ceph Storage Expert',
    goal='Generate and verify Ceph automation scripts',
    backstory='Expert in Ceph storage with deep knowledge of CLI commands',
    tools=[verify_ceph_command, review_ceph_test],
    verbose=True
)

# Create task
task = Task(
    description='Create a script to set up a Ceph RBD pool with mirroring',
    agent=ceph_expert,
    expected_output='A validated Ceph script with proper commands'
)

# Execute
crew = Crew(agents=[ceph_expert], tasks=[task])
result = crew.kickoff()
```

## Available REST API Endpoints

### Command Verification (12 endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/verify_command` | POST | Verify command + flags + arguments |
| `/api/find_command` | POST | Look up command by exact name |
| `/api/search_commands` | POST | Search across names and descriptions |
| `/api/list_subcommands` | POST | List subcommands under a prefix |
| `/api/search_flag` | POST | Find commands accepting a flag |
| `/api/search_argument` | POST | Find commands by argument name |
| `/api/get_help` | POST | Get parsed help metadata |
| `/api/get_raw_help` | POST | Get original help text |
| `/api/get_examples` | POST | Get usage examples |
| `/api/list_versions` | GET/POST | List available KB versions |
| `/api/find_binary` | POST | List all commands for a binary |
| `/api/search_keyword` | POST | Search by keyword |

### Config Verification (4 endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/verify_config` | POST | Verify config parameter |
| `/api/search_config` | POST | Search config parameters |
| `/api/get_config_help` | POST | Get full config metadata |
| `/api/list_configs_by_section` | POST | List configs by subsystem |

### Test Validation (2 endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/validate_script` | POST | Quick validation |
| `/api/review_test` | POST | Full review with analysis |

### Health Check

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server health + KB status |

## Usage Examples

### 1. Verify a Command

```bash
curl -X POST http://localhost:9090/api/verify_command \
  -H "Content-Type: application/json" \
  -d '{
    "command": "ceph osd pool create",
    "flags": ["--size"],
    "arguments": ["pool_name", "pg_num"]
  }'
```

Response:
```json
{
  "valid": true,
  "command": "ceph osd pool create",
  "flags_valid": true,
  "arguments_valid": true,
  "metadata": {
    "description": "Create a new pool",
    "flags": [...],
    "arguments": [...]
  }
}
```

### 2. Search Commands

```bash
curl -X POST http://localhost:9090/api/search_commands \
  -H "Content-Type: application/json" \
  -d '{"query": "nfs cluster create", "limit": 5}'
```

### 3. Verify Config Parameter

```bash
curl -X POST http://localhost:9090/api/verify_config \
  -H "Content-Type: application/json" \
  -d '{"name": "osd_pool_default_size"}'
```

Response:
```json
{
  "found": true,
  "name": "osd_pool_default_size",
  "type": "uint",
  "default": "3",
  "description": "Default number of replicas for pools",
  "min": "0",
  "max": "10"
}
```

### 4. Review Test Script

```bash
curl -X POST http://localhost:9090/api/review_test \
  -H "Content-Type: application/json" \
  -d '{
    "script_content": "ceph osd pool create mypool 32\nrbd create img --size 1024\nceph osd pool delete mypool mypool --yes-i-really-really-mean-it"
  }'
```

Response includes:
- Command verification results
- Missing cleanup operations
- Destructive command warnings
- Best practice suggestions

## Running as a Service

### systemd Service

Create `/etc/systemd/system/ceph-command-kb.service`:

```ini
[Unit]
Description=Ceph Command KB REST API
After=network.target

[Service]
Type=simple
User=ceph-kb
WorkingDirectory=/opt/ceph-command-kb
ExecStart=/usr/bin/python3 -m ceph_command_kb.server.rest_api --host 0.0.0.0 --port 9090
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable ceph-command-kb
sudo systemctl start ceph-command-kb
sudo systemctl status ceph-command-kb
```

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install -e .

EXPOSE 9090

CMD ["python", "-m", "ceph_command_kb.server.rest_api", "--host", "0.0.0.0", "--port", "9090"]
```

Build and run:
```bash
docker build -t ceph-command-kb .
docker run -d -p 9090:9090 --name ceph-kb ceph-command-kb
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ceph-command-kb
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ceph-command-kb
  template:
    metadata:
      labels:
        app: ceph-command-kb
    spec:
      containers:
      - name: api
        image: ceph-command-kb:latest
        ports:
        - containerPort: 9090
        livenessProbe:
          httpGet:
            path: /health
            port: 9090
          initialDelaySeconds: 10
          periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: ceph-command-kb
spec:
  selector:
    app: ceph-command-kb
  ports:
  - port: 9090
    targetPort: 9090
  type: ClusterIP
```

## Bob Agent Prompt Examples

When using Bob with the Ceph Command KB, you can use prompts like:

```
"Before generating the Ceph automation script, verify all commands using the Ceph Command KB API at http://localhost:9090"

"Search for NFS-related commands and generate a script to create an NFS cluster"

"Review this test script for Ceph command validity and best practices"

"Verify that the config parameter 'osd_pool_default_size' exists and show its valid range"
```

## Best Practices

1. **Always verify commands** before executing them in production
2. **Use the review_test endpoint** for comprehensive script validation
3. **Check config parameters** before modifying cluster settings
4. **Search before creating** - find existing commands rather than guessing syntax
5. **Monitor the health endpoint** to ensure the KB is loaded correctly
6. **Use appropriate timeouts** for HTTP requests (recommended: 30 seconds)
7. **Cache results** when possible to reduce API calls
8. **Handle errors gracefully** - the API returns structured error messages

## Troubleshooting

### Server won't start
- Check if port 9090 is already in use: `lsof -i :9090`
- Verify Python dependencies are installed: `pip list | grep -E "pyyaml|mcp|uvicorn|starlette"`
- Check knowledge base exists: `ls knowledge/ceph-20.2.1-tentacle/commands.json`

### Commands not found
- Verify the correct KB version is loaded
- Check the command name is exact (case-sensitive)
- Use search_commands to find similar commands

### Slow responses
- The first request loads the KB into memory (may take 2-3 seconds)
- Subsequent requests are fast (< 100ms)
- Consider increasing server resources if handling high load

## Support

- GitHub Issues: https://github.com/pdhiran/ceph-command-kb/issues
- Documentation: See DEVELOPMENT.md for architecture details
- Knowledge Base: Pre-generated for Ceph 20.2.1 (Tentacle)

## License

MIT License - See repository for details