"""Agent messaging API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.hermes_bridge import HermesBridge
from core.models import AgentMessage, AgentResponse, TenantORM

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/chat", response_model=AgentResponse)
def agent_chat(body: AgentMessage, db: Session = Depends(get_db)):
    """Send a message to a tenant's Hermes Agent."""
    # Validate tenant exists and is active
    tenant = db.query(TenantORM).filter(
        TenantORM.id == body.tenant_id,
        TenantORM.is_active == True,
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active tenant not found",
        )

    thread_id = body.thread_id or uuid.uuid4().hex

    bridge = HermesBridge(tenant.id, tenant.slug)
    result = bridge.ask(body.message, thread_id)

    return AgentResponse(
        thread_id=thread_id,
        reply=result["reply"],
        tenant_id=tenant.id,
    )


@router.get("/{tenant_id}/status")
def agent_status(tenant_id: str, db: Session = Depends(get_db)):
    """Check if a tenant's agent profile exists and is healthy."""
    tenant = db.query(TenantORM).filter(TenantORM.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    bridge = HermesBridge(tenant.id, tenant.slug)
    profile_exists = bridge.profile_dir.exists()

    return {
        "tenant_id": tenant_id,
        "tenant_slug": tenant.slug,
        "profile_exists": profile_exists,
        "profile_dir": str(bridge.profile_dir),
        "status": "ready" if profile_exists else "not_provisioned",
    }
