import type { AgentLabEvent } from "./types";

export interface StatusStyle {
  label: string;
  dot: string; // class for a small status dot
  badge: string; // class for a pill badge
}

export const RUN_STATUS: Record<string, StatusStyle> = {
  running: {
    label: "Running",
    dot: "bg-sky-400",
    badge: "bg-sky-400/10 text-sky-300 border-sky-400/30",
  },
  completed: {
    label: "Completed",
    dot: "bg-emerald-400",
    badge: "bg-emerald-400/10 text-emerald-300 border-emerald-400/30",
  },
  failed: {
    label: "Failed",
    dot: "bg-red-400",
    badge: "bg-red-400/10 text-red-300 border-red-400/30",
  },
};

export const AGENT_STATUS: Record<string, StatusStyle> = {
  healthy: {
    label: "Healthy",
    dot: "bg-emerald-400",
    badge: "bg-emerald-400/10 text-emerald-300 border-emerald-400/30",
  },
  running: {
    label: "Running",
    dot: "bg-sky-400",
    badge: "bg-sky-400/10 text-sky-300 border-sky-400/30",
  },
  idle: {
    label: "Idle",
    dot: "bg-zinc-400",
    badge: "bg-zinc-400/10 text-zinc-300 border-zinc-400/30",
  },
  failed: {
    label: "Failed",
    dot: "bg-red-400",
    badge: "bg-red-400/10 text-red-300 border-red-400/30",
  },
  overloaded: {
    label: "Overloaded",
    dot: "bg-orange-400",
    badge: "bg-orange-400/10 text-orange-300 border-orange-400/30",
  },
  quarantined: {
    label: "Quarantined",
    dot: "bg-purple-400",
    badge: "bg-purple-400/10 text-purple-300 border-purple-400/30",
  },
  unknown: {
    label: "Unknown",
    dot: "bg-zinc-600",
    badge: "bg-zinc-600/10 text-zinc-400 border-zinc-600/30",
  },
};

export function runStatus(status: string): StatusStyle {
  return RUN_STATUS[status] ?? AGENT_STATUS.unknown;
}

export function agentStatus(status: string): StatusStyle {
  return AGENT_STATUS[status] ?? AGENT_STATUS.unknown;
}

export type EventFamily =
  | "run"
  | "agent"
  | "message"
  | "tool"
  | "model"
  | "routing"
  | "trust"
  | "lab";

export function eventFamily(eventType: string): EventFamily {
  const prefix = eventType.split(".")[0];
  switch (prefix) {
    case "run":
    case "agent":
    case "message":
    case "tool":
    case "model":
      return prefix;
    case "routing":
      return "routing";
    case "trust":
    case "risk":
      return "trust";
    default:
      return "lab"; // fault.* / attack.* — Lab Mode events (v0.3)
  }
}

export const FAMILY_STYLES: Record<EventFamily, { label: string; badge: string; dot: string }> = {
  run: { label: "Run", badge: "bg-indigo-400/10 text-indigo-300 border-indigo-400/30", dot: "bg-indigo-400" },
  agent: { label: "Agent", badge: "bg-sky-400/10 text-sky-300 border-sky-400/30", dot: "bg-sky-400" },
  message: { label: "Message", badge: "bg-emerald-400/10 text-emerald-300 border-emerald-400/30", dot: "bg-emerald-400" },
  tool: { label: "Tool", badge: "bg-amber-400/10 text-amber-300 border-amber-400/30", dot: "bg-amber-400" },
  model: { label: "Model", badge: "bg-violet-400/10 text-violet-300 border-violet-400/30", dot: "bg-violet-400" },
  routing: { label: "Routing", badge: "bg-cyan-400/10 text-cyan-300 border-cyan-400/30", dot: "bg-cyan-400" },
  trust: { label: "Trust", badge: "bg-fuchsia-400/10 text-fuchsia-300 border-fuchsia-400/30", dot: "bg-fuchsia-400" },
  lab: { label: "Lab", badge: "bg-rose-400/10 text-rose-300 border-rose-400/30", dot: "bg-rose-400" },
};

export function isFailureEvent(eventType: string): boolean {
  return eventType.endsWith(".failed");
}

/** One-line human summary used in timelines and inspector headers. */
export function eventSummary(event: AgentLabEvent): string {
  const p = event.payload as Record<string, any>;
  switch (event.event_type) {
    case "run.started":
      return `Run started${p.name ? ` — ${p.name}` : ""}`;
    case "run.completed":
      return "Run completed";
    case "run.failed":
      return `Run failed${p.error ? ` — ${p.error}` : ""}`;
    case "agent.started":
      return `${p.name ?? event.source_agent_id} started${p.role ? ` (${p.role})` : ""}`;
    case "agent.completed":
      return `${p.name ?? event.source_agent_id} finished`;
    case "agent.failed":
      return `${p.name ?? event.source_agent_id} failed — ${p.error ?? "unknown error"}`;
    case "agent.heartbeat":
      return `heartbeat (${p.status ?? "ok"})`;
    case "message.sent": {
      const content = p.content as Record<string, unknown> | string | undefined;
      const task =
        typeof content === "object" && content !== null
          ? ((content as Record<string, unknown>).task ?? (content as Record<string, unknown>).instruction)
          : content;
      return `message${task ? ` — ${String(task)}` : ""}`;
    }
    case "message.received":
      return "message delivered";
    case "message.failed":
      return `message failed — ${p.error ?? ""}`;
    case "tool.called":
      return `${p.tool_name ?? "tool"} called`;
    case "tool.completed":
      return `${p.tool_name ?? "tool"} completed`;
    case "tool.failed":
      return `${p.tool_name ?? "tool"} failed — ${p.error ?? ""}`;
    case "model.called":
      return `${p.model ?? "model"} invoked`;
    case "model.completed":
      return `${p.model ?? "model"} — ${p.total_tokens ?? 0} tokens`;
    case "model.failed":
      return `${p.model ?? "model"} failed — ${p.error ?? ""}`;
    case "routing.decision":
      return `routed to ${p.selected_agent_id ?? event.target_agent_id} — ${p.reason ?? ""}`;
    case "trust.updated":
      return `trust → ${p.trust_score}${p.reason ? ` (${p.reason})` : ""}`;
    case "risk.updated":
      return `risk → ${p.risk_score}${p.reason ? ` (${p.reason})` : ""}`;
    case "fault.injected":
      return `fault injected — ${p.fault_type ?? ""}`;
    case "attack.injected":
      return `attack simulated — ${p.attack_type ?? ""}`;
    case "agent.quarantined":
      return `agent quarantined${p.reason ? ` — ${p.reason}` : ""}`;
    default:
      return event.event_type;
  }
}
