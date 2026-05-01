"""Data models for tenants, users, agents, and MCP registrations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ── SQLAlchemy ORM models (database) ──

from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class TenantORM(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    plan = Column(String, default="free")  # free | pro | enterprise
    api_key_hash = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    config_overrides = Column(JSON, default=dict)


class McpRegistrationORM(Base):
    __tablename__ = "mcp_registrations"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    tenant_id = Column(String, nullable=False, index=True)
    server_name = Column(String, nullable=False)
    server_type = Column(String, default="stdio")  # stdio | sse | http
    command = Column(String, nullable=True)  # for stdio
    args = Column(JSON, default=list)
    env = Column(JSON, default=dict)
    url = Column(String, nullable=True)  # for http/sse
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Pydantic API schemas ──


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9-]{3,50}$")
    plan: str = "free"


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime
    api_key: str | None = None  # only on create


class AgentMessage(BaseModel):
    tenant_id: str
    thread_id: str | None = None
    message: str = Field(..., min_length=1)


class AgentResponse(BaseModel):
    thread_id: str
    reply: str
    tenant_id: str


class McpRegistrationCreate(BaseModel):
    tenant_id: str
    server_name: str = Field(..., pattern=r"^[a-zA-Z0-9_-]{2,64}$")
    server_type: str = "stdio"
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | None = None


class McpRegistrationResponse(BaseModel):
    id: str
    tenant_id: str
    server_name: str
    server_type: str
    command: str | None
    args: list[str]
    url: str | None
    is_enabled: bool
    created_at: datetime
