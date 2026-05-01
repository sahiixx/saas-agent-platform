"""MCP server registration and lifecycle management.

Each tenant can register their own MCP servers. The platform
resolves which servers are enabled for which tenant and
registers them with the sahiixx-bus MCP gateway.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.models import (
    McpRegistrationCreate,
    McpRegistrationORM,
    McpRegistrationResponse,
    TenantORM,
)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


# ── Local MCP process manager ──

_mcp_processes: dict[str, subprocess.Popen] = {}  # noqa: F821


async def _register_with_bus(server_name: str, server_type: str, command: str | None,
                               args: list[str] | None, url: str | None) -> dict:
    """Register an MCP server with the sahiixx-bus."""
    payload = {
        "name": server_name,
        "transport": server_type,
        "command": command,
        "args": args or [],
        "url": url,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{settings.bus_url}/mcp/register", json=payload)
            if resp.status_code < 300:
                return resp.json()
            return {"status": "error", "detail": f"Bus returned {resp.status_code}"}
    except httpx.RequestError as e:
        return {"status": "error", "detail": str(e)}


@router.post("", response_model=McpRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_mcp_server(body: McpRegistrationCreate, db: Session = Depends(get_db)):
    """Register an MCP server for a tenant."""
    # Validate tenant
    tenant = db.query(TenantORM).filter(TenantORM.id == body.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Check duplicate
    existing = db.query(McpRegistrationORM).filter(
        McpRegistrationORM.tenant_id == body.tenant_id,
        McpRegistrationORM.server_name == body.server_name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"MCP server '{body.server_name}' already registered for this tenant",
        )

    orm = McpRegistrationORM(
        tenant_id=body.tenant_id,
        server_name=body.server_name,
        server_type=body.server_type,
        command=body.command,
        args=body.args,
        env=body.env,
        url=body.url,
    )
    db.add(orm)
    db.commit()
    db.refresh(orm)

    # Register with bus
    await _register_with_bus(body.server_name, body.server_type, body.command, body.args, body.url)

    return McpRegistrationResponse(
        id=orm.id,
        tenant_id=orm.tenant_id,
        server_name=orm.server_name,
        server_type=orm.server_type,
        command=orm.command,
        args=orm.args,
        url=orm.url,
        is_enabled=orm.is_enabled,
        created_at=orm.created_at,
    )


@router.get("", response_model=list[McpRegistrationResponse])
def list_mcp_servers(tenant_id: Optional[str] = None, db: Session = Depends(get_db)):
    """List MCP servers, optionally filtered by tenant."""
    query = db.query(McpRegistrationORM)
    if tenant_id:
        query = query.filter(McpRegistrationORM.tenant_id == tenant_id)
    servers = query.all()
    return [
        McpRegistrationResponse(
            id=s.id, tenant_id=s.tenant_id, server_name=s.server_name,
            server_type=s.server_type, command=s.command, args=s.args,
            url=s.url, is_enabled=s.is_enabled, created_at=s.created_at,
        )
        for s in servers
    ]


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_mcp_server(server_id: str, db: Session = Depends(get_db)):
    """Remove an MCP server registration."""
    orm = db.query(McpRegistrationORM).filter(McpRegistrationORM.id == server_id).first()
    if not orm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")
    db.delete(orm)
    db.commit()
