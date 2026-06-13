"""Human Approval System (v1.6): approval_required enforcement decisions
create pending approvals; approve resumes the exact stored action through the
existing safe executors (with v1.2/v1.3 safety re-running); deny/cancel block;
reroute/quarantine record events/metadata only (no real quarantine); secrets
and host paths never leak into approval summaries/events."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/apr.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Approval WS", "goal": "Test approvals.", "project_id": "p1"},
        ).json()["workspace_id"]
        client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
        yield client, wid, tmp_path / "workspaces" / wid


def _approvals(client, wid, **params):
    return client.get(f"/api/runtime/workspaces/{wid}/approvals", params=params).json()


def _activity_types(client, wid):
    return [e["event_type"] for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()]


def _resolve(client, wid, approval_id, action, **body):
    return client.post(
        f"/api/runtime/workspaces/{wid}/approvals/{approval_id}/{action}", json=body
    )


# ---------------------------------------------------------------- creation


def test_sensitive_write_creates_pending_approval(env):
    client, wid, root = env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "// stripe"},
    )
    assert response.status_code == 403
    approvals = _approvals(client, wid)
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["status"] == "pending"
    assert approval["action_type"] == "file.write"
    assert approval["target"] == "src/payment/checkout.ts"
    assert approval["matched_policy_rules"][0]["id"] == "approval-sensitive-file"
    assert approval["risk_level"] == "high"
    assert approval["plain_english_summary"]
    assert approval["recommended_decision"] in approval["options"]
    assert "approval.requested" in _activity_types(client, wid)
    # not executed yet
    assert not (root / "src" / "payment").exists()


def test_approval_id_in_response_detail(env):
    client, wid, _ = env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "config/auth.py", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    assert approval_id in response.json()["detail"]


def test_no_duplicate_pending_approval_for_same_action(env):
    client, wid, _ = env
    for _ in range(3):
        client.post(
            f"/api/runtime/workspaces/{wid}/files/write",
            json={"path": "src/payment/checkout.ts", "content": "// v"},
        )
    pending = _approvals(client, wid, status="pending")
    assert len(pending) == 1
    assert client.get(
        f"/api/runtime/workspaces/{wid}/approvals/pending-count"
    ).json()["pending"] == 1


def test_list_and_detail(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/auth/login.ts", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    detail = client.get(f"/api/runtime/workspaces/{wid}/approvals/{approval_id}").json()
    assert detail["approval_id"] == approval_id
    assert detail["technical_summary"].startswith("action_type=file.write")
    assert client.get(
        f"/api/runtime/workspaces/{wid}/approvals/apr-nope"
    ).status_code == 404


# -------------------------------------------------------------- resolution


def test_approve_resumes_exact_stored_file_write(env):
    client, wid, root = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "// the exact stored content"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    resolved = _resolve(client, wid, approval_id, "approve", resolved_by="alice").json()
    assert resolved["status"] == "approved"
    assert resolved["execution_status"] == "executed"
    assert resolved["resolved_by"] == "alice"
    # the EXACT stored content was written
    assert (root / "src" / "payment" / "checkout.ts").read_text() == "// the exact stored content"
    types = _activity_types(client, wid)
    for expected in (
        "approval.approved", "action.started", "sandbox.file.created",
        "action.completed", "approval.execution_resumed",
    ):
        assert expected in types


def test_deny_file_write_leaves_disk_unchanged(env):
    client, wid, root = env
    before = sorted(p.name for p in root.rglob("*"))
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "// nope"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    denied = _resolve(client, wid, approval_id, "deny", resolved_by="bob",
                      reason="too risky").json()
    assert denied["status"] == "denied"
    assert denied["resolution_reason"] == "too risky"
    assert sorted(p.name for p in root.rglob("*")) == before
    assert not (root / "src" / "payment").exists()
    types = _activity_types(client, wid)
    assert "approval.denied" in types
    assert "approval.execution_resumed" not in types


def test_double_resolution_is_conflict(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "deploy/config.yml", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    assert _resolve(client, wid, approval_id, "deny").status_code == 200
    assert _resolve(client, wid, approval_id, "approve").status_code == 409


def test_cancel_pending_approval(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/auth/login.ts", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    cancelled = _resolve(client, wid, approval_id, "cancel", resolved_by="me").json()
    assert cancelled["status"] == "cancelled"
    assert "approval.cancelled" in _activity_types(client, wid)


# ------------------------------------------------------------- commands


def test_approve_resumes_command_through_v13_safety(env):
    client, wid, root = env
    (root / "auth").mkdir()
    (root / "auth" / "note.txt").write_text("hi")
    # cat of a sensitive-path file passes v1.3 safety but trips the sensitive
    # -command approval rule.
    response = client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "cat", "args": ["auth/note.txt"]},
    )
    assert response.status_code == 403
    approval = _approvals(client, wid)[0]
    assert approval["action_type"] == "command.run"
    resolved = _resolve(client, wid, approval["approval_id"], "approve").json()
    assert resolved["execution_status"] == "executed"
    types = _activity_types(client, wid)
    assert "sandbox.command.completed" in types  # v1.3 runner actually ran
    assert "approval.execution_resumed" in types


def test_deny_command_does_not_execute_marker(env):
    client, wid, root = env
    (root / "payment").mkdir()
    response = client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "ls", "args": ["payment"]},
    )
    assert response.status_code == 403
    approval_id = _approvals(client, wid)[0]["approval_id"]
    _resolve(client, wid, approval_id, "deny")
    types = _activity_types(client, wid)
    assert "sandbox.command.completed" not in types
    assert "approval.denied" in types


# -------------------------------------------------- readonly / reroute / quarantine


def test_approve_readonly_skips_when_no_safe_readonly_path(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    resolved = _resolve(client, wid, approval_id, "approve-readonly").json()
    assert resolved["status"] == "approved"
    assert resolved["execution_status"] == "skipped"
    assert "no safe read-only" in resolved["execution_detail"]
    types = _activity_types(client, wid)
    assert "approval.override_used" in types
    assert "approval.execution_skipped" in types


def test_reroute_records_event_without_autonomous_action(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "deploy/k8s.yml", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    resolved = _resolve(client, wid, approval_id, "reroute",
                        reason="send to verifier").json()
    assert resolved["status"] == "rerouted"
    types = _activity_types(client, wid)
    assert "approval.reroute_requested" in types
    assert "approval.override_used" in types
    # no execution happened
    assert "approval.execution_resumed" not in types


def test_quarantine_records_metadata_only_no_real_quarantine(env):
    client, wid, _ = env
    agent_id = client.post(
        f"/api/runtime/workspaces/{wid}/agents",
        json={"name": "Risky", "role": "Backend Coder"},
    ).json()["agent_id"]
    # propose a protected action by the agent so the approval carries agent_id
    proposed = client.post(
        f"/api/runtime/workspaces/{wid}/actions/propose",
        json={"action_type": "payment.modify", "target": "checkout",
              "actor_type": "agent", "agent_id": agent_id},
    ).json()
    approval_id = proposed["metadata"]["approval_id"]
    resolved = _resolve(client, wid, approval_id, "quarantine",
                        reason="repeated risk").json()
    assert resolved["status"] == "quarantine_requested"
    types = _activity_types(client, wid)
    assert "approval.quarantine_requested" in types
    assert "enforcement.quarantine_triggered" in types
    # the agent definition is NOT actually restricted (real quarantine is v1.7)
    agent = client.get(f"/api/runtime/workspaces/{wid}/agents/{agent_id}").json()
    assert agent["status"] == "ready"


# ----------------------------------------------- security / replay / auth


def test_secrets_redacted_in_approval(env):
    client, wid, _ = env
    secret = "sk-deadbeef1234567890LEAK"
    # propose with a secret in the input → blocked by secret rule, but verify
    # that even an approval-required action with a sensitive arg stays clean.
    proposed = client.post(
        f"/api/runtime/workspaces/{wid}/actions/propose",
        json={"action_type": "deployment.modify", "target": "deploy",
              "input_summary": f"token {secret}"},
    ).json()
    # secret rule outranks; ensure no approval leaked the secret anywhere
    assert secret not in str(proposed)
    assert secret not in str(_approvals(client, wid))
    assert secret not in str(client.get(
        f"/api/runtime/workspaces/{wid}/activity").json())


def test_no_host_paths_in_approval_events(env):
    client, wid, root = env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/auth/login.ts", "content": "x"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    _resolve(client, wid, approval_id, "approve")
    activity = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    assert str(root) not in str(activity)


def test_approval_events_in_timeline_and_replay(env):
    client, wid, _ = env
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/pay.ts", "content": "// pay"},
    )
    approval_id = _approvals(client, wid)[0]["approval_id"]
    _resolve(client, wid, approval_id, "approve")
    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    for expected in ("approval.requested", "approval.approved", "approval.execution_resumed"):
        assert expected in timeline
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_resolution_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/apr-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers=h
        ).json()["workspace_id"]
        client.post(f"/api/runtime/workspaces/{wid}/sandbox/init", headers=h)
        client.post(
            f"/api/runtime/workspaces/{wid}/files/write",
            json={"path": "src/auth/x.ts", "content": "x"},
            headers=h,
        )
        approval_id = client.get(
            f"/api/runtime/workspaces/{wid}/approvals", headers=h
        ).json()[0]["approval_id"]
        # resolution is a write — gated
        assert _resolve(client, wid, approval_id, "approve").status_code == 401
        assert client.post(
            f"/api/runtime/workspaces/{wid}/approvals/{approval_id}/approve",
            json={}, headers=h,
        ).status_code == 200
        # reads stay open
        assert client.get(f"/api/runtime/workspaces/{wid}/approvals").status_code == 200
        assert client.get(
            f"/api/runtime/workspaces/{wid}/approvals/pending-count"
        ).status_code == 200
