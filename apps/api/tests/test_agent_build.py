"""Live Agent Execution — single governed step (v3.0).

The model is patched to return known manifests so these tests prove the
*governed pipeline*, not model quality: a model-proposed file write is routed
through the v1.5 enforcement gateway exactly like a manual write — safe files
land in the sandbox, sensitive paths halt for approval, unsafe paths are
blocked (disk untouched), and a malformed response writes nothing.
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
        database_url=f"sqlite:///{tmp_path}/build.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    app = create_app(settings)
    holder = {"text": "", "status": "completed"}

    async def fake_complete(req):  # patched mock provider
        return ModelResponse(
            provider="mock",
            model_name=req.model_name,
            output_text=holder["text"],
            latency_ms=7,
            status=holder["status"],
            input_tokens=20,
            output_tokens=40,
            error_message="boom" if holder["status"] == "failed" else None,
        )

    app.state.provider_registry.get("mock").complete = fake_complete

    with TestClient(app) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Build WS", "goal": "Build a small site.", "project_id": "p1"},
        ).json()["workspace_id"]
        agent_id = client.post(
            f"/api/runtime/workspaces/{wid}/agents",
            json={"name": "Builder", "role": "UI Agent"},
        ).json()["agent_id"]
        yield client, wid, tmp_path / "workspaces" / wid, agent_id, holder


def _manifest(files, summary="A small site."):
    return json.dumps({"summary": summary, "files": files})


def _build(client, wid, agent_id, **body):
    return client.post(
        f"/api/runtime/workspaces/{wid}/agent-build",
        json={"agent_id": agent_id, **body},
    )


def _activity_types(client, wid):
    return [e["event_type"] for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()]


# --------------------------------------------------------------- happy path


def test_build_writes_safe_files_and_emits_events(env):
    client, wid, root, agent_id, holder = env
    holder["text"] = _manifest([
        {"path": "index.html", "content": "<!doctype html><h1>Hi</h1>"},
        {"path": "styles.css", "content": "h1{color:teal}"},
    ])
    out = _build(client, wid, agent_id).json()
    assert out["status"] == "completed"
    assert out["written"] == 2
    assert {f["path"]: f["status"] for f in out["files"]} == {
        "index.html": "written", "styles.css": "written",
    }
    # files really landed in the sandbox
    assert (root / "index.html").read_text() == "<!doctype html><h1>Hi</h1>"
    assert (root / "styles.css").exists()
    types = _activity_types(client, wid)
    for expected in (
        "model.called", "model.completed", "agent.build.started",
        "action.proposed", "enforcement.allowed", "sandbox.file.created",
        "agent.build.completed",
    ):
        assert expected in types
    # and it's now previewable
    assert client.get(f"/api/runtime/workspaces/{wid}/preview-status").json()["previewable"] is True


def test_build_tolerates_markdown_fenced_json(env):
    client, wid, root, agent_id, holder = env
    holder["text"] = "Sure!\n```json\n" + _manifest(
        [{"path": "index.html", "content": "<h1>ok</h1>"}]
    ) + "\n```\n"
    out = _build(client, wid, agent_id).json()
    assert out["status"] == "completed" and out["written"] == 1
    assert (root / "index.html").exists()


# ------------------------------------------------------ governance applies


def test_sensitive_file_halts_for_approval_others_written(env):
    client, wid, root, agent_id, holder = env
    holder["text"] = _manifest([
        {"path": "index.html", "content": "<h1>store</h1>"},
        {"path": "src/payment/checkout.js", "content": "// stripe glue"},
    ])
    out = _build(client, wid, agent_id).json()
    assert out["written"] == 1
    assert out["halted_for_approval"] == 1
    by_path = {f["path"]: f["status"] for f in out["files"]}
    assert by_path["index.html"] == "written"
    assert by_path["src/payment/checkout.js"] == "halted_for_approval"
    # the safe file landed; the sensitive one did NOT
    assert (root / "index.html").exists()
    assert not (root / "src" / "payment").exists()
    # a real approval was created for the held write
    pending = client.get(f"/api/runtime/workspaces/{wid}/approvals", params={"status": "pending"}).json()
    assert len(pending) == 1
    assert pending[0]["target"] == "src/payment/checkout.js"
    assert "enforcement.approval_required" in _activity_types(client, wid)


def test_unsafe_paths_blocked_disk_untouched(env):
    client, wid, root, agent_id, holder = env
    holder["text"] = _manifest([
        {"path": "index.html", "content": "<h1>ok</h1>"},
        {"path": "../escape.html", "content": "nope"},
        {"path": ".env", "content": "API_KEY=sk-zzz"},
    ])
    out = _build(client, wid, agent_id).json()
    assert out["written"] == 1
    assert out["blocked"] == 2
    assert not (root.parent / "escape.html").exists()
    assert not (root / ".env").exists()
    statuses = {f["path"]: f["status"] for f in out["files"]}
    assert statuses["../escape.html"] == "blocked"
    assert statuses[".env"] == "blocked"


def test_quarantined_agent_cannot_build(env):
    client, wid, root, agent_id, holder = env
    client.post(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine",
        json={"reason": "test", "requested_by": "me"},
    )
    holder["text"] = _manifest([{"path": "index.html", "content": "<h1>x</h1>"}])
    response = _build(client, wid, agent_id)
    assert response.status_code == 409
    assert not (root / "index.html").exists()


# ----------------------------------------------------- failure / safety


def test_malformed_response_writes_nothing(env):
    client, wid, root, agent_id, holder = env
    holder["text"] = "Sorry, I can't produce JSON right now. Here is some prose."
    out = _build(client, wid, agent_id).json()
    assert out["status"] == "failed"
    assert out["written"] == 0
    assert not any(root.iterdir())
    assert "agent.build.failed" in _activity_types(client, wid)


def test_failed_model_call_writes_nothing(env):
    client, wid, root, agent_id, holder = env
    holder["status"] = "failed"
    holder["text"] = ""
    out = _build(client, wid, agent_id).json()
    assert out["status"] == "failed"
    assert "model.failed" in _activity_types(client, wid)
    assert "agent.build.failed" in _activity_types(client, wid)


def test_no_secrets_or_host_paths_in_build_events(env):
    client, wid, root, agent_id, holder = env
    holder["text"] = _manifest([{"path": ".env", "content": "API_KEY=sk-deadbeef1234567890"}])
    _build(client, wid, agent_id)
    activity = str(client.get(f"/api/runtime/workspaces/{wid}/activity").json())
    assert "sk-deadbeef1234567890" not in activity
    assert str(root) not in activity


def test_build_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/build-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    app = create_app(settings)

    async def fake_complete(req):
        return ModelResponse(provider="mock", model_name=req.model_name,
                             output_text=_manifest([{"path": "index.html", "content": "<h1>x</h1>"}]),
                             latency_ms=1, status="completed")

    app.state.provider_registry.get("mock").complete = fake_complete
    with TestClient(app) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post("/api/runtime/workspaces", json={"name": "W", "goal": "g"}, headers=h).json()["workspace_id"]
        agent_id = client.post(f"/api/runtime/workspaces/{wid}/agents", json={"name": "B", "role": "UI"}, headers=h).json()["agent_id"]
        assert client.post(f"/api/runtime/workspaces/{wid}/agent-build", json={"agent_id": agent_id}).status_code == 401
        assert client.post(f"/api/runtime/workspaces/{wid}/agent-build", json={"agent_id": agent_id}, headers=h).status_code == 200
