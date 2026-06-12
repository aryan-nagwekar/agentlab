"""Orchestration Engine (v1.4): workflow/plan/task creation, role-based
assignment (disabled/quarantined never assigned), dependency ordering,
lifecycle transitions, manual result recording, and runtime.workflow.* /
runtime.task.* events flowing through activity/timeline/replay.

v1.4 boundary: everything here is status metadata — no files are written,
no commands run, no model calls are made by the orchestrator."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/orch.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={
                "name": "Bottle Site",
                "goal": "Build a website that sells water bottles.",
                "project_id": "proj-1",
            },
        ).json()["workspace_id"]
        yield client, wid


def _add_agent(client, wid, name, role, status="ready"):
    agent = client.post(
        f"/api/runtime/workspaces/{wid}/agents",
        json={"name": name, "role": role},
    ).json()
    if status != "ready":
        client.patch(
            f"/api/runtime/workspaces/{wid}/agents/{agent['agent_id']}",
            json={"status": status},
        )
    return agent["agent_id"]


def _full_team(client, wid):
    return {
        "planner": _add_agent(client, wid, "Planner", "Planner"),
        "researcher": _add_agent(client, wid, "Researcher", "Researcher"),
        "backend": _add_agent(client, wid, "Backend Coder", "Backend Coder"),
        "ui": _add_agent(client, wid, "UI Agent", "UI Engineer"),
        "verifier": _add_agent(client, wid, "Verifier", "Verifier"),
    }


def _workflow(client, wid, **kwargs):
    response = client.post(f"/api/runtime/workspaces/{wid}/workflows", json=kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def _plan(client, wid, wfid):
    response = client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    assert response.status_code == 201, response.text
    return response.json()


def _tasks(client, wid, wfid):
    return client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()


def _action(client, wid, wfid, action):
    return client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/{action}")


def _activity_types(client, wid):
    return [
        e["event_type"]
        for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    ]


# -------------------------------------------------------- creation / planning


def test_create_and_list_workflows(env):
    client, wid = env
    workflow = _workflow(client, wid)
    assert workflow["goal"] == "Build a website that sells water bottles."
    assert workflow["status"] == "planned"
    assert workflow["has_plan"] is False
    listed = client.get(f"/api/runtime/workspaces/{wid}/workflows").json()
    assert [w["workflow_id"] for w in listed] == [workflow["workflow_id"]]
    detail = client.get(
        f"/api/runtime/workspaces/{wid}/workflows/{workflow['workflow_id']}"
    ).json()
    assert detail["created_by"] == "user"
    assert "runtime.workflow.created" in _activity_types(client, wid)


def test_workflow_goal_override_and_missing_goal(env, tmp_path):
    client, wid = env
    custom = _workflow(client, wid, goal="Custom goal")
    assert custom["goal"] == "Custom goal"
    bare = client.post(
        "/api/runtime/workspaces", json={"name": "No Goal WS", "project_id": "p"}
    ).json()["workspace_id"]
    response = client.post(f"/api/runtime/workspaces/{bare}/workflows", json={})
    assert response.status_code == 400
    assert "goal is required" in response.json()["detail"]


def test_plan_creates_tasks_with_assignments_and_dependencies(env):
    client, wid = env
    team = _full_team(client, wid)
    workflow = _workflow(client, wid)
    plan = _plan(client, wid, workflow["workflow_id"])
    assert plan["summary"].startswith("Deterministic 5-step pipeline")
    assert len(plan["steps"]) == 5
    assert plan["approval_requirements"] == ["backend coder"]

    tasks = _tasks(client, wid, workflow["workflow_id"])
    assert len(tasks) == 5
    by_title = {t["title"]: t for t in tasks}
    assert by_title["Draft the project plan"]["assigned_agent_id"] == team["planner"]
    assert by_title["Build the backend"]["assigned_agent_id"] == team["backend"]
    assert by_title["Build the user interface"]["assigned_agent_id"] == team["ui"]
    assert by_title["Review and verify the work"]["assigned_agent_id"] == team["verifier"]
    # dependency wiring: UI depends on backend; verify depends on 1,2,3
    assert by_title["Build the user interface"]["dependencies"] == [
        by_title["Build the backend"]["task_id"]
    ]
    assert len(by_title["Review and verify the work"]["dependencies"]) == 3
    assert all(t["status"] == "pending" for t in tasks)


def test_plan_is_one_shot(env):
    client, wid = env
    workflow = _workflow(client, wid)
    _plan(client, wid, workflow["workflow_id"])
    again = client.post(
        f"/api/runtime/workspaces/{wid}/workflows/{workflow['workflow_id']}/plan"
    )
    assert again.status_code == 409


def test_unassignable_agents_and_blocked_tasks(env):
    client, wid = env
    _add_agent(client, wid, "Planner", "Planner")
    _add_agent(client, wid, "Disabled Backend", "Backend Coder", status="disabled")
    _add_agent(client, wid, "Quarantined UI", "UI Engineer", status="quarantined")
    workflow = _workflow(client, wid)
    _plan(client, wid, workflow["workflow_id"])
    tasks = _tasks(client, wid, workflow["workflow_id"])
    by_title = {t["title"]: t for t in tasks}

    # disabled/quarantined agents must never be assigned
    assert by_title["Build the backend"]["assigned_agent_id"] is None
    assert by_title["Build the backend"]["status"] == "blocked"
    assert "no assignable" in by_title["Build the backend"]["blocked_reason"]
    assert by_title["Build the user interface"]["assigned_agent_id"] is None
    assert by_title["Draft the project plan"]["assigned_agent_id"] is not None

    types = _activity_types(client, wid)
    assert "runtime.task.assignment_failed" in types
    failed = [
        e
        for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()
        if e["event_type"] == "runtime.task.assignment_failed"
    ]
    assert all("disabled/quarantined" in e["payload"]["reason"] for e in failed)


def test_assignment_prefers_ready_over_suspicious(env):
    client, wid = env
    suspicious = _add_agent(client, wid, "Sus Planner", "Planner", status="suspicious")
    ready = _add_agent(client, wid, "Fresh Planner", "Planner")
    workflow = _workflow(client, wid)
    _plan(client, wid, workflow["workflow_id"])
    by_title = {t["title"]: t for t in _tasks(client, wid, workflow["workflow_id"])}
    assert by_title["Draft the project plan"]["assigned_agent_id"] == ready
    assert by_title["Draft the project plan"]["assigned_agent_id"] != suspicious


# ------------------------------------------------------------------ lifecycle


def test_start_requires_plan_and_dependency_ordering(env):
    client, wid = env
    _full_team(client, wid)
    workflow = _workflow(client, wid)
    wfid = workflow["workflow_id"]

    assert _action(client, wid, wfid, "start").status_code == 409  # no plan yet
    _plan(client, wid, wfid)
    started = _action(client, wid, wfid, "start")
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    by_title = {t["title"]: t for t in _tasks(client, wid, wfid)}
    # only the root task starts; everything else waits on dependencies
    assert by_title["Draft the project plan"]["status"] == "running"
    assert by_title["Research the domain"]["status"] == "pending"
    assert by_title["Build the backend"]["status"] == "pending"


def _record(client, wid, wfid, task_id, output="done"):
    return client.post(
        f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{task_id}/result",
        json={"output": output},
    )


def test_full_run_to_completion_via_results(env):
    client, wid = env
    _full_team(client, wid)
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")

    # complete tasks as they become startable; 5 rounds is the DAG depth bound
    for _ in range(5):
        running = [t for t in _tasks(client, wid, wfid) if t["status"] == "running"]
        if not running:
            break
        for task in running:
            response = _record(client, wid, wfid, task["task_id"], output=f"did {task['title']}")
            assert response.status_code == 201, response.text

    workflow = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}").json()
    assert workflow["status"] == "completed"
    assert workflow["completed_task_count"] == 5
    tasks = _tasks(client, wid, wfid)
    assert all(t["status"] == "completed" for t in tasks)
    assert all(t["latest_result"]["output"].startswith("did ") for t in tasks)
    types = _activity_types(client, wid)
    assert "runtime.workflow.completed" in types
    assert types.count("runtime.task.result_recorded") == 5


def test_pause_resume_cancel(env):
    client, wid = env
    _full_team(client, wid)
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")
    assert _action(client, wid, wfid, "pause").json()["status"] == "paused"
    assert _action(client, wid, wfid, "resume").json()["status"] == "running"
    assert _action(client, wid, wfid, "cancel").json()["status"] == "cancelled"
    # terminal: nothing further
    assert _action(client, wid, wfid, "start").status_code == 409
    assert _action(client, wid, wfid, "cancel").status_code == 409


def test_task_failure_fails_stuck_workflow(env):
    client, wid = env
    _full_team(client, wid)
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")
    root = next(t for t in _tasks(client, wid, wfid) if t["status"] == "running")
    patched = client.patch(
        f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{root['task_id']}",
        json={"status": "failed", "reason": "planner produced nothing usable"},
    )
    assert patched.status_code == 200
    workflow = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}").json()
    assert workflow["status"] == "failed"
    types = _activity_types(client, wid)
    assert "runtime.task.failed" in types
    assert "runtime.workflow.failed" in types


def test_blocked_workflow_when_unassigned_in_path(env):
    client, wid = env
    _add_agent(client, wid, "Planner", "Planner")  # only the root role exists
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")
    root = next(t for t in _tasks(client, wid, wfid) if t["status"] == "running")
    _record(client, wid, wfid, root["task_id"])
    workflow = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}").json()
    assert workflow["status"] == "blocked"
    assert "runtime.workflow.blocked" in _activity_types(client, wid)
    # rerouting the blocked tasks to a new agent unblocks via resume
    fixer = _add_agent(client, wid, "Fixer", "Backend Coder and UI and Verifier and Researcher")
    for task in _tasks(client, wid, wfid):
        if task["status"] == "blocked":
            response = client.patch(
                f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{task['task_id']}",
                json={"assigned_agent_id": fixer},
            )
            assert response.status_code == 200
    assert _action(client, wid, wfid, "resume").json()["status"] == "running"


def test_patch_task_rejects_unassignable_agent_and_bad_status(env):
    client, wid = env
    _full_team(client, wid)
    bad = _add_agent(client, wid, "Quarantined", "Backend Coder", status="quarantined")
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    task = _tasks(client, wid, wfid)[0]
    url = f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{task['task_id']}"
    rejected = client.patch(url, json={"assigned_agent_id": bad})
    assert rejected.status_code == 409
    assert "quarantined" in rejected.json()["detail"]
    invalid = client.patch(url, json={"status": "waiting_for_approval"})
    assert invalid.status_code == 422  # reserved for later versions


def test_reroute_emits_rerouted_event(env):
    client, wid = env
    _full_team(client, wid)
    second_planner = _add_agent(client, wid, "Backup Planner", "Planner")
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    root = next(
        t for t in _tasks(client, wid, wfid) if t["title"] == "Draft the project plan"
    )
    client.patch(
        f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks/{root['task_id']}",
        json={"assigned_agent_id": second_planner, "reason": "first planner overloaded"},
    )
    events = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    rerouted = next(e for e in events if e["event_type"] == "runtime.task.rerouted")
    assert rerouted["payload"]["assigned_agent_id"] == second_planner
    assert rerouted["payload"]["reason"] == "first planner overloaded"


def test_result_output_is_bounded_in_event(env):
    client, wid = env
    _full_team(client, wid)
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")
    root = next(t for t in _tasks(client, wid, wfid) if t["status"] == "running")
    _record(client, wid, wfid, root["task_id"], output="x" * 4000)
    events = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    recorded = next(e for e in events if e["event_type"] == "runtime.task.result_recorded")
    assert len(recorded["payload"]["output_summary"]) <= 300


# --------------------------------------------------------- pipeline / replay


def test_workflow_events_flow_into_timeline_and_replay(env):
    client, wid = env
    _full_team(client, wid)
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")

    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    assert "runtime.workflow.created" in timeline
    assert "runtime.workflow.plan_created" in timeline
    assert "runtime.workflow.started" in timeline
    assert "runtime.task.started" in timeline
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_workflow_writes_require_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/orch-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "W", "goal": "g"},
            headers={"X-API-Key": "k1"},
        ).json()["workspace_id"]
        assert (
            client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).status_code
            == 401
        )
        created = client.post(
            f"/api/runtime/workspaces/{wid}/workflows",
            json={},
            headers={"X-API-Key": "k1"},
        )
        assert created.status_code == 201
        wfid = created.json()["workflow_id"]
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan"
            ).status_code
            == 401
        )
        # reads stay open in local mode
        assert client.get(f"/api/runtime/workspaces/{wid}/workflows").status_code == 200


def test_orchestrator_makes_no_files_commands_or_model_calls(env, tmp_path):
    """v1.4 boundary: a full plan→start→complete cycle emits only
    runtime.workflow.*/runtime.task.* events — no sandbox file/command events
    and no model.* events appear, and no sandbox directory is created."""
    client, wid = env
    _full_team(client, wid)
    wfid = _workflow(client, wid)["workflow_id"]
    _plan(client, wid, wfid)
    _action(client, wid, wfid, "start")
    for _ in range(5):
        for task in [t for t in _tasks(client, wid, wfid) if t["status"] == "running"]:
            _record(client, wid, wfid, task["task_id"])

    types = set(_activity_types(client, wid))
    orchestration_types = {
        t for t in types if t.startswith(("runtime.workflow.", "runtime.task."))
    }
    forbidden = {
        t
        for t in types
        if t.startswith(("sandbox.file", "sandbox.command", "model."))
    }
    assert orchestration_types, "expected orchestration events"
    assert not forbidden, f"orchestrator must not execute anything: {forbidden}"
    assert not (tmp_path / "workspaces" / wid).exists()  # sandbox never touched
