"""Cost/token attribution: pricing, aggregation, endpoints, replay folding."""
from __future__ import annotations

from types import SimpleNamespace

from app import costing, pricing


def mev(event_type, source=None, **payload):
    return SimpleNamespace(
        event_type=event_type, source_agent_id=source, payload=payload
    )


# ------------------------------------------------------------------- pricing


def test_pricing_known_model():
    cost, status = pricing.estimate_cost("mock:claude-sonnet", 1000, 500)
    # 1000 * 3/1e6 + 500 * 15/1e6 = 0.003 + 0.0075 = 0.0105
    assert cost == 0.0105
    assert status == "ok"


def test_pricing_local_model_is_free():
    cost, status = pricing.estimate_cost("mock:local-ollama", 5000, 5000)
    assert cost == 0.0
    assert status == "ok"


def test_pricing_unknown_model():
    cost, status = pricing.estimate_cost("real:gpt-9", 100, 100)
    assert cost is None
    assert status == "unknown"


def test_provider_extraction():
    assert pricing.provider_of("mock:gpt-4.1") == "mock"
    assert pricing.provider_of("plainmodel") == "unknown"


# ----------------------------------------------------------------- normalize


def test_normalize_new_fields():
    call = costing.normalize_model_event(
        mev(
            "model.completed",
            source="coder",
            model_name="mock:claude-sonnet",
            provider="mock",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            latency_ms=1800,
        )
    )
    assert call.input_tokens == 1000
    assert call.output_tokens == 500
    assert call.total_tokens == 1500
    assert call.estimated_cost_usd == 0.0105
    assert call.pricing_status == "ok"


def test_normalize_legacy_fields():
    call = costing.normalize_model_event(
        mev("model.completed", source="a", model="mock:gpt-4.1", prompt_tokens=900, completion_tokens=260)
    )
    assert call.model_name == "mock:gpt-4.1"
    assert call.provider == "mock"
    assert call.input_tokens == 900
    assert call.output_tokens == 260
    assert call.total_tokens == 1160


def test_normalize_missing_tokens_graceful():
    call = costing.normalize_model_event(mev("model.completed", source="a", model="mock:gpt-4.1"))
    assert call.input_tokens == 0
    assert call.output_tokens == 0
    assert call.total_tokens == 0
    assert call.estimated_cost_usd == 0.0


def test_unknown_model_with_provided_cost():
    call = costing.normalize_model_event(
        mev("model.completed", source="a", model="custom-llm", total_tokens=100, cost_estimate=0.5)
    )
    assert call.pricing_status == "provided"
    assert call.estimated_cost_usd == 0.5


def test_unknown_model_no_cost_is_null():
    call = costing.normalize_model_event(mev("model.completed", source="a", model="custom-llm", total_tokens=100))
    assert call.estimated_cost_usd is None
    assert call.pricing_status == "unknown"


# --------------------------------------------------------------- aggregation

EVENTS = [
    mev("model.completed", source="coder", model_name="mock:claude-sonnet", input_tokens=1100, output_tokens=600, latency_ms=1800),
    mev("model.completed", source="researcher", model_name="mock:gpt-4.1", input_tokens=2400, output_tokens=300, latency_ms=900),
    mev("model.completed", source="security", model_name="mock:local-ollama", input_tokens=700, output_tokens=180, latency_ms=400),
    mev("model.called", source="coder"),
    mev("model.failed", source="security", model_name="mock:local-ollama", input_tokens=650, output_tokens=0, latency_ms=3000, error="boom"),
]


def test_run_aggregation():
    run = costing.aggregate(EVENTS)
    assert run.total_input_tokens == 1100 + 2400 + 700 + 650
    assert run.total_output_tokens == 600 + 300 + 180
    # coder: (1100*3 + 600*15)/1e6 = 0.0123
    assert run.agents["coder"].estimated_cost_usd == 0.0123
    # researcher: (2400*2 + 300*8)/1e6 = 0.0072
    assert run.agents["researcher"].estimated_cost_usd == 0.0072
    # security local-ollama free
    assert run.agents["security"].estimated_cost_usd == 0.0
    assert run.agents["security"].failed_model_call_count == 1


def test_most_expensive_and_token_heavy():
    run = costing.aggregate(EVENTS)
    assert costing._best(run.agents, "estimated_cost_usd") == "coder"
    assert costing._best(run.agents, "total_tokens") == "researcher"
    assert costing._best(run.agents, "failed_model_call_count") == "security"


