import { Link } from "react-router-dom";

import { fmtCost, fmtMs } from "../../lib/format";
import { agentStatus, eventSummary } from "../../lib/status";
import type { AgentLabEvent, GraphEdge, GraphNode } from "../../lib/types";
import { Badge, Card, SectionLabel, StatusDot, TrustBar } from "../ui";
import { ScorePanel } from "../scoring/ScorePanel";
import { EventDetail } from "./EventDetail";

export type Selection =
  | { kind: "event"; event: AgentLabEvent }
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string }
  | null;

interface InspectorPanelProps {
  selection: Selection;
  events: AgentLabEvent[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  projectId: string | undefined;
  /** When set, the agent inspector fetches the full run-scoped score explanation. */
  runId?: string;
  onSelect: (selection: Selection) => void;
  onClose: () => void;
}

export function InspectorPanel({
  selection,
  events,
  nodes,
  edges,
  projectId,
  runId,
  onSelect,
  onClose,
}: InspectorPanelProps) {
  if (!selection) {
    return (
      <Card className="flex h-full items-center justify-center p-6 text-center text-sm text-zinc-600">
        Select an agent node, a message edge, or a timeline event to inspect it.
      </Card>
    );
  }

  let title = "Inspector";
  let body: React.ReactNode = null;

  if (selection.kind === "event") {
    title = "Event";
    body = (
      <EventDetail
        event={selection.event}
        allEvents={events}
        onSelectEvent={(event) => onSelect({ kind: "event", event })}
      />
    );
  } else if (selection.kind === "node") {
    const node = nodes.find((n) => n.id === selection.id);
    title = "Agent";
    body = node ? (
      <NodeInspector
        node={node}
        events={events}
        projectId={projectId}
        runId={runId}
        onSelectEvent={(event) => onSelect({ kind: "event", event })}
      />
    ) : (
      <Missing label="agent" />
    );
  } else {
    const edge = edges.find((e) => e.id === selection.id);
    title = "Channel";
    body = edge ? (
      <EdgeInspector
        edge={edge}
        events={events}
        onSelectEvent={(event) => onSelect({ kind: "event", event })}
      />
    ) : (
      <Missing label="channel" />
    );
  }

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-edge px-4 py-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
          {title}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-1.5 text-zinc-500 transition-colors hover:bg-surface-2 hover:text-zinc-200"
          aria-label="Close inspector"
        >
          ✕
        </button>
      </div>
      <div className="min-h-0 flex-1">{body}</div>
    </Card>
  );
}

function Missing({ label }: { label: string }) {
  return <div className="p-6 text-sm text-zinc-600">This {label} is no longer in the graph.</div>;
}

