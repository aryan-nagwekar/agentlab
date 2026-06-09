"""Client API tests using a fake transport (no network)."""
from __future__ import annotations

import pytest

import agentlab
from agentlab import AgentLabClient
from agentlab.client import set_default_client


class FakeTransport:
    def __init__(self):
        self.events = []

    def enqueue(self, event):
        self.events.append(event)

    def flush(self, timeout=None):
        return True

    def close(self, timeout=None):
        pass


@pytest.fixture
def client():
    c = AgentLabClient("proj-test", disabled=True, set_as_default=True)
    c._transport = FakeTransport()
    yield c
    c._transport = None
    c.close()
    set_default_client(None)


def events_of(client, *types):
    evts = client._transport.events
    return [e for e in evts if not types or e["event_type"] in types]


def test_run_context_manager_emits_lifecycle(client):
    with client.run(name="demo-run") as run:
        run_id = run.id
    types = [e["event_type"] for e in events_of(client)]
    assert types == ["run.started", "run.completed"]
    started, completed = events_of(client)
    assert started["run_id"] == run_id
    assert started["payload"]["name"] == "demo-run"
    assert completed["payload"]["total_latency_ms"] >= 0
    assert started["project_id"] == "proj-test"
    assert started["timestamp"].endswith("Z")


def test_run_failure_emits_run_failed(client):
    with pytest.raises(ValueError):
        with client.run(name="bad-run"):
            raise ValueError("boom")
    types = [e["event_type"] for e in events_of(client)]
    assert types == ["run.started", "run.failed"]
    assert "ValueError: boom" in events_of(client)[1]["payload"]["error"]


def test_trace_agent_success_and_slug(client):
    @client.trace_agent(name="SecurityReviewAgent", role="security")
    def review():
        return "ok"

    with client.run("r"):
        assert review() == "ok"

    started = events_of(client, "agent.started")[0]
    completed = events_of(client, "agent.completed")[0]
    assert started["source_agent_id"] == "security-review-agent"
    assert started["payload"] == {"name": "SecurityReviewAgent", "role": "security"}
    assert completed["payload"]["latency_ms"] >= 0


def test_trace_agent_failure_propagates(client):
    @client.trace_agent(name="Flaky")
    def flaky():
        raise RuntimeError("nope")

    with client.run("r"):
        with pytest.raises(RuntimeError):
            flaky()

    failed = events_of(client, "agent.failed")[0]
    assert "RuntimeError: nope" in failed["payload"]["error"]
    assert "traceback" in failed["payload"]
    assert events_of(client, "agent.completed") == []


def test_nested_agents_record_parentage(client):
    @client.trace_agent(name="Child")
    def child():
        with client.trace_tool("calc", input={"x": 1}) as span:
            span.output = 2
        return "done"

    @client.trace_agent(name="Parent")
    def parent():
        return child()

    with client.run("r"):
        parent()

    parent_started = [
        e for e in events_of(client, "agent.started") if e["source_agent_id"] == "parent"
    ][0]
    child_started = [
        e for e in events_of(client, "agent.started") if e["source_agent_id"] == "child"
    ][0]
    assert child_started["payload"]["parent_agent_id"] == "parent"
    assert child_started["metadata"]["parent_event_id"] == parent_started["event_id"]

    tool_called = events_of(client, "tool.called")[0]
    assert tool_called["source_agent_id"] == "child"
    assert tool_called["metadata"]["parent_event_id"] == child_started["event_id"]


def test_send_message_links_sent_and_received(client):
    @client.trace_agent(name="Planner")
    def plan():
        return client.send_message("researcher", {"task": "dig"}, latency_ms=12.5)

    with client.run("r"):
        mid = plan()

    sent = events_of(client, "message.sent")[0]
    received = events_of(client, "message.received")[0]
    assert sent["metadata"]["message_id"] == mid
    assert received["metadata"]["message_id"] == mid
    assert sent["source_agent_id"] == "planner"
    assert sent["target_agent_id"] == "researcher"
    assert sent["payload"]["content"] == {"task": "dig"}
    assert received["payload"]["latency_ms"] == 12.5


