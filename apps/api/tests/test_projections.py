"""Projection correctness: runs, agents, messages, tools, routing, trust."""
from __future__ import annotations


def test_run_lifecycle_and_finalize(client, seeded_run):
    run = client.get("/api/runs/run-1").json()
    assert run["status"] == "failed"
    assert run["name"] == "pipeline"
    assert run["total_latency_ms"] == 1500
    assert run["total_tokens"] == 150
    assert run["total_cost_estimate"] == 0.012
    assert run["error_count"] == 2  # tool.failed + agent.failed
    assert run["agent_count"] == 3
    assert run["message_count"] == 2
    assert run["started_at"].endswith("Z")


def test_agent_states_after_run(client, seeded_run):
    planner = client.get("/api/agents/planner", params={"project_id": "proj-1"}).json()
    researcher = client.get("/api/agents/researcher", params={"project_id": "proj-1"}).json()
    coder = client.get("/api/agents/coder", params={"project_id": "proj-1"}).json()
    assert planner["status"] == "running"  # never completed in this scenario
    assert planner["name"] == "PlannerAgent"
    assert planner["role"] == "planner"
    assert researcher["status"] == "idle"
    assert coder["status"] == "failed"
    assert researcher["trust_score"] == 1.0


def test_events_endpoint_ordering_and_filters(client, seeded_run):
    events = client.get("/api/runs/run-1/events").json()
    assert len(events) == len(seeded_run)
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)
    assert events[0]["event_type"] == "run.started"
    assert events[-1]["event_type"] == "run.failed"

    sent = client.get("/api/runs/run-1/events", params={"event_type": "message.sent"}).json()
    assert [e["metadata"]["message_id"] for e in sent] == ["m1", "m2"]

    researcher_events = client.get(
        "/api/runs/run-1/events", params={"agent_id": "researcher"}
    ).json()
    types = {e["event_type"] for e in researcher_events}
    assert "tool.completed" in types
    assert "routing.decision" in types  # researcher was the routing target
    assert all(
        e["source_agent_id"] == "researcher" or e["target_agent_id"] == "researcher"
        for e in researcher_events
    )

    page = client.get("/api/runs/run-1/events", params={"limit": 5, "offset": 5}).json()
    assert len(page) == 5
    assert page[0]["event_id"] == events[5]["event_id"]


def test_trust_update_clamped_and_applied(client, event_factory):
    client.post(
        "/api/events",
        json=event_factory("agent.started", source="sketchy", payload={"name": "Sketchy"}),
    )
    client.post(
        "/api/events",
        json=event_factory(
            "trust.updated", source="sketchy", payload={"trust_score": 0.31, "reason": "errors"}
        ),
    )
    agent = client.get("/api/agents/sketchy", params={"project_id": "proj-1"}).json()
    assert agent["trust_score"] == 0.31

    client.post(
        "/api/events",
        json=event_factory("risk.updated", source="sketchy", payload={"risk_score": 7}),
    )
    agent = client.get("/api/agents/sketchy", params={"project_id": "proj-1"}).json()
    assert agent["risk_score"] == 1.0  # clamped


def test_quarantine_status(client, event_factory):
    client.post(
        "/api/events",
        json=event_factory("agent.quarantined", source="rogue", payload={"reason": "spam"}),
    )
    agent = client.get("/api/agents/rogue", params={"project_id": "proj-1"}).json()
    assert agent["status"] == "quarantined"


def test_agent_events_endpoint(client, seeded_run):
    events = client.get(
        "/api/agents/coder/events", params={"project_id": "proj-1", "limit": 10}
    ).json()
    assert events  # most recent first
    assert events[0]["event_type"] == "agent.failed"
    assert all(
        e["source_agent_id"] == "coder" or e["target_agent_id"] == "coder" for e in events
    )


def test_project_detail_includes_runs_and_agents(client, seeded_run):
    detail = client.get("/api/projects/proj-1").json()
    assert detail["project"]["id"] == "proj-1"
    assert detail["project"]["run_count"] == 1
    assert detail["project"]["agent_count"] == 3
    assert detail["runs"][0]["id"] == "run-1"
    assert detail["runs"][0]["message_count"] == 2
    assert {a["id"] for a in detail["agents"]} == {"planner", "researcher", "coder"}


def test_missing_resources_404(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/api/agents/nope").status_code == 404
