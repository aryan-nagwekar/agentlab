"""Lab Mode: fault templates, injection, projections, replay, and safety."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ALL_FAULTS = {
    "kill_agent",
    "delay_messages",
    "drop_messages",
    "force_tool_failure",
    "simulate_model_timeout",
    "overload_agent",
}


def test_fault_templates(client):
    templates = client.get("/api/lab/fault-templates").json()
    assert {t["fault_type"] for t in templates} == ALL_FAULTS
    for template in templates:
        assert template["label"]
        assert template["description"]
        assert template["target_kind"] in ("agent", "channel")
        assert isinstance(template["params"], list)
        assert template["emits"][0] == "fault.injected"


def _inject(client, fault_type, **kwargs):
    body = {"fault_type": fault_type, **kwargs}
    return client.post("/api/runs/run-1/faults", json=body)


def test_kill_agent_full_pipeline(client, seeded_run):
    before_errors = client.get("/api/runs/run-1").json()["error_count"]

    response = _inject(client, "kill_agent", target_agent_id="researcher")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["fault_type"] == "kill_agent"
    types = [e["event_type"] for e in result["events"]]
    assert types == ["fault.injected", "agent.failed"]

    fault = result["events"][0]
    assert fault["source_agent_id"] == "lab-controller"
    assert fault["target_agent_id"] == "researcher"
    assert fault["payload"]["fault_type"] == "kill_agent"
    assert fault["metadata"]["safe_simulation"] is True
    assert fault["metadata"]["created_by"] == "lab"
    # follow-up is linked back to the fault event
    assert result["events"][1]["metadata"]["fault_event_id"] == fault["event_id"]
    assert "no real process was killed" in result["events"][1]["payload"]["error"]

    # stored + listable
    faults = client.get("/api/runs/run-1/faults").json()
    assert [f["event_id"] for f in faults] == [fault["event_id"]]

    # projections: agent failed, error count up
    agent = client.get("/api/agents/researcher", params={"project_id": "proj-1"}).json()
    assert agent["status"] == "failed"
    run = client.get("/api/runs/run-1").json()
    assert run["error_count"] == before_errors + 1

    # graph reacts; lab-controller never becomes a workflow node
    graph = client.get("/api/runs/run-1/graph").json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["researcher"]["status"] == "failed"
    assert "lab-controller" not in nodes

    # metrics count the failure but not the operator
    metrics = client.get("/api/runs/run-1/metrics").json()
    assert metrics["totals"]["error_count"] == before_errors + 1
    assert "lab-controller" not in {row["agent_id"] for row in metrics["per_agent"]}


def test_overload_agent_status(client, seeded_run):
    response = _inject(client, "overload_agent", target_agent_id="planner")
    assert response.status_code == 201
    graph = client.get("/api/runs/run-1/graph").json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["planner"]["status"] == "overloaded"


def test_force_tool_failure(client, seeded_run):
    response = _inject(
        client,
        "force_tool_failure",
        target_agent_id="coder",
        params={"tool_name": "code.lint"},
    )
    assert response.status_code == 201
    types = [e["event_type"] for e in response.json()["events"]]
    assert types == ["fault.injected", "tool.called", "tool.failed"]
    failed = response.json()["events"][2]
    assert failed["payload"]["tool_name"] == "code.lint"
    assert "SimulatedToolError" in failed["payload"]["error"]


def test_simulate_model_timeout(client, seeded_run):
    response = _inject(
        client,
        "simulate_model_timeout",
        target_agent_id="researcher",
        params={"timeout_ms": 15000},
    )
    assert response.status_code == 201
    failed = response.json()["events"][2]
    assert failed["event_type"] == "model.failed"
    assert failed["payload"]["latency_ms"] == 15000
    assert "SimulatedTimeout" in failed["payload"]["error"]


def test_delay_messages_inflates_edge_latency(client, seeded_run):
    before = client.get("/api/runs/run-1/graph").json()
    edge_before = next(
        e for e in before["edges"] if e["id"] == "planner->researcher"
    )

    response = _inject(
        client,
        "delay_messages",
        source_agent_id="planner",
        target_agent_id="researcher",
        params={"delay_ms": 5000},
    )
    assert response.status_code == 201

    after = client.get("/api/runs/run-1/graph").json()
    edge_after = next(e for e in after["edges"] if e["id"] == "planner->researcher")
    assert edge_after["message_count"] == edge_before["message_count"] + 1
    assert edge_after["avg_latency_ms"] > edge_before["avg_latency_ms"]
    assert edge_after["last_status"] == "delivered"


def test_drop_messages_fails_edge(client, seeded_run):
    response = _inject(
        client,
        "drop_messages",
        source_agent_id="researcher",
        target_agent_id="coder",
        params={"drop_rate": 0.3},
    )
    assert response.status_code == 201
    types = [e["event_type"] for e in response.json()["events"]]
    assert types == ["fault.injected", "message.sent", "message.failed"]

    graph = client.get("/api/runs/run-1/graph").json()
    edge = next(e for e in graph["edges"] if e["id"] == "researcher->coder")
    assert edge["last_status"] == "failed"


def test_fault_appears_in_replay_tape_and_fold(client, seeded_run):
    tape_before = client.get("/api/runs/run-1/replay").json()
    base_count = tape_before["event_count"]

    _inject(client, "kill_agent", target_agent_id="coder")

    tape = client.get("/api/runs/run-1/replay").json()
    assert tape["event_count"] == base_count + 2
    assert tape["markers"]["faults"] == [base_count]
    assert tape["events"][base_count]["event_type"] == "fault.injected"
    assert tape["events"][base_count + 1]["event_type"] == "agent.failed"

    # Before the fault index the coder is in its original (failed-from-fixture)
    # state count; after applying the follow-up its error count grows.
    at_fault = client.get(
        "/api/runs/run-1/replay/graph", params={"index": base_count - 1}
    ).json()
    after_fault = client.get(
        "/api/runs/run-1/replay/graph", params={"index": base_count + 1}
    ).json()
    coder_before = next(n for n in at_fault["nodes"] if n["id"] == "coder")
    coder_after = next(n for n in after_fault["nodes"] if n["id"] == "coder")
    assert coder_after["errors"] == coder_before["errors"] + 1
    assert coder_after["status"] == "failed"
    assert "lab-controller" not in {n["id"] for n in after_fault["nodes"]}


def test_validation_errors(client, seeded_run):
    assert _inject(client, "set_on_fire", target_agent_id="coder").status_code == 422
    assert _inject(client, "kill_agent").status_code == 422  # missing target
    assert (
        _inject(client, "kill_agent", target_agent_id="not-in-this-run").status_code == 422
    )
    # channel fault without a source
    assert (
        _inject(client, "drop_messages", target_agent_id="coder").status_code == 422
    )
    # unknown run
    response = client.post(
        "/api/runs/ghost/faults",
        json={"fault_type": "kill_agent", "target_agent_id": "x"},
    )
    assert response.status_code == 404
    assert client.get("/api/runs/ghost/faults").status_code == 404


def test_fault_injection_respects_api_keys(tmp_path, event_factory):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/lab-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        headers = {"X-API-Key": "k1"}
        client.post("/api/events", json=event_factory("run.started"), headers=headers)
        client.post(
            "/api/events",
            json=event_factory("agent.started", source="a", payload={"name": "A"}),
            headers=headers,
        )
        body = {"fault_type": "kill_agent", "target_agent_id": "a"}
        assert client.post("/api/runs/run-1/faults", json=body).status_code == 401
        assert (
            client.post("/api/runs/run-1/faults", json=body, headers=headers).status_code
            == 201
        )