def test_failed_message(client):
    with client.run("r"):
        client.send_message("x", "hi", source_agent_id="a", status="failed", error="net down")
    types = [e["event_type"] for e in events_of(client)]
    assert "message.failed" in types
    assert "message.received" not in types


def test_trace_tool_failure(client):
    with client.run("r"):
        with pytest.raises(KeyError):
            with client.trace_tool("db.lookup", input={"k": "v"}, agent_id="researcher"):
                raise KeyError("missing")
    failed = events_of(client, "tool.failed")[0]
    assert failed["payload"]["tool_name"] == "db.lookup"
    assert failed["source_agent_id"] == "researcher"
    assert failed["payload"]["latency_ms"] >= 0


def test_log_model_call_totals(client):
    with client.run("r"):
        client.log_model_call(
            "fable-5",
            prompt_tokens=120,
            completion_tokens=80,
            latency_ms=400,
            cost_estimate=0.0123,
            agent_id="coder",
        )
    completed = events_of(client, "model.completed")[0]
    assert completed["payload"]["total_tokens"] == 200
    assert completed["payload"]["cost_estimate"] == 0.0123
    assert events_of(client, "model.called")[0]["source_agent_id"] == "coder"


def test_routing_decision_payload(client):
    candidates = [
        {"agent_id": "fast", "trust_score": 0.7},
        {"agent_id": "deep", "trust_score": 0.95},
    ]
    with client.run("r"):
        client.routing_decision(
            candidates=candidates,
            selected_agent_id="deep",
            reason="high risk task",
            confidence=0.9,
            task="security review",
            source_agent_id="planner",
        )
    evt = events_of(client, "routing.decision")[0]
    assert evt["target_agent_id"] == "deep"
    assert evt["payload"]["candidate_agents"] == candidates
    assert evt["payload"]["reason"] == "high risk task"


def test_update_trust_clamps(client):
    with client.run("r"):
        client.update_trust("sketchy", 1.7, reason="test")
        client.update_trust("sketchy", -2)
    scores = [e["payload"]["trust_score"] for e in events_of(client, "trust.updated")]
    assert scores == [1.0, 0.0]


def test_implicit_run_created_when_missing(client):
    client.heartbeat("lonely-agent")
    types = [e["event_type"] for e in events_of(client)]
    assert types[0] == "run.started"
    assert events_of(client)[0]["payload"]["implicit"] is True
    run_ids = {e["run_id"] for e in events_of(client)}
    assert len(run_ids) == 1


def test_unknown_event_type_raises(client):
    with pytest.raises(ValueError):
        client.emit("bogus.event")


def test_sequence_monotonic(client):
    with client.run("r"):
        client.heartbeat("a")
        client.heartbeat("a")
    seqs = [e["metadata"]["_seq"] for e in events_of(client)]
    assert seqs == sorted(seqs)


def test_module_level_decorator_requires_client():
    set_default_client(None)

    @agentlab.trace_agent(name="Orphan")
    def orphan():
        return 1

    with pytest.raises(RuntimeError, match="No AgentLab client"):
        orphan()


def test_module_level_decorator_binds_late():
    set_default_client(None)

    @agentlab.trace_agent(name="LateBound", role="worker")
    def work():
        return 42

    c = AgentLabClient("proj-late", disabled=True, set_as_default=True)
    c._transport = FakeTransport()
    try:
        with c.run("r"):
            assert work() == 42
        types = [e["event_type"] for e in c._transport.events]
        assert "agent.started" in types and "agent.completed" in types
    finally:
        c._transport = None
        c.close()
        set_default_client(None)


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("AGENTLAB_DISABLED", "1")
    c = AgentLabClient("proj-env", set_as_default=False)
    try:
        assert c.disabled is True
        assert c._transport is None
        # Still safe to call every API.
        with c.run("r"):
            event_id = c.emit("agent.heartbeat", source_agent_id="a")
        assert isinstance(event_id, str)
    finally:
        c.close()
