"""Replay tape, jump markers, and cursor-position topology reconstruction.

The seeded_run fixture (conftest) produces this 18-event tape:

  idx  event
  0    run.started
  1    agent.started   planner
  2    routing.decision planner -> researcher
  3    message.sent     planner -> researcher (m1)
  4    message.received planner -> researcher (m1, 120ms)
  5    agent.started   researcher
  6    tool.called     researcher (t1)
  7    tool.completed  researcher (t1, 200ms)
  8    model.called    researcher
  9    model.completed researcher (150 tok, $0.012, 350ms)
  10   agent.completed researcher (600ms)
  11   message.sent     researcher -> coder (m2)
  12   message.received researcher -> coder (m2, 80ms)
  13   agent.started   coder
  14   tool.called     coder (t2)
  15   tool.failed     coder (t2, 50ms)
  16   agent.failed    coder (300ms)
  17   run.failed
"""
from __future__ import annotations


def _graph_at(client, index):
    response = client.get("/api/runs/run-1/replay/graph", params={"index": index})
    assert response.status_code == 200
    payload = response.json()
    return {n["id"]: n for n in payload["nodes"]}, {e["id"]: e for e in payload["edges"]}


def test_replay_tape_and_markers(client, seeded_run):
    replay = client.get("/api/runs/run-1/replay").json()
    assert replay["run_id"] == "run-1"
    assert replay["status"] == "failed"
    assert replay["event_count"] == len(seeded_run) == 18
    assert replay["duration_ms"] == 1500

    types = [e["event_type"] for e in replay["events"]]
    assert types[0] == "run.started"
    assert types[-1] == "run.failed"
    timestamps = [e["timestamp"] for e in replay["events"]]
    assert timestamps == sorted(timestamps)

    markers = replay["markers"]
    assert markers["errors"] == [15, 16, 17]
    assert markers["tool_calls"] == [6, 14]
    assert markers["routing"] == [2]
    assert markers["messages"] == [3, 11]
    assert markers["faults"] == []
    assert markers["attacks"] == []


def test_graph_before_message_delivery(client, seeded_run):
    nodes, edges = _graph_at(client, 3)
    # researcher exists (referenced as routing/message target) but hasn't started
    assert set(nodes) == {"planner", "researcher"}
    assert nodes["planner"]["status"] == "running"
    assert nodes["planner"]["name"] == "PlannerAgent"
    assert nodes["planner"]["messages_out"] == 1
    assert nodes["researcher"]["status"] == "unknown"
    assert nodes["researcher"]["messages_in"] == 1
    edge = edges["planner->researcher"]
    assert edge["message_count"] == 1
    assert edge["last_status"] == "sent"
    assert edge["avg_latency_ms"] is None


def test_graph_after_message_delivery(client, seeded_run):
    _, edges = _graph_at(client, 4)
    edge = edges["planner->researcher"]
    assert edge["last_status"] == "delivered"
    assert edge["avg_latency_ms"] == 120


def test_graph_mid_run_researcher_complete(client, seeded_run):
    nodes, _ = _graph_at(client, 10)
    researcher = nodes["researcher"]
    assert researcher["status"] == "idle"
    assert researcher["name"] == "ResearchAgent"
    assert researcher["avg_latency_ms"] == 600
    assert researcher["tokens"] == 150
    assert researcher["cost_estimate"] == 0.012
    assert researcher["tool_calls"] == 1
    assert "coder" not in nodes


def test_graph_at_failure(client, seeded_run):
    nodes, edges = _graph_at(client, 16)
    coder = nodes["coder"]
    assert coder["status"] == "failed"
    assert coder["errors"] == 2  # tool.failed + agent.failed
    assert set(edges) == {"planner->researcher", "researcher->coder"}


def test_index_clamps_and_matches_live_graph(client, seeded_run):
    nodes_full, edges_full = _graph_at(client, 9_999)
    live = client.get("/api/runs/run-1/graph").json()
    live_nodes = {n["id"]: n for n in live["nodes"]}
    assert set(nodes_full) == set(live_nodes)
    for agent_id, node in nodes_full.items():
        for field in ("status", "messages_in", "messages_out", "tool_calls", "errors", "tokens"):
            assert node[field] == live_nodes[agent_id][field], (agent_id, field)
    assert {e for e in edges_full} == {e["id"] for e in live["edges"]}


def test_replay_empty_run(client, event_factory):
    client.post("/api/events", json=event_factory("run.started", run="bare-run"))
    replay = client.get("/api/runs/bare-run/replay").json()
    assert replay["event_count"] == 1
    assert replay["markers"] == {
        "errors": [],
        "tool_calls": [],
        "routing": [],
        "messages": [],
        "faults": [],
        "attacks": [],
    }
    graph = client.get("/api/runs/bare-run/replay/graph", params={"index": 0}).json()
    assert graph["nodes"] == []
    assert graph["edges"] == []


def test_replay_unknown_run_404(client):
    assert client.get("/api/runs/ghost/replay").status_code == 404
    assert client.get("/api/runs/ghost/replay/graph", params={"index": 0}).status_code == 404
