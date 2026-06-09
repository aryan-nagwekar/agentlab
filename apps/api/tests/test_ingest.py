"""Ingestion contract: validation, batching, idempotency, auth."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_single_event_accepted(client, event_factory):
    response = client.post("/api/events", json=event_factory("run.started"))
    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "duplicates": 0}


def test_batch_accepted(client, event_factory):
    batch = {"events": [event_factory("run.started"), event_factory("agent.heartbeat", source="a")]}
    response = client.post("/api/events", json=batch)
    assert response.status_code == 202
    assert response.json()["accepted"] == 2


def test_unknown_event_type_rejected(client, event_factory):
    bad = event_factory("run.started")
    bad["event_type"] = "totally.bogus"
    response = client.post("/api/events", json=bad)
    assert response.status_code == 422
    assert "unknown event_type" in response.text


def test_missing_required_field_rejected(client, event_factory):
    bad = event_factory("run.started")
    del bad["project_id"]
    response = client.post("/api/events", json=bad)
    assert response.status_code == 422


def test_duplicate_event_id_is_idempotent(client, event_factory):
    event = event_factory("run.started")
    first = client.post("/api/events", json=event)
    second = client.post("/api/events", json=event)
    assert first.json() == {"accepted": 1, "duplicates": 0}
    assert second.json() == {"accepted": 0, "duplicates": 1}
    events = client.get("/api/runs/run-1/events").json()
    assert len(events) == 1


def test_project_autocreated_on_first_event(client, event_factory):
    client.post("/api/events", json=event_factory("run.started", project="fresh-project"))
    projects = client.get("/api/projects").json()
    assert [p["id"] for p in projects] == ["fresh-project"]
    assert projects[0]["run_count"] == 1


def test_api_key_enforced_when_configured(tmp_path, event_factory):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/auth.db", api_keys="k1, k2", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        event = event_factory("run.started")
        assert client.post("/api/events", json=event).status_code == 401
        assert (
            client.post("/api/events", json=event, headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        ok = client.post("/api/events", json=event, headers={"X-API-Key": "k2"})
        assert ok.status_code == 202
        # Read path stays open in v0.1.
        assert client.get("/api/projects").status_code == 200
