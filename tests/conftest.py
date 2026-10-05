"""Exercise the API with a disposable database and tenant profiles."""

import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Set these before importing the app so ambient settings cannot select a live DB.
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("HERMES_CONFIG_DIR", str(tmp_path / "profiles"))

    from api.main import app
    from core import database
    from core.config import settings

    engine = create_engine(
        f"sqlite:///{tmp_path / 'tenants.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(settings, "database_url", str(engine.url))
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "hermes_config_dir", str(tmp_path / "profiles"))

    def forbid_external_call(*args, **kwargs):
        raise AssertionError("Tests must not contact providers or launch Hermes/MCP processes")

    monkeypatch.setattr(subprocess, "run", forbid_external_call)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbid_external_call)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbid_external_call)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        engine.dispose()
