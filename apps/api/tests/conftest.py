from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BASE_TS = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)
_tick = itertools.count(0)


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/test.db", api_keys="", cors_origins=""
    )
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def event_factory():
    """Builds valid event dicts with monotonically increasing timestamps."""

    def make(
        event_type: str,
        *,
        project="proj-1",
        run="run-1",
        source=None,
        target=None,
        payload=None,
        metadata=None,
        event_id=None,
        offset_ms=None,
    ):
        step = next(_tick) if offset_ms is None else None
        ts = BASE_TS + timedelta(milliseconds=offset_ms if offset_ms is not None else step * 10)
        return {
            "event_id": event_id or str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "project_id": project,
            "run_id": run,
            "source_agent_id": source,
            "target_agent_id": target,
            "payload": payload or {},
            "metadata": metadata or {},
        }

    return make


@pytest.fixture
def seeded_run(client, event_factory):
    """A realistic failed pipeline run: planner -> researcher -> coder (fails)."""
    events = [
        event_factory("run.started", payload={"name": "pipeline"}),
        event_factory(
            "agent.started", source="planner", payload={"name": "PlannerAgent", "role": "planner"}
        ),
        event_factory(
            "routing.decision",
            source="planner",
            target="researcher",
            payload={
                "task": "research the topic",
                "candidate_agents": [
                    {"agent_id": "researcher", "trust_score": 0.9},
                    {"agent_id": "cache", "trust_score": 0.6},
                ],
                "selected_agent_id": "researcher",
                "reason": "fresh data required",
                "confidence": 0.88,
            },
        ),
        event_factory(
            "message.sent",
            source="planner",
            target="researcher",
            payload={"content": {"task": "research X"}},
            metadata={"message_id": "m1"},
        ),
        event_factory(
            "message.received",
            source="planner",
            target="researcher",
            payload={"latency_ms": 120},
            metadata={"message_id": "m1"},
        ),
        event_factory(
            "agent.started",
            source="researcher",
            payload={"name": "ResearchAgent", "role": "researcher"},
        ),
        event_factory(
            "tool.called",
            source="researcher",
            payload={"tool_name": "web.search", "input": {"q": "X"}},
            metadata={"tool_call_id": "t1"},
        ),
        event_factory(
            "tool.completed",
            source="researcher",
            payload={"tool_name": "web.search", "output": {"hits": 3}, "latency_ms": 200},
            metadata={"tool_call_id": "t1"},
        ),
        event_factory("model.called", source="researcher", payload={"model": "sim-fable-5"}),
        event_factory(
            "model.completed",
            source="researcher",
            payload={
                "model": "sim-fable-5",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "latency_ms": 350,
                "cost_estimate": 0.012,
            },
        ),
        event_factory(
            "agent.completed",
            source="researcher",
            payload={"name": "ResearchAgent", "latency_ms": 600},
        ),
        event_factory(
            "message.sent",
            source="researcher",
            target="coder",
            payload={"content": {"summary": "findings"}},
            metadata={"message_id": "m2"},
        ),
        event_factory(
            "message.received",
            source="researcher",
            target="coder",
            payload={"latency_ms": 80},
            metadata={"message_id": "m2"},
        ),
        event_factory(
            "agent.started", source="coder", payload={"name": "CodingAgent", "role": "coder"}
        ),
        event_factory(
            "tool.called",
            source="coder",
            payload={"tool_name": "code.lint", "input": {"file": "api.py"}},
            metadata={"tool_call_id": "t2"},
        ),
        event_factory(
            "tool.failed",
            source="coder",
            payload={"tool_name": "code.lint", "error": "linter crashed", "latency_ms": 50},
            metadata={"tool_call_id": "t2"},
        ),
        event_factory(
            "agent.failed",
            source="coder",
            payload={"name": "CodingAgent", "error": "RuntimeError: lint failed", "latency_ms": 300},
        ),
        event_factory("run.failed", payload={"name": "pipeline", "total_latency_ms": 1500}),
    ]
    response = client.post("/api/events", json={"events": events})
    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": len(events), "duplicates": 0}
    return events
