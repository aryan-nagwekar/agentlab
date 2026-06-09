"""Topology graph and metrics derivation."""
from __future__ import annotations


def test_graph_nodes_and_edges(client, seeded_run):
    graph = client.get("/api/runs/run-1/graph").json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}

    assert set(nodes) == {"planner", "researcher", "coder"}

    planner = nodes["planner"]
    assert planner["name"] == "PlannerAgent"
    assert planner["role"] == "planner"
    assert planner["messages_out"] == 1
    assert planner["messages_in"] == 0

    researcher = nodes["researcher"]
    assert researcher["messages_in"] == 1
    assert researcher["messages_out"] == 1
    assert researcher["tool_calls"] == 1
    assert researcher["tokens"] == 150
    assert researcher["cost_estimate"] == 0.012
    assert researcher["avg_latency_ms"] == 600
    assert researcher["status"] == "idle"

    coder = nodes["coder"]
    assert coder["errors"] == 2
    assert coder["status"] == "failed"
    assert coder["tool_calls"] == 1

    assert set(edges) == {"planner->researcher", "researcher->coder"}
    edge1 = edges["planner->researcher"]
    assert edge1["message_count"] == 1
    assert edge1["avg_latency_ms"] == 120
    assert edge1["last_status"] == "delivered"
    assert edge1["last_message_at"].endswith("Z")


def test_metrics_totals_and_highlights(client, seeded_run):
    metrics = client.get("/api/runs/run-1/metrics").json()
    totals = metrics["totals"]
    assert totals["agents"] == 3
    assert totals["messages"] == 2
    assert totals["tool_calls"] == 2
    assert totals["model_calls"] == 1
    assert totals["tokens"] == 150
    assert totals["cost_estimate"] == 0.012
    assert totals["error_count"] == 2
    assert totals["events"] == len(seeded_run)
    # operation latencies: [600 agent, 200 tool, 350 model, 50 tool.failed, 300 agent.failed]
    assert totals["avg_latency_ms"] == 300
    assert totals["p95_latency_ms"] == 600
    assert totals["duration_ms"] is not None

    per_agent = {row["agent_id"]: row for row in metrics["per_agent"]}
    assert per_agent["researcher"]["tokens"] == 150
    assert per_agent["researcher"]["avg_latency_ms"] == 600
    assert per_agent["coder"]["errors"] == 2
    assert per_agent["planner"]["messages"] == 1

    highlights = metrics["highlights"]
    assert highlights["slowest_agent"]["agent_id"] == "researcher"
    assert highlights["slowest_agent"]["unit"] == "ms"
    assert highlights["most_expensive_agent"]["agent_id"] == "researcher"
    assert highlights["most_unreliable_agent"]["agent_id"] == "coder"
    assert highlights["most_active_agent"]["agent_id"] == "researcher"


def test_graph_empty_run(client, event_factory):
    client.post("/api/events", json=event_factory("run.started", run="lonely-run"))
    graph = client.get("/api/runs/lonely-run/graph").json()
    assert graph["nodes"] == []
    assert graph["edges"] == []
    metrics = client.get("/api/runs/lonely-run/metrics").json()
    assert metrics["totals"]["agents"] == 0
    assert metrics["highlights"]["slowest_agent"] is None
