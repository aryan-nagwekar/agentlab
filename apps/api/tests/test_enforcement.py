"""Action Enforcement Gateway (v1.5): proposals, deterministic policy
evaluation with matched-rule recording, decision events, integration with
files/commands/workflows (blocked actions never execute; existing v1.2/v1.3
safety stays as defense in depth), redaction, and replay reconstruction.

v1.5 boundary: approval_required / quarantine_triggered / rerouted / retry
decisions are recorded as events only — no approval inbox, no validators,
no real quarantine, no autonomous execution."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/enf.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Enforced WS", "goal": "Test enforcement.", "project_id": "p1"},
        ).json()["workspace_id"]
        client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
        yield client, wid, tmp_path / "workspaces" / wid


def _propose(client, wid, **body):
    return client.post(f"/api/runtime/workspaces/{wid}/actions/propose", json=body)


def _activity(client, wid):
    return client.get(f"/api/runtime/workspaces/{wid}/activity").json()


def _types(client, wid):
    return [e["event_type"] for e in _activity(client, wid)]


def _add_agent(client, wid, name, role, status="ready", risk=None):
    agent = client.post(
        f"/api/runtime/workspaces/{wid}/agents", json={"name": name, "role": role}
    ).json()
    patch = {}
    if status != "ready":
        patch["status"] = status
    if patch:
        client.patch(f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}", json=patch)
    if risk is not None:
        # risk_score is engine-derived in real flows; tests set it directly.
        client.patch(
            f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}",
            json={"metadata": {"test": True}},
        )
    return agent["agent_id"]


# ------------------------------------------------------- generic propose API


def test_propose_allow_records_decision_and_events(env):
    client, wid, _ = env
    response = _propose(client, wid, action_type="file.write", target="notes/draft.md")
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["status"] == "allowed"
    decision = out["decision"]
    assert decision["decision"] == "allow"
    assert decision["matched_rules"] == [{"id": "allow-file-write", "name": "Allow safe sandbox writes"}]
    assert decision["reason"]
    types = _types(client, wid)
    for expected in ("action.proposed", "policy.rule.matched", "policy.evaluated", "enforcement.allowed"):
        assert expected in types
    # the generic API never executes: nothing landed on disk
    allowed = next(e for e in _activity(client, wid) if e["event_type"] == "enforcement.allowed")
    assert allowed["payload"]["execution_allowed"] is True


def test_propose_without_evaluate_then_evaluate(env):
    client, wid, _ = env
    out = _propose(client, wid, action_type="file.read", target="a.txt", evaluate=False).json()
    assert out["status"] == "proposed"
    assert out["decision"] is None
    evaluated = client.post(
        f"/api/runtime/workspaces/{wid}/actions/{out['action_id']}/evaluate"
    ).json()
    assert evaluated["status"] == "allowed"
    assert evaluated["decision"]["decision"] == "allow"
    again = client.post(f"/api/runtime/workspaces/{wid}/actions/{out['action_id']}/evaluate")
    assert again.status_code == 409


def test_block_decision_for_traversal_and_secret_file(env):
    client, wid, root = env
    blocked = _propose(client, wid, action_type="file.write", target="../escape.txt").json()
    assert blocked["status"] == "blocked"
    assert blocked["decision"]["decision"] == "block"
    assert blocked["decision"]["matched_rules"][0]["id"] == "block-path-escape"
    secret = _propose(client, wid, action_type="file.read", target=".env").json()
    assert secret["decision"]["matched_rules"][0]["id"] == "block-secret-file"
    assert "enforcement.blocked" in _types(client, wid)
    assert not (root.parent / "escape.txt").exists()


def test_protected_action_requires_approval_and_does_not_execute(env):
    client, wid, _ = env
    out = _propose(
        client, wid, action_type="payment.modify", target="checkout flow",
        input_summary="switch payment provider",
    ).json()
    assert out["status"] == "approval_required"
    assert out["decision"]["decision"] == "require_human_approval"
    assert out["decision"]["matched_rules"][0]["id"] == "approval-protected-action"
    types = _types(client, wid)
    assert "enforcement.approval_required" in types
    # recorded as pending future approval; nothing resolves or executes it
    assert "action.started" not in types
    fetched = client.get(f"/api/runtime/workspaces/{wid}/actions/{out['action_id']}").json()
    assert fetched["status"] == "approval_required"


def test_unverified_research_reroutes(env):
    client, wid, _ = env
    out = _propose(
        client, wid, action_type="data.save", target="suppliers",
        metadata={"unverified_research": True},
    ).json()
    assert out["status"] == "rerouted"
    assert out["decision"]["decision"] == "reroute_to_verifier"
    assert "enforcement.rerouted" in _types(client, wid)
    assert "action.started" not in _types(client, wid)


def test_disabled_and_quarantined_actors_blocked(env):
    client, wid, _ = env
    disabled = _add_agent(client, wid, "Dead Agent", "Backend Coder", status="disabled")
    quarantined = _add_agent(client, wid, "Q Agent", "Researcher", status="quarantined")
    for agent_id in (disabled, quarantined):
        out = _propose(
            client, wid, action_type="file.write", target="ok.txt",
            actor_type="agent", agent_id=agent_id,
        ).json()
        assert out["status"] == "blocked"
        assert out["decision"]["matched_rules"][0]["id"] == "block-unassignable-actor"
        assert out["decision"]["trust_score_before"] is not None


def test_suspicious_actor_mutating_action_downgraded(env):
    client, wid, _ = env
    suspicious = _add_agent(client, wid, "Sus", "UI Engineer", status="suspicious")
    out = _propose(
        client, wid, action_type="file.write", target="page.tsx",
        actor_type="agent", agent_id=suspicious,
    ).json()
    assert out["decision"]["decision"] == "downgrade_permissions"
    assert "enforcement.permissions_downgraded" in _types(client, wid)
    # read-only inspection stays available for caution-tier actors
    caution = _add_agent(client, wid, "Careful", "UI Engineer", status="caution")
    read = _propose(
        client, wid, action_type="file.read", target="page.tsx",
        actor_type="agent", agent_id=caution,
    ).json()
    assert read["decision"]["decision"] == "allow_readonly"
    assert read["status"] == "allowed"


def test_flagged_task_result_gated_for_agents_not_users(env):
    client, wid, _ = env
    _add_agent(client, wid, "Planner", "Planner")
    _add_agent(client, wid, "Backend", "Backend Coder")
    researcher = _add_agent(client, wid, "Researcher", "Researcher")
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    tasks = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()
    backend_task = next(t for t in tasks if t["title"] == "Build the backend")
    assert backend_task["requires_approval"] is True

    # agent actor recording a flagged result → approval_required, no execution
    gated = _propose(
        client, wid, action_type="task.result_record", target=backend_task["task_id"],
        actor_type="agent", agent_id=researcher, task_id=backend_task["task_id"],
    ).json()
    assert gated["status"] == "approval_required"
    assert gated["decision"]["matched_rules"][0]["id"] == "approval-flagged-task-result"

    # validation-flagged (not approval) task → reroute for non-verifier agents
    research_task = next(t for t in tasks if t["title"] == "Research the domain")
    rerouted = _propose(
        client, wid, action_type="task.result_record", target=research_task["task_id"],
        actor_type="agent", agent_id=researcher, task_id=research_task["task_id"],
    ).json()
    assert rerouted["decision"]["decision"] == "reroute_to_verifier"


def test_unknown_action_type_blocked_by_default(env):
    client, wid, _ = env
    out = _propose(client, wid, action_type="warp.core.eject", target="x").json()
    assert out["status"] == "blocked"
    assert out["decision"]["matched_rules"][0]["id"] == "block-unknown-action"


def test_high_risk_publish_requires_approval(env):
    client, wid, _ = env
    out = _propose(
        client, wid, action_type="final_output.publish", target="storefront",
        sensitivity_level="high",
    ).json()
    assert out["status"] == "approval_required"
    normal = _propose(
        client, wid, action_type="final_output.publish", target="draft"
    ).json()
    assert normal["status"] == "allowed"


def test_secrets_redacted_in_proposals_decisions_events(env):
    client, wid, _ = env
    secret = "sk-abcdef1234567890SECRET"
    out = _propose(
        client, wid, action_type="message.send", target="agent-b",
        input_summary=f"use key {secret} for the call",
    ).json()
    # blocked by the secret rule, and the secret never survives anywhere
    assert out["decision"]["matched_rules"][0]["id"] == "block-secret-in-input"
    assert secret not in str(out)
    assert "[redacted]" in out["input_summary"]
    assert secret not in str(_activity(client, wid))
    assert secret not in str(
        client.get(f"/api/runtime/workspaces/{wid}/enforcement/decisions").json()
    )


def test_no_host_paths_in_enforcement_events(env):
    client, wid, root = env
    _propose(client, wid, action_type="file.write", target="../escape.txt")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "ok.txt", "content": "fine"},
    )
    assert str(root) not in str(_activity(client, wid))


# ------------------------------------------------------- integrated surfaces


def test_file_write_allowed_path_proceeds_with_full_event_arc(env):
    client, wid, root = env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/app.py", "content": "print('hi')"},
    )
    assert response.status_code == 200
    assert (root / "src" / "app.py").read_text() == "print('hi')"
    types = _types(client, wid)
    for expected in (
        "action.proposed", "policy.evaluated", "enforcement.allowed",
        "action.started", "sandbox.file.created", "action.completed",
    ):
        assert expected in types


def test_file_traversal_blocked_by_gateway_before_execution(env):
    client, wid, root = env
    before = sorted(p.name for p in root.rglob("*"))
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "../../pwn.txt", "content": "nope"},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("blocked (traversal)")
    assert sorted(p.name for p in root.rglob("*")) == before
    types = _types(client, wid)
    assert "enforcement.blocked" in types
    assert "sandbox.file.blocked" in types  # legacy parity audit
    assert "action.started" not in types


def test_sensitive_file_write_requires_approval_and_does_not_execute(env):
    client, wid, root = env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "// stripe glue"},
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail.startswith("approval required (approval-sensitive-file)")
    assert "v1.6" in detail
    assert not (root / "src" / "payment").exists()
    types = _types(client, wid)
    assert "enforcement.approval_required" in types
    assert "action.started" not in types


def test_command_allowed_path_proceeds_through_v13_safety(env):
    client, wid, _ = env
    result = client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "pwd", "args": []},
    ).json()
    assert result["status"] == "completed"
    types = _types(client, wid)
    assert "enforcement.allowed" in types  # gateway decision (allow_sandbox_only)
    assert "sandbox.command.completed" in types  # v1.3 runner still audited
    allowed = next(e for e in _activity(client, wid) if e["event_type"] == "enforcement.allowed")
    assert allowed["payload"]["decision"] == "allow_sandbox_only"


def test_command_dangerous_blocked_by_gateway_before_execution(env):
    client, wid, root = env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "sh", "args": ["-c", "touch PWNED"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("blocked (dangerous_command)")
    assert not (root / "PWNED").exists()
    types = _types(client, wid)
    assert "enforcement.blocked" in types
    assert "sandbox.command.blocked" in types  # legacy parity audit
    assert "sandbox.command.started" not in types


def test_command_missing_manifest_yields_retry_decision(env):
    client, wid, _ = env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "npm", "args": ["test"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("blocked (missing_manifest)")
    types = _types(client, wid)
    assert "enforcement.retry_required" in types
    assert "sandbox.command.started" not in types


def test_workflow_start_and_result_are_enforced_metadata_actions(env):
    client, wid, _ = env
    _add_agent(client, wid, "Planner", "Planner")
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    started = client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/start")
    assert started.status_code == 200
    tasks = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()
    running = next(t for t in tasks if t["status"] == "running")
    recorded = client.post(
        f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{running['task_id']}/result",
        json={"output": "done"},
    )
    assert recorded.status_code == 201
    activity = _activity(client, wid)
    enforced_types = {
        e["payload"].get("action_type")
        for e in activity
        if e["event_type"] == "enforcement.allowed"
    }
    assert "workflow.start" in enforced_types
    assert "task.result_record" in enforced_types


# ------------------------------------------------------ listing / replay / auth


def test_decisions_listing_and_policies_endpoint(env):
    client, wid, _ = env
    _propose(client, wid, action_type="file.write", target="a.txt")
    _propose(client, wid, action_type="file.write", target="../bad")
    decisions = client.get(f"/api/runtime/workspaces/{wid}/enforcement/decisions").json()
    assert len(decisions) == 2
    assert {d["decision"] for d in decisions} == {"allow", "block"}
    assert all(d["matched_rules"] and d["reason"] for d in decisions)
    assert decisions[0]["action_type"] == "file.write"

    policies = client.get("/api/runtime/policies").json()
    ids = [p["id"] for p in policies]
    assert ids == sorted(ids, key=lambda i: next(p["priority"] for p in policies if p["id"] == i))
    assert "block-path-escape" in ids
    assert all(p["reason"] and p["decision"] for p in policies)


def test_enforcement_decisions_appear_in_timeline_and_replay(env):
    client, wid, _ = env
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    _propose(client, wid, action_type="auth.modify", target="login flow")
    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    for expected in (
        "action.proposed", "policy.rule.matched", "policy.evaluated",
        "enforcement.approval_required",
    ):
        assert expected in timeline
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_propose_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/enf-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers={"X-API-Key": "k1"}
        ).json()["workspace_id"]
        body = {"action_type": "file.read", "target": "a.txt"}
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/actions/propose", json=body
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/actions/propose",
                json=body,
                headers={"X-API-Key": "k1"},
            ).status_code
            == 201
        )
        # reads stay open in local mode
        assert client.get(f"/api/runtime/workspaces/{wid}/actions").status_code == 200
        assert (
            client.get(
                f"/api/runtime/workspaces/{wid}/enforcement/decisions"
            ).status_code
            == 200
        )
        assert client.get("/api/runtime/policies").status_code == 200
