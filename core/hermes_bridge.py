"""Tenant-isolated Hermes Agent bridge.

Each tenant gets its own Hermes Agent profile directory
with isolated memory, skills, and config. The bridge
proxies messages through Hermes CLI or direct Python API.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from core.config import settings


class HermesBridge:
    """Per-tenant Hermes Agent wrapper.

    Creates an isolated Hermes profile per tenant so memory,
    skills, and config never leak between customers.
    """

    def __init__(self, tenant_id: str, tenant_slug: str):
        self.tenant_id = tenant_id
        self.tenant_slug = tenant_slug
        self.profile_name = f"saas-{tenant_slug}"
        self.profile_dir = (
            Path(settings.hermes_config_dir).expanduser() / self.profile_name
        )

    def provision(self):
        """Create the isolated Hermes profile for this tenant."""
        profile_path = self.profile_dir
        profile_path.mkdir(parents=True, exist_ok=True)

        # Write tenant-specific hermes config
        config = {
            "provider": "ollama-launch",
            "model": settings.ollama_model,
            "ollama_url": settings.ollama_url,
            "memory": {
                "mode": "persistent",
                "backend": "sqlite",
                "path": str(profile_path / "memory.db"),
                "tenant_id": self.tenant_id,
            },
            "tools": {
                "enabled": ["terminal", "file", "web"],
                "mcp_servers": [],
            },
            "personality": "professional-assistant",
            "spawn_depth": 1,
        }

        (profile_path / "config.json").write_text(json.dumps(config, indent=2))

        # Create isolated memory directory
        memory_dir = profile_path / "memory"
        memory_dir.mkdir(exist_ok=True)
        (memory_dir / "AGENTS.md").write_text(
            f"# {self.tenant_slug} — Tenant Context\n\n"
            f"Tenant ID: {self.tenant_id}\n"
            f"Plan: standard\n"
        )

        return self

    def teardown(self):
        """Remove all tenant data."""
        if self.profile_dir.exists():
            shutil.rmtree(self.profile_dir)

    def ask(self, message: str, thread_id: Optional[str] = None) -> dict:
        """Send a message to this tenant's Hermes Agent and get a reply.

        Uses the Hermes CLI with the tenant-specific profile.
        Falls back to direct Ollama API if Hermes CLI is unavailable.
        """
        # Primary path: use Hermes CLI with tenant profile
        try:
            result = subprocess.run(
                ["hermes", "--profile", self.profile_name, "chat", "--message", message],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "HERMES_CONFIG_DIR": str(self.profile_dir.parent)},
            )
            if result.returncode == 0:
                return {"reply": result.stdout.strip(), "source": "hermes-cli"}
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass

        # Fallback: direct Ollama call via httpx
        import httpx

        try:
            resp = httpx.post(
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are a helpful AI assistant for tenant {self.tenant_slug}.",
                        },
                        {"role": "user", "content": message},
                    ],
                    "stream": False,
                },
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("message", {}).get("content", "")
                return {"reply": reply, "source": "ollama-direct"}
        except Exception:
            pass

        return {"reply": "Agent unavailable. Please try again.", "source": "none"}
