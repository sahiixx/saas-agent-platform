"""Tenant management API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.hermes_bridge import HermesBridge
from core.models import TenantCreate, TenantORM, TenantResponse

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(body: TenantCreate, db: Session = Depends(get_db)):
    """Create a new tenant with isolated Hermes profile and API key."""
    # Check slug uniqueness
    existing = db.query(TenantORM).filter(TenantORM.slug == body.slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant slug '{body.slug}' already exists",
        )

    tenant_id = uuid.uuid4().hex
    api_key = uuid.uuid4().hex

    orm = TenantORM(
        id=tenant_id,
        name=body.name,
        slug=body.slug,
        plan=body.plan,
        api_key_hash=api_key,  # Note: hash in production
    )
    db.add(orm)
    db.commit()
    db.refresh(orm)

    # Provision isolated Hermes profile
    try:
        bridge = HermesBridge(tenant_id, body.slug)
        bridge.provision()
    except Exception as e:
        db.delete(orm)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision agent: {e}",
        )

    return TenantResponse(
        id=tenant_id,
        name=orm.name,
        slug=orm.slug,
        plan=orm.plan,
        is_active=orm.is_active,
        created_at=orm.created_at,
        api_key=api_key,
    )


@router.get("", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)):
    """List all tenants."""
    tenants = db.query(TenantORM).all()
    return [
        TenantResponse(
            id=t.id, name=t.name, slug=t.slug,
            plan=t.plan, is_active=t.is_active,
            created_at=t.created_at,
        )
        for t in tenants
    ]


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Get a single tenant."""
    t = db.query(TenantORM).filter(TenantORM.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse(
        id=t.id, name=t.name, slug=t.slug,
        plan=t.plan, is_active=t.is_active,
        created_at=t.created_at,
    )


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(tenant_id: str, db: Session = Depends(get_db)):
    """Delete a tenant and all associated data."""
    t = db.query(TenantORM).filter(TenantORM.id == tenant_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Tear down agent profile
    try:
        bridge = HermesBridge(tenant_id, t.slug)
        bridge.teardown()
    except Exception:
        pass

    db.delete(t)
    db.commit()
