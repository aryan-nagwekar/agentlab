"""Pause/Resume the bounded agent loop on approval (v3.2).

When a step hits an approval-required action, the loop PAUSES (the run is
persisted as awaiting_approval) instead of ending. Once the human resolves the
approval through the normal v1.6 flow — approve writes the held action, deny
keeps it blocked — the loop RESUMES from the next step, with the resolution
folded into the prompt. The model is patched to scripted step manifests so
these tests prove the pause/resume state machine, not model quality.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_gateway import ModelResponse


def _step(files=None, commands=None, done=False, summary="step", status="completed"):
    return {
        "text": json.dumps(
            {"summary": summary, "done": done, "files": files or [], "commands": commands or []}
        ),
        "status": status,
    }


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/resume.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    app = create_app(settings)
    # Scripted responses consumed in order across BOTH the run and resume calls
    # (the counter is NOT reset between requests — that's the point of resume).
    holder = {"responses": [], "i": 0, "default": _step(done=True, summary="done")}

    async def fake_complete(req):
        idx = holder["i"]
        holder["i"] += 1
        resp = holder["responses"][idx] if idx < len(holder["responses"]) else holder["default"]
        status = resp.get("status", "completed")
        return ModelResponse(
            provider="mock", model_name=req.model_name, output_text=resp.get("text", ""),
            latency_ms=5, status=status, input_tokens=10, output_tokens=20,
            error_message="boom" if status == "failed" else None,
        )

    app.state.provider_registry.get("mock").complete = fake_complete

    with TestClient(app) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Resume WS", "goal": "Build a small site.", "project_id": "p1"},
        ).json()["workspace_id"]
        agent_id = client.post(
            f"/api/runtime/workspaces/{wid}/agents",
            json={"name": "Builder", "role": "Backend Coder"},
        ).json()["agent_id"]
        yield client, wid, tmp_path / "workspaces" / wid, agent_id, holder


def _run(client, wid, agent_id, **body):
    return client.post(
        f"/api/runtime/workspaces/{wid}/agent-run", json={"agent_id": agent_id, **body}
    )


def _resume(client, wid, run_id):
    return client.post(f"/api/runtime/workspaces/{wid}/agent-run/{run_id}/resume", json={})


def _resolve(client, wid, approval_id, decision="approve"):
    return client.post(
        f"/api/runtime/workspaces/{wid}/approvals/{approval_id}/{decision}",
        json={"resolved_by": "tester"},
    )


def _activity_types(client, wid):
    return [e["event_type"] for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()]


# the canonical halting step: one safe file + one sensitive payment file
_HALTING = _step(
    files=[
        {"path": "index.html", "content": "<h1>store</h1>"},
        {"path": "src/payment/checkout.js", "content": "// stripe glue"},
    ]
)


# ---------------------------------------------------------------- pause


def test_pause_persists_resumable_state(env):
    client, wid, root, agent_id, holder = env
    holder["responses"] = [_HALTING, _step(done=True)]
    holder["i"] = 0
    out = _run(client, wid, agent_id).json()

    assert out["status"] == "awaiting_approval"
    assert out["resumable"] is True
    assert out["stop_reason"] == "halted_for_approval"
    assert len(out["pending_approval_ids"]) == 1
    run_id = out["run_id"]
    # GET reflects the same persisted state
    state = client.get(f"/api/runtime/workspaces/{wid}/agent-run/{run_id}").json()
    assert state["status"] == "awaiting_approval"
    assert state["run_id"] == run_id
    assert "runtime.agent_run.paused" in _activity_types(client, wid)


def test_resume_blocked_while_approval_pending(env):
    client, wid, root, agent_id, holder = env
    holder["responses"] = [_HALTING, _step(done=True)]
    holder["i"] = 0
    run_id = _run(client, wid, agent_id).json()["run_id"]
    # No approval resolved yet → resume is refused.
    resp = _resume(client, wid, run_id)
    assert resp.status_code == 409
    assert "still pending" in resp.json()["detail"]


# ---------------------------------------------------------------- resume


def test_resume_after_approve_writes_held_file_and_continues(env):
    client, wid, root, agent_id, holder = env
    holder["responses"] = [
        _HALTING,
        _step(files=[{"path": "styles.css", "content": "h1{color:teal}"}], done=True),
    ]
    holder["i"] = 0
    run = _run(client, wid, agent_id).json()
    run_id = run["run_id"]
    approval_id = run["pending_approval_ids"][0]

    # Approve through the normal v1.6 flow → the held write executes now.
    assert _resolve(client, wid, approval_id, "approve").status_code == 200
    assert (root / "src" / "payment" / "checkout.js").exists()

    out = _resume(client, wid, run_id).json()
    assert out["status"] == "completed"
    assert out["stop_reason"] == "done"
    # the held payment outcome was reconciled to "approved"
    step0 = out["steps"][0]
    statuses = {f["path"]: f["status"] for f in step0["files"]}
    assert statuses["src/payment/checkout.js"] == "approved"
    # the loop continued: step 1 ran and wrote styles.css
    assert len(out["steps"]) == 2
    assert (root / "styles.css").exists()
    types = _activity_types(client, wid)
    assert "runtime.agent_run.resumed" in types
    assert "runtime.agent_run.completed" in types


def test_resume_after_deny_keeps_blocked_and_continues(env):
    client, wid, root, agent_id, holder = env
    holder["responses"] = [
        _HALTING,
        _step(files=[{"path": "styles.css", "content": "body{}"}], done=True),
    ]
    holder["i"] = 0
    run = _run(client, wid, agent_id).json()
    run_id = run["run_id"]
    approval_id = run["pending_approval_ids"][0]

    assert _resolve(client, wid, approval_id, "deny").status_code == 200
    assert not (root / "src" / "payment").exists()

    out = _resume(client, wid, run_id).json()
    assert out["status"] == "completed"
    step0 = out["steps"][0]
    statuses = {f["path"]: f["status"] for f in step0["files"]}
    assert statuses["src/payment/checkout.js"] == "denied"
    assert (root / "styles.css").exists()


def test_resume_can_pause_again_then_finish(env):
    client, wid, root, agent_id, holder = env
    holder["responses"] = [
        _step(files=[{"path": "a.html", "content": "<h1>a</h1>"},
                     {"path": "src/auth/login.js", "content": "// auth"}]),
        _step(files=[{"path": "b.html", "content": "<h1>b</h1>"},
                     {"path": "src/payment/pay.js", "content": "// pay"}]),
        _step(done=True),
    ]
    holder["i"] = 0

    # First pause on the auth file.
    run = _run(client, wid, agent_id).json()
    run_id = run["run_id"]
    assert run["status"] == "awaiting_approval"
    _resolve(client, wid, run["pending_approval_ids"][0], "approve")

    # Resume → second step halts on the payment file → pauses again.
    out2 = _resume(client, wid, run_id).json()
    assert out2["status"] == "awaiting_approval"
    assert out2["stop_reason"] == "halted_for_approval"
    assert len(out2["steps"]) == 2
    _resolve(client, wid, out2["pending_approval_ids"][0], "approve")

    # Resume again → final done step → completed.
    out3 = _resume(client, wid, run_id).json()
    assert out3["status"] == "completed"
    assert (root / "src" / "auth" / "login.js").exists()
    assert (root / "src" / "payment" / "pay.js").exists()
    assert _activity_types(client, wid).count("runtime.agent_run.resumed") == 2


def test_resume_unknown_run_404(env):
    client, wid, root, agent_id, holder = env
    assert _resume(client, wid, "arun-nope").status_code == 404
    assert client.get(f"/api/runtime/workspaces/{wid}/agent-run/arun-nope").status_code == 404


def test_resume_non_awaiting_run_409(env):
    client, wid, root, agent_id, holder = env
    holder["responses"] = [_step(files=[{"path": "index.html", "content": "<h1>x</h1>"}], done=True)]
    holder["i"] = 0
    run_id = _run(client, wid, agent_id).json()["run_id"]
    # The run completed (no approval) → cannot resume.
    resp = _resume(client, wid, run_id)
    assert resp.status_code == 409
    assert "not awaiting approval" in resp.json()["detail"]


def test_resume_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/resume-auth.db",
        api_keys="k1", cors_origins="", workspaces_root=str(tmp_path / "ws"),
    )
    app = create_app(settings)

    async def fake_complete(req):
        return ModelResponse(provider="mock", model_name=req.model_name,
                             output_text=_step(done=True)["text"], latency_ms=1, status="completed")

    app.state.provider_registry.get("mock").complete = fake_complete
    with TestClient(app) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post("/api/runtime/workspaces", json={"name": "W", "goal": "g"}, headers=h).json()["workspace_id"]
        aid = client.post(f"/api/runtime/workspaces/{wid}/agents", json={"name": "B", "role": "UI"}, headers=h).json()["agent_id"]
        run_id = client.post(f"/api/runtime/workspaces/{wid}/agent-run", json={"agent_id": aid}, headers=h).json()["run_id"]
        assert client.post(f"/api/runtime/workspaces/{wid}/agent-run/{run_id}/resume", json={}).status_code == 401