function NodeInspector({
  node,
  events,
  projectId,
  runId,
  onSelectEvent,
}: {
  node: GraphNode;
  events: AgentLabEvent[];
  projectId: string | undefined;
  runId?: string;
  onSelectEvent: (event: AgentLabEvent) => void;
}) {
  const style = agentStatus(node.status);
  const related = events
    .filter((e) => e.source_agent_id === node.id || e.target_agent_id === node.id)
    .slice(-10)
    .reverse();

  return (
    <div className="flex h-full flex-col overflow-y-auto px-4 py-4">
      <div className="flex items-center gap-2.5">
        <StatusDot className={style.dot} pulse={node.status === "running"} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[15px] font-semibold text-zinc-100">{node.name}</div>
          <div className="font-mono text-[11px] text-zinc-500">{node.id}</div>
        </div>
        <Badge className={style.badge}>{style.label}</Badge>
      </div>
      {node.role ? <div className="mt-1.5 text-[12px] text-zinc-500">role: {node.role}</div> : null}

      <div className="mt-4">
        {runId ? (
          // Full run-scoped score: tier, latest reason, factors, history.
          <ScorePanel agentId={node.id} projectId={projectId} runId={runId} />
        ) : (
          // Replay: show the cursor-scoped score carried on the node.
          <div className="space-y-2.5">
            <div>
              <SectionLabel>Trust score</SectionLabel>
              <TrustBar value={node.trust_score} />
            </div>
            <div>
              <SectionLabel>Risk score</SectionLabel>
              <div className="flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-rose-400"
                    style={{ width: `${Math.round(node.risk_score * 100)}%` }}
                  />
                </div>
                <span className="font-mono text-[11px] text-zinc-400">{node.risk_score.toFixed(2)}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <MiniStat label="msgs in" value={String(node.messages_in)} />
        <MiniStat label="msgs out" value={String(node.messages_out)} />
        <MiniStat label="tools" value={String(node.tool_calls)} />
        <MiniStat label="errors" value={String(node.errors)} danger={node.errors > 0} />
        <MiniStat label="avg task" value={fmtMs(node.avg_latency_ms)} />
        <MiniStat label="cost" value={fmtCost(node.cost_estimate)} />
      </div>

      <div className="mt-4">
        <SectionLabel>Recent activity</SectionLabel>
        <div className="space-y-1">
          {related.map((event) => (
            <button
              key={event.event_id}
              type="button"
              onClick={() => onSelectEvent(event)}
              className="flex w-full items-center gap-2 rounded-md border border-edge bg-surface-2 px-2 py-1.5 text-left transition-colors hover:border-edge-strong"
            >
              <span className="shrink-0 font-mono text-[10px] text-zinc-500">
                {event.event_type}
              </span>
              <span className="truncate text-[11px] text-zinc-400">{eventSummary(event)}</span>
            </button>
          ))}
        </div>
      </div>

      <Link
        to={`/agents/${node.id}${projectId ? `?project=${projectId}` : ""}`}
        className="mt-4 inline-block text-[12px] font-medium text-indigo-300 hover:text-indigo-200"
      >
        Open agent page →
      </Link>
    </div>
  );
}

function EdgeInspector({
  edge,
  events,
  onSelectEvent,
}: {
  edge: GraphEdge;
  events: AgentLabEvent[];
  onSelectEvent: (event: AgentLabEvent) => void;
}) {
  const messages = events.filter(
    (e) =>
      e.event_type === "message.sent" &&
      e.source_agent_id === edge.source &&
      e.target_agent_id === edge.target,
  );

  return (
    <div className="flex h-full flex-col overflow-y-auto px-4 py-4">
      <div className="font-mono text-[13px] text-zinc-200">
        {edge.source} <span className="text-zinc-600">→</span> {edge.target}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <MiniStat label="messages" value={String(edge.message_count)} />
        <MiniStat label="avg latency" value={fmtMs(edge.avg_latency_ms)} />
        <MiniStat
          label="last status"
          value={edge.last_status ?? "—"}
          danger={edge.last_status === "failed"}
        />
      </div>

      <div className="mt-4">
        <SectionLabel>Messages on this channel</SectionLabel>
        <div className="space-y-1">
          {messages.length === 0 ? (
            <div className="text-[12px] text-zinc-600">No message payloads captured.</div>
          ) : (
            messages.map((event) => (
              <button
                key={event.event_id}
                type="button"
                onClick={() => onSelectEvent(event)}
                className="w-full rounded-md border border-edge bg-surface-2 px-2.5 py-2 text-left transition-colors hover:border-edge-strong"
              >
                <div className="truncate text-[12px] text-zinc-300">{eventSummary(event)}</div>
                <div className="mt-0.5 font-mono text-[10px] text-zinc-600">
                  {String(event.metadata.message_id ?? event.event_id)}
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-md border border-edge bg-surface-2 px-2 py-1.5">
      <div className={`truncate font-mono text-[12px] ${danger ? "text-red-300" : "text-zinc-200"}`}>
        {value}
      </div>
      <div className="text-[9.5px] uppercase tracking-wider text-zinc-600">{label}</div>
    </div>
  );
}
