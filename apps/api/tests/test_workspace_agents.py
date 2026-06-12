"""Workspace Agent Definitions + Permissions (v1.1): CRUD, templates,
permission/status lifecycle, and workspace_agent.* events flowing through the
normal event/timeline/replay systems. Definitions are metadata only."""
from __future__ import annotations

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def _workspace(client, **overrides) -> dict:
    body = {"name": "Agent Workspace", "project_id": "proj-1", **overrides}
    response = client.post("/api/runtime/workspaces", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _agent(client, wid, **overrides) -> dict:
    body = {"name": "Planner", "role": "planner", **overrides}
    response = client.post(f"/api/runtime/workspaces/{wid}/agents", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ----------------------------------------------------------------------- CRUD


def test_create_agent_defaults(client):
    wid = _workspace(client)["workspace_id"]
    agent = _agent(client, wid)
    assert agent["agent_id"].startswith("wsagent-")
    assert agent["status"] == "ready"
    assert agent["model_provider"] == "mock"
    # conservative default permission profile, full key set present
    assert agent["permissions"]["can_read_files"] is True
    assert agent["permissions"]["can_write_files"] is False
    assert agent["permissions"]["can_run_commands"] is False
    assert len(agent["permissions"]) == 13
    assert agent["trust_score"] == 1.0
    assert agent["risk_score"] == 0.0


def test_list_and_get_agents(client):
    wid = _workspace(client)["workspace_id"]
    a1 = _agent(client, wid, name="Planner")
    a2 = _agent(client, wid, name="Coder", role="backend")
    listed = client.get(f"/api/runtime/workspaces/{wid}/agents").json()
    assert [a["agent_id"] for a in listed] == [a1["agent_id"], a2["agent_id"]]
    detail = client.get(
        f"/api/runtime/workspaces/{wid}/agents/{a2['agent_id']}"
    ).json()
    assert detail["name"] == "Coder"
    assert client.get(
        f"/api/runtime/workspaces/{wid}/agents/wsagent-nope"
    ).status_code == 404


def test_workspace_agent_count(client):
    wid = _workspace(client)["workspace_id"]
    _agent(client, wid)
    _agent(client, wid, name="Two")
    assert client.get(f"/api/runtime/workspaces/{wid}").json()["agent_count"] == 2


def test_update_agent_metadata(client):
    wid = _workspace(client)["workspace_id"]
    agent = _agent(client, wid)
    patched = client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}",
        json={"name": "Lead Planner", "model_name": "mock:gpt-4.1", "requires_verification": True},
    ).json()
    assert patched["name"] == "Lead Planner"
    assert patched["model_name"] == "mock:gpt-4.1"
    assert patched["requires_verification"] is True


def test_change_permissions(client):
    wid = _workspace(client)["workspace_id"]
    agent = _agent(client, wid)
    patched = client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}",
        json={"permissions": {"can_write_files": True}},
    ).json()
    # partial overlay keeps the full profile, flips just the one flag
    assert patched["permissions"]["can_write_files"] is True
    assert patched["permissions"]["can_read_files"] is True
    assert len(patched["permissions"]) == 13


def test_change_status(client):
    wid = _workspace(client)["workspace_id"]
    agent = _agent(client, wid)
    patched = client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}",
        json={"status": "quarantined"},
    ).json()
    assert patched["status"] == "quarantined"


def test_delete_agent_removes_row_keeps_history(client):
    wid = _workspace(client)["workspace_id"]
    agent = _agent(client, wid)
    aid = agent["agent_id"]
    assert client.delete(f"/api/runtime/workspaces/{wid}/agents/{aid}").status_code == 204
    assert client.get(f"/api/runtime/workspaces/{wid}/agents/{aid}").status_code == 404
    assert client.get(f"/api/runtime/workspaces/{wid}/agents").json() == []
    # the deletion is preserved in the event log
    types = [
        e["event_type"]
        for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    ]
    assert "workspace_agent.deleted" in types


# ------------------------------------------------------------------- validation


def test_invalid_status_rejected(client):
    wid = _workspace(client)["workspace_id"]
    bad = client.post(
        f"/api/runtime/workspaces/{wid}/agents",
        json={"name": "X", "role": "r", "status": "exploded"},
    )
    assert bad.status_code == 422


def test_invalid_permission_key_rejected(client):
    wid = _workspace(client)["workspace_id"]
    bad = client.post(
        f"/api/runtime/workspaces/{wid}/agents",
        json={"name": "X", "role": "r", "permissions": {"can_launch_missiles": True}},
    )
    assert bad.status_code == 422


