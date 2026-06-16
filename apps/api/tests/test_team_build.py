"""Team Build (v3.4): Goal -> Team.

The orchestrator plans + assigns; each agent then builds its part through the
SAME governed pipeline, sharing one sandbox. The mock provider is patched to
return role-appropriate output (a file manifest for writers, text for the rest),
so these tests prove the GOVERNED MULTI-AGENT pipeline — not model quality.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_gateway import ModelResponse


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/team.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    app = create_app(settings)
    holder = {"writer_files": [{"path": "index.html", "content": "<!doctype html><h1>Team</h1>"}]}

    async def fake_complete(req):
        # Writers get a JSON file manifest; everyone else gets plain text.
        if "Focus on your role" in (req.system_prompt or ""):
            text = json.dumps({"summary": "my part", "files": holder["writer_files"]})
        else:
            text = "Here is my contribution as the agent on this team."
        return ModelResponse(
            provider="mock", model_name=req.model_name, output_text=text,
            latency_ms=5, status="completed", input_tokens=10, output_tokens=20,
        )

    app.state.provider_registry.get("mock").complete = fake_complete

    with TestClient(app) as client:
        yield client, tmp_path / "workspaces", holder


def _team_from_template(client, template="storefront-team"):
    # Use a workspace template to materialize a full agent team, then point it at
    # the keyless mock model so the test needs no real keys.
    wid = client.post(
        f"/api/runtime/workspace-templates/{template}/create", json={}
    ).json()["workspace_id"]
    for a in client.get(f"/api/runtime/workspaces/{wid}/agents").json():
        client.patch(
            f"/api/runtime/workspaces/{wid}/agents/{a['agent_id']}",
            json={"model_provider": "mock", "model_name": "mock:claude-sonnet"},
        )
    return wid


def _activity_types(client, wid):
    return [
        e["event_type"]
        for e in client.get(
            f"/api/runtime/workspaces/{wid}/activity", params={"limit": 500}
        ).json()
    ]


# ----------------------------------------------------------- happy path


def test_team_build_plans_and_each_agent_contributes(env):
    client, root, _holder = env
    wid = _team_from_template(client)
    out = client.post(f"/api/runtime/workspaces/{wid}/team-build", json={}).json()

    assert out["status"] == "completed"
    assert out["workflow_id"].startswith("wf-")
    # the 5-step plan assigned all roles in this team
    assert out["step_count"] == 5
    roles = [s["role"] for s in out["steps"]]
    kinds = {s["role"]: s["kind"] for s in out["steps"]}
    # writers (UI/backend) build files; the rest contribute text
    assert kinds.get("frontend") == "build"
    assert any(k == "build" for k in kinds.values())
    assert any(k == "contribute" for k in kinds.values())
    # files were actually written, through the governed pipeline
    assert out["total_written"] >= 1
    assert (root / wid / "index.html").exists()

    types = _activity_types(client, wid)
    for expected in (
        "runtime.team_build.started", "runtime.workflow.created", "runtime.task.assigned",
        "model.called", "model.completed", "runtime.team_build.step",
        "action.proposed", "enforcement.allowed", "sandbox.file.created",
        "runtime.team_build.completed",
    ):
        assert expected in types, f"missing {expected}"
    # the site is previewable
    assert client.get(f"/api/runtime/workspaces/{wid}/preview-status").json()["previewable"]


def test_team_build_runs_validators_on_written_files(env):
    client, _root, holder = env
    holder["writer_files"] = [
        {"path": "index.html", "content": "<!doctype html><h1>ok</h1>"},
        {"path": "data.json", "content": "{\"items\": [1, 2, 3]}"},
    ]
    wid = _team_from_template(client)
    out = client.post(f"/api/runtime/workspaces/{wid}/team-build", json={}).json()
    # a writer step ran code_syntax/secret_exposure on its files
    val_events = [t for t in _activity_types(client, wid) if t.startswith("validator.")]
    assert val_events
    writer_steps = [s for s in out["steps"] if s["kind"] == "build"]
    assert any(s["validations"] for s in writer_steps)


# ----------------------------------------------------- governance applies


def test_team_build_halts_cleanly_on_sensitive_file(env):
    client, root, holder = env
    holder["writer_files"] = [
        {"path": "index.html", "content": "<h1>store</h1>"},
        {"path": "src/payment/checkout.js", "content": "// stripe glue"},
    ]
    wid = _team_from_template(client)
    out = client.post(f"/api/runtime/workspaces/{wid}/team-build", json={}).json()
    assert out["stop_reason"] == "halted_for_approval"
    assert out["total_held"] >= 1
    # the sensitive file was NOT written; a real approval is waiting
    assert not (root / wid / "src" / "payment").exists()
    pending = client.get(
        f"/api/runtime/workspaces/{wid}/approvals", params={"status": "pending"}
    ).json()
    assert any(p["target"] == "src/payment/checkout.js" for p in pending)
    assert "enforcement.approval_required" in _activity_types(client, wid)


def test_no_assignable_agents_fails_cleanly(env):
    client, _root, _holder = env
    # a workspace with a goal but no agents -> the plan can assign nothing
    wid = client.post(
        "/api/runtime/workspaces", json={"name": "Empty", "goal": "Build a site."}
    ).json()["workspace_id"]
    out = client.post(f"/api/runtime/workspaces/{wid}/team-build", json={}).json()
    assert out["status"] == "failed"
    assert out["step_count"] == 0
    assert out["stop_reason"] == "no_assignable_agents"


def test_team_build_requires_goal(env):
    client, _root, _holder = env
    wid = client.post("/api/runtime/workspaces", json={"name": "NoGoal"}).json()["workspace_id"]
    assert client.post(f"/api/runtime/workspaces/{wid}/team-build", json={}).status_code == 400


def test_team_build_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/team-auth.db",
        api_keys="k1", cors_origins="", workspaces_root=str(tmp_path / "ws"),
    )
    app = create_app(settings)

    async def fake_complete(req):
        return ModelResponse(provider="mock", model_name=req.model_name,
                             output_text="text", latency_ms=1, status="completed")

    app.state.provider_registry.get("mock").complete = fake_complete
    with TestClient(app) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W", "goal": "g"}, headers=h
        ).json()["workspace_id"]
        assert client.post(f"/api/runtime/workspaces/{wid}/team-build", json={}).status_code == 401
        assert client.post(
            f"/api/runtime/workspaces/{wid}/team-build", json={}, headers=h
        ).status_code == 200