def test_model_breakdown():
    run = costing.aggregate(EVENTS)
    assert run.models["mock:claude-sonnet"].call_count == 1
    assert run.models["mock:local-ollama"].failure_count == 1
    assert run.models["mock:gpt-4.1"].total_tokens == 2700


def test_retry_count():
    # one model.called for coder but only one completed -> no extra retry;
    # add a second called to simulate a retry
    events = EVENTS + [mev("model.called", source="coder")]
    run = costing.aggregate(events)
    # coder: 2 called, 1 completed -> retry_count 1
    assert run.agents["coder"].retry_count == 1


def test_replay_cost_folds_by_cursor():
    full = costing.aggregate(EVENTS)
    partial = costing.aggregate(EVENTS[:1])  # only coder's completed call
    assert partial.estimated_cost_usd == 0.0123
    assert partial.total_tokens == 1700
    assert full.estimated_cost_usd > partial.estimated_cost_usd


def test_deterministic():
    a = costing.aggregate(EVENTS)
    b = costing.aggregate(EVENTS)
    assert a.estimated_cost_usd == b.estimated_cost_usd
    assert a.total_tokens == b.total_tokens


# ------------------------------------------------------------------ endpoints


def _seed_model_run(client, event_factory):
    events = [
        event_factory("run.started", payload={"name": "cost-run"}),
        event_factory("agent.started", source="coder", payload={"name": "CodingAgent"}),
        event_factory("model.completed", source="coder", payload={
            "model_name": "mock:claude-sonnet", "provider": "mock",
            "input_tokens": 1100, "output_tokens": 600, "total_tokens": 1700, "latency_ms": 1800}),
        event_factory("agent.started", source="researcher", payload={"name": "ResearchAgent"}),
        event_factory("model.completed", source="researcher", payload={
            "model_name": "mock:gpt-4.1", "provider": "mock",
            "input_tokens": 2400, "output_tokens": 300, "total_tokens": 2700, "latency_ms": 900}),
        event_factory("model.failed", source="researcher", payload={
            "model_name": "mock:gpt-4.1", "input_tokens": 500, "output_tokens": 0, "error": "timeout"}),
        event_factory("run.completed", payload={"name": "cost-run"}),
    ]
    assert client.post("/api/events", json={"events": events}).status_code == 202


def test_run_costs_endpoint(client, event_factory):
    _seed_model_run(client, event_factory)
    data = client.get("/api/runs/run-1/costs").json()
    assert data["most_expensive_agent"] == "coder"
    assert data["most_token_heavy_agent"] == "researcher"
    assert data["highest_failure_agent"] == "researcher"
    # coder 0.0123 + researcher 0.0072 (completed) + 0.001 (failed, 500 in-tokens)
    assert data["estimated_cost_usd"] == round(0.0123 + 0.0072 + 0.001, 6)
    by_agent = {a["agent_id"]: a for a in data["agent_breakdown"]}
    assert by_agent["coder"]["estimated_cost_usd"] == 0.0123
    assert by_agent["researcher"]["failed_model_calls"] == 1
    models = {m["model_name"]: m for m in data["model_breakdown"]}
    assert models["mock:claude-sonnet"]["provider"] == "mock"


def test_token_summary_endpoint(client, event_factory):
    _seed_model_run(client, event_factory)
    data = client.get("/api/runs/run-1/token-summary").json()
    assert data["total_tokens"] == 1700 + 2700 + 500
    assert data["model_breakdown"][0]["total_tokens"] >= data["model_breakdown"][-1]["total_tokens"]


def test_agent_costs_endpoint(client, event_factory):
    _seed_model_run(client, event_factory)
    data = client.get("/api/agents/coder/costs", params={"project_id": "proj-1"}).json()
    assert data["agent_id"] == "coder"
    assert data["estimated_cost_usd"] == 0.0123
    assert data["most_used_model"] == "mock:claude-sonnet"


def test_project_cost_summary_endpoint(client, event_factory):
    _seed_model_run(client, event_factory)
    data = client.get("/api/projects/proj-1/cost-summary").json()
    # coder 0.0123 + researcher 0.0072 (completed) + 0.001 (failed, 500 in-tokens)
    assert data["estimated_cost_usd"] == round(0.0123 + 0.0072 + 0.001, 6)
    assert data["run_count"] == 1


def test_cost_endpoints_404(client):
    assert client.get("/api/runs/ghost/costs").status_code == 404
    assert client.get("/api/runs/ghost/token-summary").status_code == 404
    assert client.get("/api/agents/ghost/costs").status_code == 404
    assert client.get("/api/projects/ghost/cost-summary").status_code == 404
