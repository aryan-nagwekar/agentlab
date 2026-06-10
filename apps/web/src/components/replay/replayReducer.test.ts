/**
 * Pins the client fold to the same semantics as the backend
 * (apps/api/tests/test_replay.py uses the equivalent 18-event tape).
 */
import { describe, expect, it } from "vitest";

import type { AgentLabEvent } from "../../lib/types";
import { foldReplayGraph, nextMarker } from "./replayReducer";

let counter = 0;
function makeEvent(
  eventType: string,
  options: {
    source?: string | null;
    target?: string | null;
    payload?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  } = {},
): AgentLabEvent {
  counter += 1;
  return {
    id: counter,
    event_id: `evt-${counter}`,
    event_type: eventType,
    timestamp: new Date(Date.UTC(2026, 5, 9, 12, 0, 0, counter * 10)).toISOString(),
    project_id: "proj-1",
    run_id: "run-1",
    source_agent_id: options.source ?? null,
    target_agent_id: options.target ?? null,
    payload: options.payload ?? {},
    metadata: options.metadata ?? {},
  };
}

const tape: AgentLabEvent[] = [
  makeEvent("run.started", { payload: { name: "pipeline" } }),
  makeEvent("agent.started", { source: "planner", payload: { name: "PlannerAgent", role: "planner" } }),
  makeEvent("routing.decision", { source: "planner", target: "researcher", payload: { selected_agent_id: "researcher" } }),
  makeEvent("message.sent", { source: "planner", target: "researcher", payload: { content: { task: "research" } }, metadata: { message_id: "m1" } }),
  makeEvent("message.received", { source: "planner", target: "researcher", payload: { latency_ms: 120 }, metadata: { message_id: "m1" } }),
  makeEvent("agent.started", { source: "researcher", payload: { name: "ResearchAgent", role: "researcher" } }),
  makeEvent("tool.called", { source: "researcher", payload: { tool_name: "web.search" } }),
  makeEvent("tool.completed", { source: "researcher", payload: { tool_name: "web.search", latency_ms: 200 } }),
  makeEvent("model.called", { source: "researcher", payload: { model: "sim-fable-5" } }),
  makeEvent("model.completed", { source: "researcher", payload: { total_tokens: 150, cost_estimate: 0.012, latency_ms: 350 } }),
  makeEvent("agent.completed", { source: "researcher", payload: { latency_ms: 600 } }),
  makeEvent("message.sent", { source: "researcher", target: "coder", metadata: { message_id: "m2" } }),
  makeEvent("message.received", { source: "researcher", target: "coder", payload: { latency_ms: 80 }, metadata: { message_id: "m2" } }),
  makeEvent("agent.started", { source: "coder", payload: { name: "CodingAgent", role: "coder" } }),
  makeEvent("tool.called", { source: "coder", payload: { tool_name: "code.lint" } }),
  makeEvent("tool.failed", { source: "coder", payload: { tool_name: "code.lint", error: "boom", latency_ms: 50 } }),
  makeEvent("agent.failed", { source: "coder", payload: { error: "RuntimeError", latency_ms: 300 } }),
  makeEvent("run.failed", { payload: { error: "RuntimeError" } }),
];

const at = (index: number) => foldReplayGraph(tape.slice(0, index + 1), "run-1", "proj-1");
const nodesById = (index: number) =>
  Object.fromEntries(at(index).nodes.map((node) => [node.id, node]));
const edgesById = (index: number) =>
  Object.fromEntries(at(index).edges.map((edge) => [edge.id, edge]));

describe("foldReplayGraph", () => {
  it("shows the message sent but not yet delivered at index 3", () => {
    const nodes = nodesById(3);
    expect(Object.keys(nodes).sort()).toEqual(["planner", "researcher"]);
    expect(nodes.planner.status).toBe("running");
    expect(nodes.planner.name).toBe("PlannerAgent");
    expect(nodes.planner.messages_out).toBe(1);
    expect(nodes.researcher.status).toBe("unknown");
    expect(nodes.researcher.messages_in).toBe(1);
    const edge = edgesById(3)["planner->researcher"];
    expect(edge.message_count).toBe(1);
    expect(edge.last_status).toBe("sent");
    expect(edge.avg_latency_ms).toBeNull();
  });

  it("records delivery latency at index 4", () => {
    const edge = edgesById(4)["planner->researcher"];
    expect(edge.last_status).toBe("delivered");
    expect(edge.avg_latency_ms).toBe(120);
  });

  it("accumulates researcher stats by index 10", () => {
    const researcher = nodesById(10).researcher;
    expect(researcher.status).toBe("idle");
    expect(researcher.name).toBe("ResearchAgent");
    expect(researcher.avg_latency_ms).toBe(600);
    expect(researcher.tokens).toBe(150);
    expect(researcher.cost_estimate).toBe(0.012);
    expect(researcher.tool_calls).toBe(1);
    expect(nodesById(10).coder).toBeUndefined();
  });

  it("marks the coder failed with two errors at index 16", () => {
    const coder = nodesById(16).coder;
    expect(coder.status).toBe("failed");
    expect(coder.errors).toBe(2);
    expect(Object.keys(edgesById(16)).sort()).toEqual([
      "planner->researcher",
      "researcher->coder",
    ]);
  });

  it("is stable for the full tape and sorts deterministically", () => {
    const graph = at(tape.length - 1);
    expect(graph.nodes.map((n) => n.id)).toEqual(["coder", "planner", "researcher"]);
    expect(graph.edges.map((e) => e.id)).toEqual([
      "planner->researcher",
      "researcher->coder",
    ]);
  });

  it("returns an empty graph for an empty slice", () => {
    const graph = foldReplayGraph([], "run-1", "proj-1");
    expect(graph.nodes).toEqual([]);
    expect(graph.edges).toEqual([]);
  });
});

