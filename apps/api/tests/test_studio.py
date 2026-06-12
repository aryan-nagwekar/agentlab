"""Agent Builder Studio: workflow CRUD, validation, DAG execution, and
integration with the existing graph/replay/cost/score read paths."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.studio.service import SEED_WORKFLOW_NAME

RUN_INPUT = "Build a simple FastAPI endpoint and review it for security."


def _workflow_body(**overrides) -> dict:
    body = {
        "name": "Test Team",
        "description": "two-step pipeline",
        "project_id": "proj-1",
        "agents": [
            {
                "agent_id": "writer",
                "name": "Writer",
                "role": "writer",
                "provider": "mock",
                "model_name": "mock:gpt-4.1",
            },
            {
                "agent_id": "reviewer",
                "name": "Reviewer",
                "role": "reviewer",
                "provider": "mock",
                "model_name": "mock:claude-sonnet",
            },
        ],
        "edges": [
            {"edge_id": "e1", "source_agent_id": "writer", "target_agent_id": "reviewer"}
        ],
    }
    body.update(overrides)
    return body


# ----------------------------------------------------------------------- seed


def test_seeded_workflow_exists_and_validates(client):
    workflows = client.get("/api/studio/workflows").json()
    seeded = next(w for w in workflows if w["name"] == SEED_WORKFLOW_NAME)
    assert seeded["agent_count"] == 4
    assert seeded["edge_count"] == 3
    detail = client.get(f"/api/studio/workflows/{seeded['workflow_id']}").json()
    assert all(a["provider"] == "mock" for a in detail["agents"])  # zero keys needed
    verdict = client.post(f"/api/studio/workflows/{seeded['workflow_id']}/validate").json()
    assert verdict == {"valid": True, "errors": [], "warnings": []}


def test_seeded_workflow_runs_without_any_keys(client):
    seeded = next(
        w for w in client.get("/api/studio/workflows").json() if w["name"] == SEED_WORKFLOW_NAME
    )
    response = client.post(
        f"/api/studio/workflows/{seeded['workflow_id']}/run", json={"input": RUN_INPUT}
    )
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "completed"
    assert result["open_run_url"] == f"/runs/{result['run_id']}"
    types = [e["event_type"] for e in client.get(f"/api/runs/{result['run_id']}/events").json()]
    assert types[0] == "run.started"
    assert types[-1] == "run.completed"
    assert types.count("agent.started") == 4
    assert types.count("model.completed") == 4
    assert types.count("message.sent") == 3  # one per edge


# ----------------------------------------------------------------------- CRUD


def test_create_get_update_delete_workflow(client):
    created = client.post("/api/studio/workflows", json=_workflow_body())
    assert created.status_code == 201
    workflow = created.json()
    workflow_id = workflow["workflow_id"]
    assert {a["agent_id"] for a in workflow["agents"]} == {"writer", "reviewer"}

    listed = client.get("/api/studio/workflows").json()
    assert workflow_id in [w["workflow_id"] for w in listed]

    updated = client.put(
        f"/api/studio/workflows/{workflow_id}",
        json=_workflow_body(name="Renamed Team", edges=[]),
    ).json()
    assert updated["name"] == "Renamed Team"
    assert updated["edges"] == []
    assert len(updated["agents"]) == 2

    assert client.delete(f"/api/studio/workflows/{workflow_id}").status_code == 204
    assert client.get(f"/api/studio/workflows/{workflow_id}").status_code == 404


def test_agent_crud(client):
    workflow_id = client.post("/api/studio/workflows", json=_workflow_body()).json()["workflow_id"]

    created = client.post(
        f"/api/studio/workflows/{workflow_id}/agents",
        json={"name": "Extra Agent", "role": "extra", "provider": "mock",
              "model_name": "mock:gemini-pro"},
    )
    assert created.status_code == 201
    agent_id = created.json()["agent_id"]
    assert agent_id == "extra-agent"  # slug derived from the name

    updated = client.put(
        f"/api/studio/workflows/{workflow_id}/agents/{agent_id}",
        json={"name": "Extra Agent", "role": "analyst", "provider": "mock",
              "model_name": "mock:local-ollama", "temperature": 0.7},
    ).json()
    assert updated["role"] == "analyst"
    assert updated["model_name"] == "mock:local-ollama"
    assert updated["temperature"] == 0.7

    assert (
        client.delete(f"/api/studio/workflows/{workflow_id}/agents/{agent_id}").status_code == 204
    )
    remaining = client.get(f"/api/studio/workflows/{workflow_id}").json()["agents"]
    assert agent_id not in [a["agent_id"] for a in remaining]


def test_deleting_agent_removes_its_edges(client):
    workflow_id = client.post("/api/studio/workflows", json=_workflow_body()).json()["workflow_id"]
    client.delete(f"/api/studio/workflows/{workflow_id}/agents/writer")
    detail = client.get(f"/api/studio/workflows/{workflow_id}").json()
    assert detail["edges"] == []  # the writer→reviewer edge went with the agent


def test_edge_crud_and_invalid_edges_rejected(client):
    workflow_id = client.post(
        "/api/studio/workflows", json=_workflow_body(edges=[])
    ).json()["workflow_id"]

    ok = client.post(
        f"/api/studio/workflows/{workflow_id}/edges",
        json={"source_agent_id": "writer", "target_agent_id": "reviewer", "label": "draft"},
    )
    assert ok.status_code == 201
    edge_id = ok.json()["edge_id"]

    unknown = client.post(
        f"/api/studio/workflows/{workflow_id}/edges",
        json={"source_agent_id": "writer", "target_agent_id": "ghost"},
    )
    assert unknown.status_code == 422

    self_loop = client.post(
        f"/api/studio/workflows/{workflow_id}/edges",
        json={"source_agent_id": "writer", "target_agent_id": "writer"},
    )
    assert self_loop.status_code == 422

    assert (
        client.delete(f"/api/studio/workflows/{workflow_id}/edges/{edge_id}").status_code == 204
    )


# ----------------------------------------------------------------- validation


def test_cycle_rejected_with_clear_error(client):
    body = _workflow_body(
        edges=[
            {"edge_id": "e1", "source_agent_id": "writer", "target_agent_id": "reviewer"},
            {"edge_id": "e2", "source_agent_id": "reviewer", "target_agent_id": "writer"},
        ]
    )
    workflow_id = client.post("/api/studio/workflows", json=body).json()["workflow_id"]
    verdict = client.post(f"/api/studio/workflows/{workflow_id}/validate").json()
    assert verdict["valid"] is False
    assert "Cycles are not supported in v0.8. Please use a DAG workflow." in verdict["errors"]
    run = client.post(f"/api/studio/workflows/{workflow_id}/run", json={"input": RUN_INPUT})
    assert run.status_code == 422


def test_unknown_provider_and_mock_model_rejected(client):
    body = _workflow_body()
    body["agents"][0]["provider"] = "ghost-provider"
    body["agents"][1]["model_name"] = "mock:does-not-exist"
    workflow_id = client.post("/api/studio/workflows", json=body).json()["workflow_id"]
    verdict = client.post(f"/api/studio/workflows/{workflow_id}/validate").json()
    assert verdict["valid"] is False
    assert any("unknown provider 'ghost-provider'" in e for e in verdict["errors"])
    assert any("unknown mock model 'mock:does-not-exist'" in e for e in verdict["errors"])


def test_empty_workflow_invalid(client):
    workflow_id = client.post(
        "/api/studio/workflows", json={"name": "Empty", "project_id": "proj-1"}
    ).json()["workflow_id"]
    verdict = client.post(f"/api/studio/workflows/{workflow_id}/validate").json()
    assert verdict["valid"] is False
    assert "Workflow must contain at least one agent." in verdict["errors"]


def test_unconfigured_real_provider_warns_but_is_valid(client):
    body = _workflow_body()
    body["agents"][1]["provider"] = "anthropic"
    body["agents"][1]["model_name"] = "claude-sonnet-4-6"
    workflow_id = client.post("/api/studio/workflows", json=body).json()["workflow_id"]
    verdict = client.post(f"/api/studio/workflows/{workflow_id}/validate").json()
    assert verdict["valid"] is True
    assert any("not configured" in w for w in verdict["warnings"])


# ------------------------------------------------------------------ execution


def test_run_creates_normal_agentlab_run_with_full_telemetry(client):
    workflow_id = client.post("/api/studio/workflows", json=_workflow_body()).json()["workflow_id"]
    result = client.post(
        f"/api/studio/workflows/{workflow_id}/run", json={"input": RUN_INPUT}
    ).json()
    run_id = result["run_id"]
    assert result["status"] == "completed"

    run = client.get(f"/api/runs/{run_id}").json()
    assert run["name"] == "Test Team"
    assert run["status"] == "completed"
    assert run["total_tokens"] > 0

    events = client.get(f"/api/runs/{run_id}/events").json()
    types = [e["event_type"] for e in events]
    for expected in ("run.started", "agent.started", "model.called", "model.completed",
                     "message.sent", "message.received", "agent.completed", "run.completed"):
        assert expected in types, f"missing {expected}"

    # Studio metadata reaches the inspector.
    model_done = next(e for e in events if e["event_type"] == "model.completed")
    assert model_done["metadata"]["source"] == "studio"
    assert model_done["metadata"]["workflow_id"] == workflow_id
    assert model_done["metadata"]["workflow_name"] == "Test Team"
    assert model_done["metadata"]["agent_definition_id"] in ("writer", "reviewer")
    started = next(e for e in events if e["event_type"] == "agent.started"
                   and e["source_agent_id"] == "reviewer")
    assert started["metadata"]["upstream_agents"] == ["writer"]
    assert started["metadata"]["downstream_agents"] == []

    # Run history is recorded for the Studio sidebar.
    history = client.get(f"/api/studio/workflows/{workflow_id}/runs").json()
    assert history[0]["run_id"] == run_id
    assert history[0]["status"] == "completed"


def test_run_appears_in_graph_replay_costs_scores(client):
    workflow_id = client.post("/api/studio/workflows", json=_workflow_body()).json()["workflow_id"]
    run_id = client.post(
        f"/api/studio/workflows/{workflow_id}/run", json={"input": RUN_INPUT}
    ).json()["run_id"]

    graph = client.get(f"/api/runs/{run_id}/graph").json()
    assert {n["id"] for n in graph["nodes"]} == {"writer", "reviewer"}
    assert len(graph["edges"]) == 1

    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert replay["event_count"] > 0
    assert replay["status"] == "completed"

    costs = client.get(f"/api/runs/{run_id}/costs").json()
    assert costs["total_tokens"] > 0
    assert costs["estimated_cost_usd"] > 0
    assert costs["most_expensive_agent"] in ("writer", "reviewer")
    by_agent = {a["agent_id"] for a in costs["agent_breakdown"]}
    assert by_agent == {"writer", "reviewer"}

    scores = client.get(f"/api/runs/{run_id}/scores").json()
    by_id = {a["agent_id"]: a for a in scores["agents"]}
    assert by_id["writer"]["tier"] == "trusted"  # clean run stays high trust
    assert by_id["writer"]["risk_score"] == 0.0


def test_failing_agent_fails_cleanly_and_skips_downstream(client):
    body = _workflow_body()
    # The mock provider fails when the agent's metadata asks it to.
    body["agents"][0]["metadata"] = {"simulate_failure": True}
    workflow_id = client.post("/api/studio/workflows", json=body).json()["workflow_id"]
    result = client.post(
        f"/api/studio/workflows/{workflow_id}/run", json={"input": RUN_INPUT}
    ).json()
    assert result["status"] == "failed"
    run_id = result["run_id"]

    events = client.get(f"/api/runs/{run_id}/events").json()
    types = [e["event_type"] for e in events]
    assert "model.failed" in types
    assert "agent.failed" in types
    assert types[-1] == "run.failed"
    run_failed = next(e for e in events if e["event_type"] == "run.failed")
    assert run_failed["payload"]["failed_agents"] == ["writer"]
    assert run_failed["payload"]["skipped_agents"] == ["reviewer"]  # downstream never ran
    assert types.count("agent.started") == 1

    # Failure degrades reliability without flagging the agent as malicious.
    scores = client.get(f"/api/runs/{run_id}/scores").json()
    writer = next(a for a in scores["agents"] if a["agent_id"] == "writer")
    assert writer["trust_score"] < 1.0
    assert writer["risk_score"] > 0.0
    assert writer["tier"] != "high-risk"


def test_unconfigured_real_provider_fails_with_model_failed(client):
    body = _workflow_body()
    body["agents"] = [
        {"agent_id": "solo", "name": "Solo", "role": "writer",
         "provider": "anthropic", "model_name": "claude-sonnet-4-6"}
    ]
    body["edges"] = []
    workflow_id = client.post("/api/studio/workflows", json=body).json()["workflow_id"]
    result = client.post(
        f"/api/studio/workflows/{workflow_id}/run", json={"input": RUN_INPUT}
    ).json()
    assert result["status"] == "failed"
    events = client.get(f"/api/runs/{result['run_id']}/events").json()
    failed = next(e for e in events if e["event_type"] == "model.failed")
    assert "not configured" in failed["payload"]["error"]


def test_no_raw_key_in_studio_responses(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/studio-keys.db",
        api_keys="",
        cors_origins="",
        anthropic_api_key="sk-ant-studio-secret-key-7777",
    )
    with TestClient(create_app(settings)) as client:
        body = _workflow_body()
        body["agents"][1]["provider"] = "anthropic"
        body["agents"][1]["model_name"] = "claude-sonnet-4-6"
        created = client.post("/api/studio/workflows", json=body)
        workflow_id = created.json()["workflow_id"]
        responses = [
            created.text,
            client.get(f"/api/studio/workflows/{workflow_id}").text,
            client.post(f"/api/studio/workflows/{workflow_id}/validate").text,
            client.post(f"/api/studio/workflows/{workflow_id}/run", json={"input": RUN_INPUT}).text,
        ]
        run_id = __import__("json").loads(responses[-1])["run_id"]
        responses.append(client.get(f"/api/runs/{run_id}/events").text)
        for text in responses:
            assert "sk-ant-studio-secret-key-7777" not in text


def test_run_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/studio-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        seeded = next(
            w for w in client.get("/api/studio/workflows").json()
            if w["name"] == SEED_WORKFLOW_NAME
        )
        url = f"/api/studio/workflows/{seeded['workflow_id']}/run"
        assert client.post(url, json={"input": RUN_INPUT}).status_code == 401
        ok = client.post(url, json={"input": RUN_INPUT}, headers={"X-API-Key": "k1"})
        assert ok.status_code == 201
