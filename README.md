# SaaS Agent Platform

Multi-tenant AI agent SaaS platform built on Hermes Agent + MCP Servers.

## Quick Start

```bash
# Create venv
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Start the bus
cd ../sahiixx-bus
source .venv/bin/activate
python -c "from sahiixx_bus.server import app; import uvicorn; uvicorn.run(app, host='127.0.0.1', port=9000)"

# Start the platform
cd ../saas-agent-platform
uv run uvicorn api.main:app --reload --port 8080
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/tenants` | Create tenant (auto-provisions Hermes profile) |
| GET | `/api/v1/tenants` | List all tenants |
| GET | `/api/v1/tenants/{id}` | Get tenant details |
| DELETE | `/api/v1/tenants/{id}` | Delete tenant + all data |
| POST | `/api/v1/agents/chat` | Send message to tenant's agent |
| GET | `/api/v1/agents/{id}/status` | Check agent profile health |
| POST | `/api/v1/mcp` | Register MCP server for tenant |
| GET | `/api/v1/mcp` | List MCP servers |
| DELETE | `/api/v1/mcp/{id}` | Unregister MCP server |
| GET | `/health` | Health check |

## Example: Create tenant + chat

```bash
# Create tenant
curl -X POST http://localhost:8080/api/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "slug": "acme-corp", "plan": "pro"}'

# Chat with tenant's agent
curl -X POST http://localhost:8080/api/v1/agents/chat \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "<id-from-above>", "message": "What is the capital of France?"}'
```

## Architecture

```
┌─────────────────────────────────────────┐
│  FastAPI Platform (port 8080)           │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Tenants  │ │ Agents   │ │ MCP      │  │
│  │ API      │ │ API      │ │ Registry │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       │            │            │         │
│       ▼            ▼            ▼         │
│  ┌─────────┐ ┌────────────┐ ┌──────────┐ │
│  │  SQLite  │ │ Hermes    │ │ sahiixx  │ │
│  │  (multi  │ │ Bridge    │ │ Bus MCP  │ │
│  │  tenant) │ │ (per-     │ │ Gateway  │ │
│  │          │ │  tenant)  │ │          │ │
│  └─────────┘ └────────────┘ └────┬─────┘ │
└───────────────────────────────────┼───────┘
                                    │
                                    ▼
                             ┌──────────┐
                             │ Ollama   │
                             │ (local)  │
                             │ or       │
                             │ Cloud LLM│
                             └──────────┘
```
