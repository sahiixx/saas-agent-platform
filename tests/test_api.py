"""API contracts and tenant persistence/isolation without live agent calls."""

import json
from pathlib import Path

import pytest


def create_tenant(client, slug="tenant-one"):
    response = client.post("/api/v1/tenants", json={"name": slug, "slug": slug})
    assert response.status_code == 201
    return response.json()


def test_health_and_root(client):
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["docs"] == "/docs"


def test_create_persists_tenant_and_only_returns_key_on_create(client):
    tenant = create_tenant(client)
    assert tenant["name"] == "tenant-one"
    assert tenant["plan"] == "free"
    assert tenant["is_active"] is True
    assert len(tenant["api_key"]) == 32
    assert tenant["created_at"]

    fetched = client.get(f"/api/v1/tenants/{tenant['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == {**tenant, "api_key": None}
    assert client.get("/api/v1/tenants").json() == [fetched.json()]


@pytest.mark.parametrize("body", [
    {"name": "", "slug": "valid-slug"},
    {"name": "Tenant", "slug": "ab"},
    {"name": "Tenant", "slug": "Invalid Slug"},
    {"slug": "valid-slug"},
])
def test_invalid_tenant_is_not_persisted(client, body):
    assert client.post("/api/v1/tenants", json=body).status_code == 422
    assert client.get("/api/v1/tenants").json() == []


def test_duplicate_slug_does_not_reprovision_existing_profile(client):
    from core.config import settings

    tenant = create_tenant(client)
    profile = Path(settings.hermes_config_dir) / "saas-tenant-one"
    memory = profile / "memory" / "keep.txt"
    memory.write_text("existing tenant memory")
    response = client.post("/api/v1/tenants", json={"name": "Duplicate", "slug": tenant["slug"]})
    assert response.status_code == 409
    assert len(client.get("/api/v1/tenants").json()) == 1
    assert memory.read_text() == "existing tenant memory"
    assert json.loads((profile / "config.json").read_text())["memory"]["tenant_id"] == tenant["id"]


def test_provision_failure_rolls_back_tenant(client, monkeypatch):
    from core.hermes_bridge import HermesBridge

    def fail_provision(self):
        raise OSError("profile storage unavailable")

    monkeypatch.setattr(HermesBridge, "provision", fail_provision)
    response = client.post("/api/v1/tenants", json={"name": "Tenant", "slug": "failed-tenant"})
    assert response.status_code == 500
    assert "Failed to provision agent" in response.json()["detail"]
    assert client.get("/api/v1/tenants").json() == []


def test_profiles_and_deletion_are_isolated_per_tenant(client):
    from core.config import settings

    first = create_tenant(client, "tenant-one")
    second = create_tenant(client, "tenant-two")
    assert first["id"] != second["id"]
    assert first["api_key"] != second["api_key"]
    profiles = Path(settings.hermes_config_dir)
    for tenant in (first, second):
        profile = profiles / f"saas-{tenant['slug']}"
        config = json.loads((profile / "config.json").read_text())
        assert config["memory"]["tenant_id"] == tenant["id"]
        assert config["memory"]["path"] == str(profile / "memory.db")
        assert tenant["id"] in (profile / "memory" / "AGENTS.md").read_text()

    response = client.delete(f"/api/v1/tenants/{first['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert not (profiles / "saas-tenant-one").exists()
    assert (profiles / "saas-tenant-two" / "config.json").exists()
    assert client.get(f"/api/v1/tenants/{first['id']}").status_code == 404
    assert [t["id"] for t in client.get("/api/v1/tenants").json()] == [second["id"]]


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/tenants/missing"),
    ("delete", "/api/v1/tenants/missing"),
    ("get", "/api/v1/agents/missing/status"),
])
def test_missing_tenant_returns_404(client, method, path):
    assert getattr(client, method)(path).status_code == 404


def test_chat_uses_correct_tenant_and_thread(client, monkeypatch):
    from core.hermes_bridge import HermesBridge

    calls = []

    def fake_ask(self, message, thread_id):
        calls.append((self.tenant_id, self.tenant_slug, message, thread_id))
        return {"reply": f"reply for {self.tenant_slug}"}

    monkeypatch.setattr(HermesBridge, "ask", fake_ask)
    for slug in ("tenant-one", "tenant-two"):
        tenant = create_tenant(client, slug)
        response = client.post("/api/v1/agents/chat", json={
            "tenant_id": tenant["id"], "thread_id": f"thread-{slug}", "message": "hello",
        })
        assert response.status_code == 200
        assert response.json() == {
            "tenant_id": tenant["id"], "thread_id": f"thread-{slug}", "reply": f"reply for {slug}",
        }
        assert calls[-1] == (tenant["id"], slug, "hello", f"thread-{slug}")
    assert len(calls) == 2


def test_chat_rejects_missing_and_inactive_tenants_before_provider_call(client):
    from core.database import SessionLocal
    from core.models import TenantORM

    tenant = create_tenant(client)
    with SessionLocal() as db:
        db.query(TenantORM).filter_by(id=tenant["id"]).update({"is_active": False})
        db.commit()

    for tenant_id in ("missing", tenant["id"]):
        response = client.post("/api/v1/agents/chat", json={"tenant_id": tenant_id, "message": "hello"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Active tenant not found"
