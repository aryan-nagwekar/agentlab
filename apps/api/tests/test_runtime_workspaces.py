"""Runtime Workspaces (v1.0): CRUD, status lifecycle, artifact registry, and
workspace.* events flowing through the normal event/timeline/replay systems."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _create(client, **overrides) -> dict:
    body = {
        "name": "Demo Workspace",
        "goal": "A future AI-built project area.",
        "project_id": "proj-1",
        **overrides,
    }
    response = client.post("/api/runtime/workspaces", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ----------------------------------------------------------------------- CRUD


def test_create_workspace(client):
    workspace = _create(client)
    assert workspace["workspace_id"].startswith("ws-")
    assert workspace["status"] == "draft"
    assert workspace["goal"] == "A future AI-built project area."
    assert workspace["activity_run_id"] == f"{workspace['workspace_id']}-activity"
    assert workspace["artifact_count"] == 0


def test_list_workspaces(client):
    first = _create(client, name="One")
    second = _create(client, name="Two")
    listed = client.get("/api/runtime/workspaces").json()
    ids = [w["workspace_id"] for w in listed]
    assert first["workspace_id"] in ids
    assert second["workspace_id"] in ids


def test_get_workspace_detail_and_404(client):
    workspace = _create(client)
    detail = client.get(f"/api/runtime/workspaces/{workspace['workspace_id']}").json()
    assert detail["name"] == "Demo Workspace"
    assert client.get("/api/runtime/workspaces/ws-nope").status_code == 404


def test_patch_metadata_and_status(client):
    workspace = _create(client)
    wid = workspace["workspace_id"]
    patched = client.patch(
        f"/api/runtime/workspaces/{wid}",
        json={"name": "Renamed", "goal": "New goal", "metadata": {"owner": "aryan"}},
    ).json()
    assert patched["name"] == "Renamed"
    assert patched["metadata"] == {"owner": "aryan"}

    moved = client.patch(f"/api/runtime/workspaces/{wid}", json={"status": "active"}).json()
    assert moved["status"] == "active"

    bad = client.patch(f"/api/runtime/workspaces/{wid}", json={"status": "exploded"})
    assert bad.status_code == 422


def test_delete_archives_instead_of_destroying(client):
    workspace = _create(client)
    wid = workspace["workspace_id"]
    archived = client.delete(f"/api/runtime/workspaces/{wid}")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    # the row (and its history) still exists
    assert client.get(f"/api/runtime/workspaces/{wid}").json()["status"] == "archived"
    # archiving twice is a no-op
    assert client.delete(f"/api/runtime/workspaces/{wid}").json()["status"] == "archived"


def test_register_and_list_artifacts(client):
    workspace = _create(client)
    wid = workspace["workspace_id"]
    created = client.post(
        f"/api/runtime/workspaces/{wid}/artifacts",
        json={"name": "index.html", "type": "file", "path": "site/index.html"},
    )
    assert created.status_code == 201
    artifact = created.json()
    assert artifact["artifact_id"].startswith("artifact-")
    assert artifact["path"] == "site/index.html"

    listed = client.get(f"/api/runtime/workspaces/{wid}/artifacts").json()
    assert [a["artifact_id"] for a in listed] == [artifact["artifact_id"]]
    assert client.get(f"/api/runtime/workspaces/{wid}").json()["artifact_count"] == 1


# --------------------------------------------------------------------- events


def test_lifecycle_emits_workspace_events(client):
    workspace = _create(client)
    wid = workspace["workspace_id"]
    client.patch(f"/api/runtime/workspaces/{wid}", json={"goal": "Better goal"})
    client.patch(f"/api/runtime/workspaces/{wid}", json={"status": "active"})
    client.post(
        f"/api/runtime/workspaces/{wid}/artifacts", json={"name": "notes.md", "type": "document"}
    )
    client.delete(f"/api/runtime/workspaces/{wid}")

    activity = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    types = [e["event_type"] for e in activity]  # newest first
    assert types == [
        "workspace.archived",
        "workspace.artifact_registered",
        "workspace.status_changed",
        "workspace.updated",
        "workspace.created",
    ]
    status_changed = next(e for e in activity if e["event_type"] == "workspace.status_changed")
    assert status_changed["payload"]["from_status"] == "draft"
    assert status_changed["payload"]["to_status"] == "active"
    assert status_changed["metadata"]["source"] == "runtime"
    assert all(e["metadata"]["workspace_id"] == wid for e in activity)


def test_noop_patch_emits_nothing(client):
    workspace = _create(client)
    wid = workspace["workspace_id"]
    client.patch(f"/api/runtime/workspaces/{wid}", json={"name": "Demo Workspace"})
    activity = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    assert [e["event_type"] for e in activity] == ["workspace.created"]


def test_workspace_events_flow_into_timeline_and_replay(client):
    workspace = _create(client)
    wid = workspace["workspace_id"]
    run_id = workspace["activity_run_id"]
    client.patch(f"/api/runtime/workspaces/{wid}", json={"status": "active"})
    client.post(
        f"/api/runtime/workspaces/{wid}/artifacts", json={"name": "spec.md", "type": "document"}
    )

    # The activity run is a normal AgentLab run: timeline, replay, and the
    # other read APIs accept it without special-casing.
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["name"] == "Workspace · Demo Workspace"

    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    assert timeline == [
        "workspace.created",
        "workspace.status_changed",
        "workspace.artifact_registered",
    ]

    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert replay["event_count"] == 3
    assert [e["event_type"] for e in replay["events"]] == timeline

    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path

    # Workspace status maps onto the activity-run projection when terminal.
    client.patch(f"/api/runtime/workspaces/{wid}", json={"status": "completed"})
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"


def test_workspace_run_appears_in_project(client):
    workspace = _create(client)
    runs = client.get("/api/projects/proj-1/runs").json()
    assert workspace["activity_run_id"] in [r["id"] for r in runs]


def test_writes_require_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/rt-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/runtime/workspaces", json={"name": "X"}).status_code == 401
        created = client.post(
            "/api/runtime/workspaces", json={"name": "X"}, headers={"X-API-Key": "k1"}
        )
        assert created.status_code == 201
        wid = created.json()["workspace_id"]
        assert client.patch(f"/api/runtime/workspaces/{wid}", json={"name": "Y"}).status_code == 401
        assert client.delete(f"/api/runtime/workspaces/{wid}").status_code == 401
        # reads stay open in local mode
        assert client.get("/api/runtime/workspaces").status_code == 200
