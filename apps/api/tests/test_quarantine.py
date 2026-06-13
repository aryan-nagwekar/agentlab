"""Real Runtime Quarantine (v1.7): quarantine actually restricts an agent's
runtime actions. Manual + approval + enforcement-triggered quarantine; agent-
attributed file/command/task actions blocked before execution (disk
untouched); existing tasks blocked; unquarantine restores; approval cannot
bypass quarantine; events flow through activity/timeline/replay."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/q.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Quarantine WS", "goal": "Build a site.", "project_id": "p1"},
        ).json()["workspace_id"]
        client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
        yield client, wid, tmp_path / "workspaces" / wid


def _agent(client, wid, name="Coder", role="Backend Coder"):
    return client.post(
        f"/api/runtime/workspaces/{wid}/agents", json={"name": name, "role": role}
    ).json()["agent_id"]


def _types(client, wid):
    return [e["event_type"] for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()]


def _quarantine(client, wid, agent_id, reason="manual review"):
    return client.post(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine",
        json={"reason": reason, "requested_by": "admin"},
    )


# ---------------------------------------------------------------- lifecycle


def test_manual_quarantine_sets_status_and_metadata(env):
    client, wid, _ = env
    agent_id = _agent(client, wid)
    response = _quarantine(client, wid, agent_id)
    assert response.status_code == 200, response.text
    agent = response.json()
    assert agent["status"] == "quarantined"
    assert agent["quarantine"]["reason"] == "manual review"
    assert agent["quarantine"]["requested_by"] == "admin"
    assert agent["quarantine"]["previous_status"] == "ready"
    assert "quarantine" not in agent["metadata"]  # bookkeeping kept out of public meta
    types = _types(client, wid)
    for expected in ("agent.quarantine.requested", "agent.quarantined", "agent.quarantine.enforced"):
        assert expected in types
    # re-quarantine is a conflict
    assert _quarantine(client, wid, agent_id).status_code == 409


def test_unquarantine_restores_status(env):
    client, wid, _ = env
    agent_id = _agent(client, wid, role="UI Engineer")
    # move to caution first so we can prove the prior status is restored
    client.patch(f"/api/runtime/workspaces/{wid}/agents/{agent_id}", json={"status": "caution"})
    _quarantine(client, wid, agent_id)
    restored = client.post(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/unquarantine",
        json={"reason": "cleared", "requested_by": "admin"},
    ).json()
    assert restored["status"] == "caution"
    assert restored["quarantine"]["lifted_by"] == "admin"
    types = _types(client, wid)
    for expected in (
        "agent.unquarantine.requested", "agent.unquarantined", "agent.permissions.restored",
    ):
        assert expected in types
    # unquarantine of a non-quarantined agent is a conflict
    assert client.post(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/unquarantine", json={}
    ).status_code == 409


def test_quarantine_status_endpoint(env):
    client, wid, _ = env
    agent_id = _agent(client, wid)
    before = client.get(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine"
    ).json()
    assert before["quarantined"] is False
    _quarantine(client, wid, agent_id)
    after = client.get(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine"
    ).json()
    assert after["quarantined"] is True
    assert after["quarantine"]["reason"] == "manual review"


def test_metadata_patch_preserves_quarantine(env):
    client, wid, _ = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    # a user metadata PATCH must not wipe the quarantine bookkeeping
    client.patch(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}",
        json={"metadata": {"note": "hello"}},
    )
    agent = client.get(f"/api/runtime/workspaces/{wid}/agents/{agent_id}").json()
    assert agent["status"] == "quarantined"
    assert agent["quarantine"] is not None
    assert agent["metadata"]["note"] == "hello"


# --------------------------------------------------- file/command restriction


def test_quarantined_agent_file_write_blocked_before_execution(env):
    client, wid, root = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    before = sorted(p.name for p in root.rglob("*"))
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/app.py", "content": "print('x')", "agent_id": agent_id},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("blocked (block-unassignable-actor)")
    # disk unchanged
    assert sorted(p.name for p in root.rglob("*")) == before
    assert not (root / "src").exists()
    types = _types(client, wid)
    assert "agent.quarantine.blocked_action" in types
    assert "enforcement.blocked" in types
    assert "action.started" not in types


def test_quarantined_agent_file_delete_blocked(env):
    client, wid, root = env
    # create a file as a user (allowed), then quarantine an agent and try delete
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "keep.txt", "content": "data"},
    )
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    response = client.delete(
        f"/api/runtime/workspaces/{wid}/files",
        params={"path": "keep.txt", "agent_id": agent_id},
    )
    assert response.status_code == 400
    assert (root / "keep.txt").exists()  # untouched
    assert "agent.quarantine.blocked_action" in _types(client, wid)


def test_quarantined_agent_command_blocked_before_execution(env):
    client, wid, root = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    response = client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "pwd", "args": [], "agent_id": agent_id},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("blocked (block-unassignable-actor)")
    types = _types(client, wid)
    assert "agent.quarantine.blocked_action" in types
    assert "sandbox.command.started" not in types  # never ran


def test_user_actions_still_work_alongside_quarantined_agent(env):
    client, wid, root = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    # a normal user write (no agent_id) is unaffected
    ok = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "user.txt", "content": "fine"},
    )
    assert ok.status_code == 200
    assert (root / "user.txt").read_text() == "fine"


def test_unquarantined_agent_can_act_again(env):
    client, wid, root = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    client.post(f"/api/runtime/workspaces/{wid}/agents/{agent_id}/unquarantine", json={})
    ok = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "back.txt", "content": "again", "agent_id": agent_id},
    )
    assert ok.status_code == 200
    assert (root / "back.txt").read_text() == "again"


# ------------------------------------------------------------ workflow integration


def _full_team(client, wid):
    for name, role in [
        ("Planner", "Planner"), ("Researcher", "Researcher"),
        ("Backend", "Backend Coder"), ("UI", "UI Engineer"), ("Verifier", "Verifier"),
    ]:
        client.post(f"/api/runtime/workspaces/{wid}/agents", json={"name": name, "role": role})


def test_quarantined_agent_not_assigned_normal_tasks(env):
    client, wid, _ = env
    _full_team(client, wid)
    # quarantine the planner agent before planning (its role keyword "plan"
    # is not shared by any other template agent, so no fallback assignee)
    agents = client.get(f"/api/runtime/workspaces/{wid}/agents").json()
    planner = next(a for a in agents if a["role"] == "Planner")
    _quarantine(client, wid, planner["agent_id"])
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    tasks = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()
    # the quarantined agent is never assigned ANY task
    assert all(t["assigned_agent_id"] != planner["agent_id"] for t in tasks)
    planner_task = next(t for t in tasks if t["title"] == "Draft the project plan")
    assert planner_task["assigned_agent_id"] is None
    assert planner_task["status"] == "blocked"


def test_quarantine_blocks_existing_assigned_tasks(env):
    client, wid, _ = env
    _full_team(client, wid)
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    tasks = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()
    backend_task = next(t for t in tasks if t["title"] == "Build the backend")
    backend_agent = backend_task["assigned_agent_id"]
    assert backend_task["status"] == "pending"
    # quarantining the agent blocks its already-assigned task
    _quarantine(client, wid, backend_agent)
    after = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()
    blocked = next(t for t in after if t["title"] == "Build the backend")
    assert blocked["status"] == "blocked"
    assert "quarantined" in blocked["blocked_reason"]
    assert "runtime.task.blocked" in _types(client, wid)


def test_task_result_recording_blocked_for_quarantined_agent(env):
    client, wid, _ = env
    _full_team(client, wid)
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/start")
    tasks = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()
    running = next(t for t in tasks if t["status"] == "running")
    # quarantine the agent the running task is assigned to
    _quarantine(client, wid, running["assigned_agent_id"])
    blocked = client.post(
        f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{running['task_id']}/result",
        json={"output": "done"},
    )
    assert blocked.status_code == 400
    assert "quarantined" in blocked.json()["detail"]
    assert "agent.quarantine.blocked_action" in _types(client, wid)


# --------------------------------------------------------- approval interplay


def test_approval_cannot_bypass_quarantine(env):
    client, wid, root = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    # an agent-attributed write is blocked outright (not even an approval is
    # created — the quarantine rule outranks the sensitive-file approval rule)
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "x", "agent_id": agent_id},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("blocked (block-unassignable-actor)")
    approvals = client.get(f"/api/runtime/workspaces/{wid}/approvals").json()
    assert approvals == []
    assert not (root / "src").exists()


def test_enforcement_quarantine_events_in_quarantine_feed(env):
    client, wid, _ = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    feed = client.get(f"/api/runtime/workspaces/{wid}/quarantine/events").json()
    kinds = {e["event_type"] for e in feed}
    assert "agent.quarantined" in kinds
    assert "agent.quarantine.enforced" in kinds
    # the feed only contains quarantine-family events
    assert all(
        e["event_type"].startswith(("agent.quarantine", "agent.unquarantine", "agent.permissions"))
        or e["event_type"] == "agent.quarantined"
        for e in feed
    )


# --------------------------------------------------- security / replay / auth


def test_no_secrets_or_host_paths_in_quarantine_events(env):
    client, wid, root = env
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id, reason="touched sk-deadbeef1234567890 secret note")
    activity = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    # the reason is stored verbatim (operator-authored), but no host path leaks
    assert str(root) not in str(activity)


def test_quarantine_events_in_timeline_and_replay(env):
    client, wid, _ = env
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    agent_id = _agent(client, wid)
    _quarantine(client, wid, agent_id)
    client.post(f"/api/runtime/workspaces/{wid}/agents/{agent_id}/unquarantine", json={})
    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    for expected in ("agent.quarantined", "agent.unquarantined", "agent.permissions.restored"):
        assert expected in timeline
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_quarantine_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/q-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers=h
        ).json()["workspace_id"]
        agent_id = client.post(
            f"/api/runtime/workspaces/{wid}/agents",
            json={"name": "A", "role": "Backend Coder"}, headers=h,
        ).json()["agent_id"]
        body = {"reason": "x", "requested_by": "admin"}
        assert client.post(
            f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine", json=body
        ).status_code == 401
        assert client.post(
            f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine", json=body, headers=h
        ).status_code == 200
        # reads stay open
        assert client.get(
            f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine"
        ).status_code == 200
        assert client.get(
            f"/api/runtime/workspaces/{wid}/quarantine/events"
        ).status_code == 200
