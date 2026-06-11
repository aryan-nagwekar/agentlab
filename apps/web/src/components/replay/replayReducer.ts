/**
 * Pure event-fold: rebuilds the topology from the first N events of a run's
 * replay tape.
 *
 * Mirrors apps/api/app/replay.py `fold_events` — the two implement the SAME
 * semantics over the same wire events. Change one, change both (the backend
 * test suite pins the semantics; replayReducer.test.ts pins this mirror).
 */
import { scoreEvents } from "../../lib/scoring";
import type { AgentLabEvent, GraphEdge, GraphNode, RunGraph } from "../../lib/types";

interface EdgeAccumulator {
  count: number;
  latencies: number[];
  lastStatus: string | null;
  lastAt: string | null;
}

const round2 = (value: number) => Math.round(value * 100) / 100;
const round6 = (value: number) => Math.round(value * 1e6) / 1e6;

function asNumber(value: unknown): number | null {
  const parsed = typeof value === "string" ? Number(value) : value;
  return typeof parsed === "number" && Number.isFinite(parsed) ? parsed : null;
}

export function foldReplayGraph(
  events: AgentLabEvent[],
  runId: string,
  projectId: string,
): RunGraph {
  const participants = new Set<string>();
  const names = new Map<string, string>();
  const roles = new Map<string, string>();
  const status = new Map<string, string>();
  // Trust/risk are derived by the scoring engine mirror (lib/scoring.ts) over
  // exactly the events applied so far, so replay shows scores evolving.
  const scores = scoreEvents(events);
  const messagesIn = new Map<string, number>();
  const messagesOut = new Map<string, number>();
  const toolCalls = new Map<string, number>();
  const errors = new Map<string, number>();
  const latencies = new Map<string, number[]>();
  const tokens = new Map<string, number>();
  const costs = new Map<string, number>();
  const edges = new Map<string, EdgeAccumulator & { source: string; target: string }>();

  const bump = (map: Map<string, number>, key: string, delta = 1) =>
    map.set(key, (map.get(key) ?? 0) + delta);

  for (const event of events) {
    const etype = event.event_type;
    const payload = event.payload ?? {};
    const src = event.source_agent_id;
    const tgt = event.target_agent_id;
    // Lab control-plane events: lab-controller is an operator, not a
    // workflow participant (mirrors the backend fold).
    if (etype !== "fault.injected" && etype !== "attack.injected") {
      if (src) participants.add(src);
      if (tgt) participants.add(tgt);
    }

    if (src) {
      if (etype === "agent.started") {
        status.set(src, "running");
        if (typeof payload.name === "string" && payload.name) names.set(src, payload.name);
        if (typeof payload.role === "string" && payload.role) roles.set(src, payload.role);
      } else if (etype === "agent.completed") {
        status.set(src, "idle");
      } else if (etype === "agent.failed") {
        status.set(src, "failed");
      } else if (etype === "agent.quarantined") {
        status.set(src, "quarantined");
      } else if (etype === "agent.joined") {
        status.set(src, typeof payload.status === "string" && payload.status ? payload.status : "running");
        if (typeof payload.name === "string" && payload.name) names.set(src, payload.name);
        if (typeof payload.role === "string" && payload.role) roles.set(src, payload.role);
      } else if (etype === "agent.suspicious") {
        if (status.get(src) !== "quarantined") status.set(src, "suspicious");
        if (typeof payload.name === "string" && payload.name) names.set(src, payload.name);
        if (typeof payload.role === "string" && payload.role) roles.set(src, payload.role);
      } else if (etype === "agent.heartbeat" && typeof payload.status === "string" && payload.status) {
        status.set(src, payload.status);
      }

      if (
        etype === "agent.failed" ||
        etype === "message.failed" ||
        etype === "tool.failed" ||
        etype === "model.failed"
      ) {
        bump(errors, src);
      }
      if (etype === "agent.completed" || etype === "agent.failed") {
        const latency = asNumber(payload.latency_ms);
        if (latency !== null) {
          if (!latencies.has(src)) latencies.set(src, []);
          latencies.get(src)!.push(latency);
        }
      }
      if (etype === "tool.called") bump(toolCalls, src);
      if (etype === "model.completed") {
        const total = asNumber(payload.total_tokens);
        if (total !== null) bump(tokens, src, Math.trunc(total));
        const cost = asNumber(payload.cost_estimate);
        if (cost !== null) bump(costs, src, cost);
      }
    }

    if (
      etype === "message.sent" ||
      etype === "message.received" ||
      etype === "message.failed" ||
      etype === "message.flagged"
    ) {
      const source = src ?? "external";
      const target = tgt ?? "external";
      participants.add(source);
      participants.add(target);
      const key = `${source}->${target}`;
      const ensure = () =>
        edges.get(key) ??
        ({ source, target, count: 0, latencies: [], lastStatus: null, lastAt: null } as EdgeAccumulator & {
          source: string;
          target: string;
        });
      if (etype === "message.sent") {
        bump(messagesOut, source);
        bump(messagesIn, target);
        const entry = ensure();
        entry.count += 1;
        entry.lastStatus = "sent";
        entry.lastAt = event.timestamp;
        edges.set(key, entry);
      } else {
        const entry = ensure();
        entry.lastStatus =
          etype === "message.received"
            ? "delivered"
            : etype === "message.flagged"
              ? "flagged"
              : "failed";
        entry.lastAt = event.timestamp;
        if (etype === "message.received") {
          const latency = asNumber(payload.latency_ms);
          if (latency !== null) entry.latencies.push(latency);
        }
        edges.set(key, entry);
      }
    }
  }

  const nodes: GraphNode[] = [...participants].sort().map((agentId) => {
    const taskLatencies = latencies.get(agentId) ?? [];
    return {
      id: agentId,
      name: names.get(agentId) ?? agentId,
      role: roles.get(agentId) ?? null,
      status: status.get(agentId) ?? "unknown",
      trust_score: scores.get(agentId)?.trust ?? 1.0,
      risk_score: scores.get(agentId)?.risk ?? 0.0,
      messages_in: messagesIn.get(agentId) ?? 0,
      messages_out: messagesOut.get(agentId) ?? 0,
      tool_calls: toolCalls.get(agentId) ?? 0,
      errors: errors.get(agentId) ?? 0,
      avg_latency_ms:
        taskLatencies.length > 0
          ? round2(taskLatencies.reduce((a, b) => a + b, 0) / taskLatencies.length)
          : null,
      tokens: tokens.get(agentId) ?? 0,
      cost_estimate: round6(costs.get(agentId) ?? 0),
    };
  });

  const edgeModels: GraphEdge[] = [...edges.entries()]
    .map(([id, entry]) => ({
      id,
      source: entry.source,
      target: entry.target,
      message_count: entry.count,
      avg_latency_ms:
        entry.latencies.length > 0
          ? round2(entry.latencies.reduce((a, b) => a + b, 0) / entry.latencies.length)
          : null,
      last_status: entry.lastStatus,
      last_message_at: entry.lastAt,
    }))
    .sort((a, b) => a.id.localeCompare(b.id));

  return { run_id: runId, project_id: projectId, nodes, edges: edgeModels };
}

/** Next marker strictly after the cursor, or null. */
export function nextMarker(markers: number[], cursor: number): number | null {
  for (const index of markers) {
    if (index > cursor) return index;
  }
  return null;
}
