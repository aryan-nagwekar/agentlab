"""Model gateway: providers, health, test-call telemetry, and key safety."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_gateway.base import redact_key


# ----------------------------------------------------------------- redaction


def test_redact_key():
    assert redact_key("sk-1234567890abcd") == "sk-...abcd"
    assert redact_key("short") == "***"
    assert redact_key("") is None
    assert redact_key(None) is None


def test_build_model_events_full_output_opt_in():
    from app.model_gateway import build_model_events
    from app.model_gateway.base import ModelRequest, ModelResponse

    long_answer = "A" * 5000
    req = ModelRequest(provider="mock", model_name="mock:x", prompt="hi", run_id="r1")
    resp = ModelResponse(provider="mock", model_name="mock:x", output_text=long_answer,
                         latency_ms=1, status="completed")

    # Default (runtime/test-call): short preview only — the full answer is NOT persisted.
    _called, done = build_model_events(req, resp)
    assert done.payload["output_preview"] == long_answer[:200]
    assert "output_text" not in done.payload

    # Studio opts in: the complete answer is persisted (bounded).
    _called, done_full = build_model_events(req, resp, full_output=True)
    assert done_full.payload["output_text"] == long_answer
    assert done_full.payload["output_preview"] == long_answer[:200]


# ----------------------------------------------------------------- providers


def test_list_providers_mock_available(client):
    data = client.get("/api/model-gateway/providers").json()
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["mock"]["configured"] is True
    assert by_name["mock"]["status"] == "available"
    assert "mock:claude-sonnet" in by_name["mock"]["models"]
    # real providers without keys are present but not configured
    assert by_name["anthropic"]["configured"] is False
    assert by_name["anthropic"]["status"] == "not_configured"
    assert by_name["openai"]["status"] == "not_configured"


def test_provider_health(client):
    assert client.get("/api/model-gateway/providers/mock/health").json()["status"] == "available"
    assert (
        client.get("/api/model-gateway/providers/anthropic/health").json()["status"]
        == "not_configured"
    )
    assert client.get("/api/model-gateway/providers/nope/health").status_code == 404


def test_no_raw_key_in_provider_list():
    settings = Settings(
        database_url="sqlite:///:memory:",
        api_keys="",
        cors_origins="",
        openai_api_key="sk-supersecret-REAL-key-1234",
        anthropic_api_key="sk-ant-anothersecret-5678",
        gemini_api_key="AIzaSyFAKE-gemini-secret-key-9876",
    )
    with TestClient(create_app(settings)) as client:
        raw = client.get("/api/model-gateway/providers").text
        assert "sk-supersecret-REAL-key-1234" not in raw
        assert "sk-ant-anothersecret-5678" not in raw
        assert "AIzaSyFAKE-gemini-secret-key-9876" not in raw
        by_name = {p["name"]: p for p in client.get("/api/model-gateway/providers").json()["providers"]}
        # only a redacted hint is exposed
        assert by_name["openai"]["configured"] is True
        assert by_name["openai"]["key_redacted"] == "sk-...1234"
        assert by_name["openai"]["status"] == "available"
        # the redacted hint must not be the full key
        assert "supersecret" not in by_name["openai"]["key_redacted"]
        assert by_name["gemini"]["key_redacted"] == "AIz...9876"
        assert "gemini-secret" not in by_name["gemini"]["key_redacted"]


# ----------------------------------------------------------------- test-call


def _seed_run(client, event_factory):
    client.post(
        "/api/events",
        json={
            "events": [
                event_factory("run.started", payload={"name": "gw"}),
                event_factory("agent.started", source="planner", payload={"name": "Planner"}),
            ]
        },
    )


def test_test_call_mock_emits_telemetry(client, event_factory):
    _seed_run(client, event_factory)
    body = {
        "provider": "mock",
        "model_name": "mock:claude-sonnet",
        "prompt": "Say hello from AgentLab.",
        "agent_id": "planner",
        "project_id": "proj-1",
        "run_id": "run-1",
    }
    response = client.post("/api/model-gateway/test-call", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["total_tokens"] > 0
    assert result["event_id"]
    assert "mock:claude-sonnet" in result["output_text"]

    # telemetry landed in the run
    types = [e["event_type"] for e in client.get("/api/runs/run-1/events").json()]
    assert "model.called" in types
    assert "model.completed" in types


def test_test_call_mock_failure(client, event_factory):
    _seed_run(client, event_factory)
    body = {
        "provider": "mock",
        "model_name": "mock:gpt-4.1",
        "prompt": "fail please",
        "agent_id": "planner",
        "project_id": "proj-1",
        "run_id": "run-1",
        "simulate_failure": True,
    }
    result = client.post("/api/model-gateway/test-call", json=body).json()
    assert result["status"] == "failed"
    assert "Simulated provider failure" in result["error_message"]
    types = [e["event_type"] for e in client.get("/api/runs/run-1/events").json()]
    assert "model.failed" in types


def test_run_model_call_endpoint(client, event_factory):
    _seed_run(client, event_factory)
    body = {
        "provider": "mock",
        "model_name": "mock:gpt-4.1",
        "prompt": "Research multi-agent security.",
        "agent_id": "planner",
        "project_id": "proj-1",
    }
    result = client.post("/api/runs/run-1/model-call", json=body).json()
    assert result["status"] == "completed"


def test_gateway_events_flow_into_costs(client, event_factory):
    _seed_run(client, event_factory)
    for _ in range(3):
        client.post(
            "/api/runs/run-1/model-call",
            json={
                "provider": "mock",
                "model_name": "mock:claude-sonnet",
                "prompt": "compute something expensive " * 5,
                "agent_id": "planner",
                "project_id": "proj-1",
            },
        )
    costs = client.get("/api/runs/run-1/costs").json()
    assert costs["total_tokens"] > 0
    assert costs["estimated_cost_usd"] > 0
    by_agent = {a["agent_id"]: a for a in costs["agent_breakdown"]}
    assert by_agent["planner"]["model_call_count"] == 3
    assert by_agent["planner"]["most_used_model"] == "mock:claude-sonnet"


def test_unknown_provider_validation(client, event_factory):
    _seed_run(client, event_factory)
    response = client.post(
        "/api/model-gateway/test-call",
        json={"provider": "ghost", "model_name": "x", "prompt": "hi", "run_id": "run-1"},
    )
    assert response.status_code == 422


def test_unknown_mock_model_validation(client, event_factory):
    _seed_run(client, event_factory)
    response = client.post(
        "/api/model-gateway/test-call",
        json={"provider": "mock", "model_name": "mock:does-not-exist", "prompt": "hi", "run_id": "run-1"},
    )
    assert response.status_code == 422


def test_test_call_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/gw-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        body = {"provider": "mock", "model_name": "mock:gpt-4.1", "prompt": "hi"}
        assert client.post("/api/model-gateway/test-call", json=body).status_code == 401
        ok = client.post("/api/model-gateway/test-call", json=body, headers={"X-API-Key": "k1"})
        assert ok.status_code == 200


def test_test_call_without_run_does_not_crash(client):
    # No run_id -> returns a response but emits no telemetry
    result = client.post(
        "/api/model-gateway/test-call",
        json={"provider": "mock", "model_name": "mock:gpt-4.1", "prompt": "hello"},
    ).json()
    assert result["status"] == "completed"
    assert result["event_id"] is None


def test_default_demo_works_without_any_keys(client):
    # The mock provider must be fully usable with zero env keys configured.
    data = client.get("/api/model-gateway/providers").json()
    mock = next(p for p in data["providers"] if p["name"] == "mock")
    assert mock["requires_key"] is False
    assert mock["configured"] is True


# ------------------------------------------------------------ gemini (v0.7.1)


def test_gemini_in_registry_not_configured_without_key():
    settings = Settings(
        database_url="sqlite:///:memory:", api_keys="", cors_origins="", gemini_api_key=""
    )
    with TestClient(create_app(settings)) as client:
        by_name = {
            p["name"]: p for p in client.get("/api/model-gateway/providers").json()["providers"]
        }
        gemini = by_name["gemini"]
        assert gemini["requires_key"] is True
        assert gemini["configured"] is False
        assert gemini["status"] == "not_configured"
        assert "GEMINI_API_KEY" in gemini["message"]
        assert "gemini-2.0-flash" in gemini["models"]


def test_gemini_configured_with_key_is_redacted(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/gem.db",
        api_keys="",
        cors_origins="",
        gemini_api_key="AIzaSyFAKE-configured-key-5432",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/model-gateway/providers")
        assert "AIzaSyFAKE-configured-key-5432" not in response.text
        gemini = next(p for p in response.json()["providers"] if p["name"] == "gemini")
        assert gemini["configured"] is True
        assert gemini["status"] == "available"
        assert gemini["key_redacted"] == "AIz...5432"
        health = client.get("/api/model-gateway/providers/gemini/health")
        assert "AIzaSyFAKE-configured-key-5432" not in health.text
        assert health.json()["status"] == "available"


def test_gemini_call_failure_is_captured_safely(tmp_path, event_factory):
    # Port 9 (discard) refuses connections instantly — no real network traffic.
    # The key travels as a URL query param, so this also proves a failed call
    # never echoes the URL (and therefore the key) back to the client.
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/gemfail.db",
        api_keys="",
        cors_origins="",
        gemini_api_key="AIzaSyFAKE-leaky-key-test-4321",
        gemini_base_url="http://127.0.0.1:9/v1beta",
    )
    with TestClient(create_app(settings)) as client:
        _seed_run(client, event_factory)
        response = client.post(
            "/api/model-gateway/test-call",
            json={
                "provider": "gemini",
                "model_name": "gemini-2.0-flash",
                "prompt": "hello",
                "agent_id": "planner",
                "project_id": "proj-1",
                "run_id": "run-1",
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "failed"
        assert result["error_message"]
        assert "AIzaSyFAKE-leaky-key-test-4321" not in response.text
        events_response = client.get("/api/runs/run-1/events")
        assert "AIzaSyFAKE-leaky-key-test-4321" not in events_response.text
        types = [e["event_type"] for e in events_response.json()]
        assert "model.failed" in types


# ------------------------------------------- ollama troubleshooting (v0.7.1)


def test_ollama_unavailable_returns_troubleshooting_message(tmp_path):
    # Point at the discard port so the health check fails fast and predictably.
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/oll.db",
        api_keys="",
        cors_origins="",
        ollama_base_url="http://127.0.0.1:9",
    )
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/model-gateway/providers/ollama/health").json()
        assert health["status"] == "unavailable"
        assert "http://127.0.0.1:9" in health["detail"]
        assert "ollama serve" in health["detail"]
        assert "host.docker.internal" in health["detail"]
        # the providers list carries the same hint as `message`
        providers = client.get("/api/model-gateway/providers").json()["providers"]
        ollama = next(p for p in providers if p["name"] == "ollama")
        assert ollama["message"] == health["detail"]


def test_ollama_timeout_is_configurable(tmp_path):
    # The Ollama completion timeout (too low at 300s for a 7B model building a
    # full page) is settable so local-model builds can finish.
    from app.model_gateway import build_registry

    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/oll2.db",
        api_keys="",
        cors_origins="",
        ollama_timeout_seconds=900.0,
    )
    registry = build_registry(settings)
    assert registry.get("ollama")._timeout_seconds == 900.0
    # default is generous for local models
    assert Settings().ollama_timeout_seconds == 600.0