def test_trust_risk_out_of_range_rejected(client):
    wid = _workspace(client)["workspace_id"]
    bad = client.post(
        f"/api/runtime/workspaces/{wid}/agents",
        json={"name": "X", "role": "r", "risk_score": 5.0},
    )
    assert bad.status_code == 422


# -------------------------------------------------------------------- templates


def test_list_agent_templates(client):
    templates = client.get("/api/runtime/agent-templates").json()
    ids = {t["template_id"] for t in templates}
    assert {
        "planner",
        "ui-agent",
        "backend-coder",
        "researcher",
        "marketing",
        "verifier",
        "safety-reviewer",
    } <= ids
    backend = next(t for t in templates if t["template_id"] == "backend-coder")
    assert backend["permissions"]["can_access_database"] is True
    assert backend["status"] == "caution"
    assert backend["risk_notes"]


def test_create_agent_from_template(client):
    wid = _workspace(client)["workspace_id"]
    created = client.post(
        f"/api/runtime/workspaces/{wid}/agents/from-template/backend-coder", json={}
    )
    assert created.status_code == 201, created.text
    agent = created.json()
    assert agent["role"] == "backend"
    assert agent["status"] == "caution"
    assert agent["permissions"]["can_access_database"] is True
    assert agent["metadata"]["template_id"] == "backend-coder"
    assert agent["metadata"]["future_approval_required"]


def test_create_agent_from_template_with_name_override(client):
    wid = _workspace(client)["workspace_id"]
    agent = client.post(
        f"/api/runtime/workspaces/{wid}/agents/from-template/planner",
        json={"name": "Chief Planner"},
    ).json()
    assert agent["name"] == "Chief Planner"
    assert agent["role"] == "planner"


def test_unknown_template_404(client):
    wid = _workspace(client)["workspace_id"]
    assert client.post(
        f"/api/runtime/workspaces/{wid}/agents/from-template/nope", json={}
    ).status_code == 404


# --------------------------------------------------------------------- events


def test_agent_actions_emit_events(client):
    workspace = _workspace(client)
    wid = workspace["workspace_id"]
    agent = _agent(client, wid)
    aid = agent["agent_id"]
    client.patch(f"/api/runtime/workspaces/{wid}/agents/{aid}", json={"name": "Renamed"})
    client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{aid}",
        json={"permissions": {"can_run_commands": True}},
    )
    client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{aid}", json={"status": "disabled"}
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/agents/from-template/planner", json={}
    )

    activity = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    types = [e["event_type"] for e in activity]  # newest first
    assert types == [
        "workspace_agent.template_instantiated",
        "workspace_agent.status_changed",
        "workspace_agent.permission_changed",
        "workspace_agent.updated",
        "workspace_agent.created",
        "workspace.created",
    ]
    perm = next(e for e in activity if e["event_type"] == "workspace_agent.permission_changed")
    assert perm["payload"]["changed"] == ["can_run_commands"]
    assert perm["metadata"]["source"] == "runtime"
    assert all(e["metadata"]["workspace_id"] == wid for e in activity)


def test_noop_agent_patch_emits_nothing(client):
    wid = _workspace(client)["workspace_id"]
    agent = _agent(client, wid)
    aid = agent["agent_id"]
    client.patch(f"/api/runtime/workspaces/{wid}/agents/{aid}", json={"name": "Planner"})
    types = [
        e["event_type"]
        for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    ]
    assert types == ["workspace_agent.created", "workspace.created"]


def test_agent_events_flow_into_timeline_and_replay(client):
    workspace = _workspace(client)
    wid = workspace["workspace_id"]
    run_id = workspace["activity_run_id"]
    agent = _agent(client, wid)
    client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}",
        json={"status": "running"},
    )

    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    assert timeline == [
        "workspace.created",
        "workspace_agent.created",
        "workspace_agent.status_changed",
    ]
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_agent_writes_require_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/agents-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        created_ws = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers={"X-API-Key": "k1"}
        )
        wid = created_ws.json()["workspace_id"]
        # writes blocked without key
        assert client.post(
            f"/api/runtime/workspaces/{wid}/agents", json={"name": "A", "role": "r"}
        ).status_code == 401
        created = client.post(
            f"/api/runtime/workspaces/{wid}/agents",
            json={"name": "A", "role": "r"},
            headers={"X-API-Key": "k1"},
        )
        assert created.status_code == 201
        aid = created.json()["agent_id"]
        assert client.delete(
            f"/api/runtime/workspaces/{wid}/agents/{aid}"
        ).status_code == 401
        # reads stay open in local mode
        assert client.get(f"/api/runtime/workspaces/{wid}/agents").status_code == 200
        assert client.get("/api/runtime/agent-templates").status_code == 200
