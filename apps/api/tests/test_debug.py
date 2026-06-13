"""Visual Project Debugging aggregation (v1.9): deterministic, read-only
summary/issues/project-map derived from existing models + events. Verifies
health states, recommended actions, issue derivation, the lite project map,
no state mutation, and that no secrets/host paths leak into the summary."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/dbg.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Debug WS", "goal": "Build a small site.", "project_id": "p1"},
        ).json()["workspace_id"]
        yield client, wid, tmp_path / "workspaces" / wid


def _summary(client, wid):
    return client.get(f"/api/runtime/workspaces/{wid}/debug/summary").json()


def _issues(client, wid):
    return client.get(f"/api/runtime/workspaces/{wid}/debug/issues").json()


def _add_agent(client, wid, name, role, status="ready"):
    a = client.post(
        f"/api/runtime/workspaces/{wid}/agents", json={"name": name, "role": role}
    ).json()
    if status != "ready":
        client.patch(
            f"/api/runtime/workspaces/{wid}/agents/{a['agent_id']}", json={"status": status}
        )
    return a["agent_id"]


# ---------------------------------------------------------------- health


def test_no_signals_on_fresh_workspace(env):
    client, wid, _ = env
    summary = _summary(client, wid)
    assert summary["health"]["state"] == "no_signals"
    assert summary["health"]["label"] == "No signals yet"
    # fresh workspace recommends initializing the sandbox / creating a workflow
    actions = [a["action"] for a in summary["recommended_actions"]]
    assert "init_sandbox" in actions
    assert "create_workflow" in actions


def test_safe_to_continue_after_clean_activity(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "index.html", "content": "<h1>ok</h1>"},
    )
    summary = _summary(client, wid)
    assert summary["health"]["state"] == "safe_to_continue"
    assert summary["counts"]["sandbox_files"] == 1


def test_health_approval_needed(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/checkout.ts", "content": "// stripe"},
    )  # halts → pending approval
    summary = _summary(client, wid)
    assert summary["health"]["state"] == "approval_needed"
    assert summary["counts"]["pending_approvals"] == 1
    assert summary["recommended_actions"][0]["action"] == "review_approval"


def test_health_validation_failed(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "bad.py", "content": "def (:"},
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/validators/run",
        json={"validator_type": "code_syntax", "target_ref": "bad.py"},
    )
    summary = _summary(client, wid)
    assert summary["health"]["state"] == "validation_failed"
    assert summary["counts"]["failed_validators"] == 1


def test_health_agent_restricted_outranks_others(env):
    client, wid, _ = env
    agent = _add_agent(client, wid, "Risky", "Backend Coder")
    client.post(f"/api/runtime/workspaces/{wid}/agents/{agent}/quarantine",
                json={"reason": "repeated risk"})
    # also create a pending approval so multiple signals are active
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/auth/login.ts", "content": "x"},
    )
    summary = _summary(client, wid)
    assert summary["health"]["state"] == "agent_restricted"  # highest severity wins
    assert "Needs approval" in summary["health"]["active_labels"]  # but both surfaced
    assert summary["counts"]["quarantined_agents"] == 1


def test_health_build_test_failed(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "ls", "args": ["nope"]},
    )  # exits non-zero
    summary = _summary(client, wid)
    assert summary["health"]["state"] == "build_test_failed"
    actions = [a["action"] for a in summary["recommended_actions"]]
    assert "fix_command" in actions


def test_blocked_workflow_health(env):
    client, wid, _ = env
    _add_agent(client, wid, "Planner", "Planner")  # only root role
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    summary = _summary(client, wid)
    # unassigned steps become blocked tasks
    assert summary["counts"]["blocked_tasks"] > 0
    assert summary["health"]["state"] in ("blocked", "validation_failed", "approval_needed")
    assert summary["workflow_progress"]["blocked_tasks"]


# ---------------------------------------------------------------- issues


def test_issues_aggregate_multiple_sources(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    # pending approval
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/payment/pay.ts", "content": "x"},
    )
    # failed validator
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "broken.json", "content": "{,,}"},
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/validators/run",
        json={"validator_type": "code_syntax", "target_ref": "broken.json"},
    )
    # quarantined agent
    agent = _add_agent(client, wid, "Q", "Researcher")
    client.post(f"/api/runtime/workspaces/{wid}/agents/{agent}/quarantine",
                json={"reason": "bad"})

    issues = _issues(client, wid)
    kinds = {i["kind"] for i in issues}
    assert {"approval_needed", "validation_failed", "agent_restricted"} <= kinds
    assert all(i["title"] and i["link"] for i in issues)
    # high-severity issues come first
    severities = [i["severity"] for i in issues]
    assert severities == sorted(severities, key=lambda s: 0 if s == "high" else 1)


# ------------------------------------------------------------ project map


def test_project_map_derives_from_real_rows(env):
    client, wid, _ = env
    _add_agent(client, wid, "Planner", "Planner")
    _add_agent(client, wid, "Backend", "Backend Coder")
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    cmap = client.get(f"/api/runtime/workspaces/{wid}/debug/project-map").json()
    types = {n["type"] for n in cmap["nodes"]}
    assert {"goal", "workflow", "task", "agent"} <= types
    # goal connects to the workflow
    assert any(e["from"] == "goal" and e["to"] == wfid for e in cmap["edges"])
    # node ids are unique
    ids = [n["id"] for n in cmap["nodes"]]
    assert len(ids) == len(set(ids))


def test_project_map_includes_validation_nodes(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/validators/run",
        json={"validator_type": "data_flow",
              "payload": {"consumer": {"fields": {"price": "number"}},
                          "producer": {"fields": {"cost": "number"}}}},
    )
    cmap = client.get(f"/api/runtime/workspaces/{wid}/debug/project-map").json()
    assert any(n["type"] == "validation" for n in cmap["nodes"])


# ----------------------------------------------- aggregations / sections


def test_summary_sections_present(env):
    client, wid, _ = env
    _add_agent(client, wid, "Planner", "Planner", status="caution")
    summary = _summary(client, wid)
    assert "caution" in summary["agents_overview"]["by_status"]
    assert summary["agents_overview"]["total"] == 1
    assert "workflow_progress" in summary
    assert "validation_summary" in summary
    assert "enforcement_summary" in summary
    assert "recent_changes" in summary


def test_recent_changes_reflect_activity(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "a.txt", "content": "hi"},
    )
    summary = _summary(client, wid)
    labels = [c["label"] for c in summary["recent_changes"]]
    assert "File created" in labels


# --------------------------------------------------- security / read-only


def test_no_secrets_or_host_paths_in_summary(env):
    client, wid, root = env
    secret = "sk-livedeadbeef1234567890"
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "leak.py", "content": f"API_KEY='{secret}'"},
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/validators/run",
        json={"validator_type": "secret_exposure", "target_ref": "leak.py"},
    )
    blob = (
        str(_summary(client, wid))
        + str(_issues(client, wid))
        + str(client.get(f"/api/runtime/workspaces/{wid}/debug/project-map").json())
    )
    assert secret not in blob
    assert str(root) not in blob


def test_debug_endpoints_are_read_only(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "a.txt", "content": "hi"},
    )
    before = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    # hitting every debug endpoint several times must not change activity
    for _ in range(3):
        _summary(client, wid)
        _issues(client, wid)
        client.get(f"/api/runtime/workspaces/{wid}/debug/project-map")
    after = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    assert len(after) == len(before)


def test_debug_endpoints_open_in_local_mode(env):
    client, wid, _ = env
    assert client.get(f"/api/runtime/workspaces/{wid}/debug/summary").status_code == 200
    assert client.get(f"/api/runtime/workspaces/{wid}/debug/issues").status_code == 200
    assert client.get(f"/api/runtime/workspaces/{wid}/debug/project-map").status_code == 200
    assert client.get("/api/runtime/workspaces/ws-nope/debug/summary").status_code == 404