describe("fault injection folding (Lab Mode)", () => {
  const base = () => [
    makeEvent("run.started"),
    makeEvent("agent.started", { source: "researcher", payload: { name: "ResearchAgent" } }),
  ];
  const fold = (events: AgentLabEvent[]) => foldReplayGraph(events, "run-1", "proj-1");
  const ids = (events: AgentLabEvent[]) => fold(events).nodes.map((n) => n.id);

  it("kill_agent: fault + agent.failed turns the node failed, no lab-controller node", () => {
    const events = [
      ...base(),
      makeEvent("fault.injected", {
        source: "lab-controller",
        target: "researcher",
        payload: { fault_type: "kill_agent" },
        metadata: { safe_simulation: true, created_by: "lab" },
      }),
      makeEvent("agent.failed", {
        source: "researcher",
        payload: { error: "SimulatedCrash", latency_ms: 0 },
      }),
    ];
    const graph = fold(events);
    const researcher = graph.nodes.find((n) => n.id === "researcher")!;
    expect(researcher.status).toBe("failed");
    expect(researcher.errors).toBe(1);
    expect(ids(events)).not.toContain("lab-controller");
  });

  it("fault.injected alone changes no workflow state", () => {
    const events = [
      ...base(),
      makeEvent("fault.injected", {
        source: "lab-controller",
        target: "researcher",
        payload: { fault_type: "kill_agent" },
      }),
    ];
    const researcher = fold(events).nodes.find((n) => n.id === "researcher")!;
    expect(researcher.status).toBe("running");
    expect(researcher.errors).toBe(0);
    expect(ids(events)).toEqual(["researcher"]);
  });

  it("overload_agent: heartbeat flips the node to overloaded", () => {
    const events = [
      ...base(),
      makeEvent("fault.injected", {
        source: "lab-controller",
        target: "researcher",
        payload: { fault_type: "overload_agent" },
      }),
      makeEvent("agent.heartbeat", {
        source: "researcher",
        payload: { status: "overloaded", stats: { queue_depth: 250 } },
      }),
    ];
    expect(fold(events).nodes.find((n) => n.id === "researcher")!.status).toBe("overloaded");
  });

  it("drop_messages: sent + failed marks the edge failed", () => {
    const events = [
      ...base(),
      makeEvent("message.sent", {
        source: "researcher",
        target: "coder",
        metadata: { message_id: "mx" },
      }),
      makeEvent("message.failed", {
        source: "researcher",
        target: "coder",
        payload: { error: "SimulatedDrop" },
        metadata: { message_id: "mx" },
      }),
    ];
    const edge = fold(events).edges.find((e) => e.id === "researcher->coder")!;
    expect(edge.message_count).toBe(1);
    expect(edge.last_status).toBe("failed");
    const researcher = fold(events).nodes.find((n) => n.id === "researcher")!;
    expect(researcher.errors).toBe(1); // message.failed attributed to sender
  });

  it("delay_messages: delivery latency lands on the edge", () => {
    const events = [
      ...base(),
      makeEvent("message.sent", {
        source: "researcher",
        target: "coder",
        metadata: { message_id: "md" },
      }),
      makeEvent("message.received", {
        source: "researcher",
        target: "coder",
        payload: { latency_ms: 5000 },
        metadata: { message_id: "md" },
      }),
    ];
    const edge = fold(events).edges.find((e) => e.id === "researcher->coder")!;
    expect(edge.avg_latency_ms).toBe(5000);
    expect(edge.last_status).toBe("delivered");
  });
});

describe("nextMarker", () => {
  it("finds the next strictly-after marker", () => {
    expect(nextMarker([15, 16, 17], 10)).toBe(15);
    expect(nextMarker([15, 16, 17], 15)).toBe(16);
    expect(nextMarker([15, 16, 17], 17)).toBeNull();
    expect(nextMarker([], 0)).toBeNull();
  });
});
