"""Workspace templates (v3.3): one-click REAL workspace setup.

A workspace template materializes a real workspace + agent team + goal +
sandbox — but writes NO files (unlike the bottle-shop demo). The agents build
for real only when the user runs a build afterward.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/wt.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        yield client, tmp_path / "workspaces"


def test_list_workspace_templates(env):
    client, _root = env
    templates = client.get("/api/runtime/workspace-templates").json()
    ids = {t["template_id"] for t in templates}
    assert {"storefront-team", "landing-page-team", "web-app-team"} <= ids
    storefront = next(t for t in templates if t["template_id"] == "storefront-team")
    assert storefront["goal"]
    assert storefront["agent_count"] == len(storefront["agent_roles"]) == 6
    assert "UI Agent" in storefront["agent_roles"]


def test_create_from_template_builds_a_real_workspace(env):
    client, root = env
    out = client.post(
        "/api/runtime/workspace-templates/storefront-team/create", json={}
    )
    assert out.status_code == 201, out.text
    ws = out.json()
    wid = ws["workspace_id"]
    assert ws["name"] == "Storefront Team"
    assert ws["goal"]  # the template's goal was applied
    assert ws["metadata"]["workspace_template"] == "storefront-team"

    # A real agent team was materialized on the local default model.
    agents = client.get(f"/api/runtime/workspaces/{wid}/agents").json()
    assert len(agents) == 6
    assert all(a["model_provider"] == "ollama" for a in agents)
    assert all(a["model_name"] == "qwen2.5-coder" for a in agents)

    # The sandbox was initialized, but NO files were written — nothing is canned.
    status = client.get(f"/api/runtime/workspaces/{wid}/sandbox/status").json()
    assert status["file_count"] == 0
    assert not any((root / wid).iterdir())  # empty sandbox dir on disk

    # The setup is ordinary workspace history (events), and the agent team shows up.
    types = [e["event_type"] for e in client.get(
        f"/api/runtime/workspaces/{wid}/activity").json()]
    assert "workspace.created" in types
    assert "sandbox.initialized" in types
    assert types.count("workspace_agent.template_instantiated") == 6


def test_create_from_template_with_overrides(env):
    client, _root = env
    ws = client.post(
        "/api/runtime/workspace-templates/landing-page-team/create",
        json={"name": "My Landing Page", "goal": "Build a landing page for a coffee brand."},
    ).json()
    assert ws["name"] == "My Landing Page"
    assert ws["goal"] == "Build a landing page for a coffee brand."
    agents = client.get(f"/api/runtime/workspaces/{ws['workspace_id']}/agents").json()
    assert len(agents) == 4


def test_unknown_template_404(env):
    client, _root = env
    assert client.post(
        "/api/runtime/workspace-templates/nope/create", json={}
    ).status_code == 404


def test_create_from_template_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/wt-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        # listing is open; creating is gated
        assert client.get("/api/runtime/workspace-templates").status_code == 200
        assert client.post(
            "/api/runtime/workspace-templates/web-app-team/create", json={}
        ).status_code == 401
        assert client.post(
            "/api/runtime/workspace-templates/web-app-team/create",
            json={}, headers={"X-API-Key": "k1"},
        ).status_code == 201
