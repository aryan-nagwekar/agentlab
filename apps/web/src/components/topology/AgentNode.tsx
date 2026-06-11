import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { clsx } from "clsx";

import { fmtMs } from "../../lib/format";
import { agentStatus } from "../../lib/status";
import { tierStyle } from "../../lib/scoring";
import type { GraphNode } from "../../lib/types";
import { Badge, StatusDot, TrustBar } from "../ui";

export type AgentFlowNode = Node<{ node: GraphNode }, "agent">;

const STATUS_RING: Record<string, string> = {
  running: "border-sky-400/50 shadow-[0_0_28px_-8px_rgba(56,189,248,0.55)]",
  failed: "border-red-400/50 shadow-[0_0_28px_-8px_rgba(248,113,113,0.6)]",
  quarantined: "border-purple-400/60 border-dashed shadow-[0_0_30px_-6px_rgba(192,132,252,0.7)]",
  overloaded: "border-orange-400/50 shadow-[0_0_28px_-8px_rgba(251,146,60,0.5)]",
  suspicious: "border-amber-400/60 shadow-[0_0_30px_-6px_rgba(251,191,36,0.65)]",
};

export function AgentNode({ data, selected }: NodeProps<AgentFlowNode>) {
  const node = data.node;
  const style = agentStatus(node.status);
  return (
    <div
      className={clsx(
        "w-[232px] rounded-xl border bg-surface-2/95 px-3.5 py-3 backdrop-blur transition-shadow",
        STATUS_RING[node.status] ?? "border-edge",
        selected && "ring-2 ring-indigo-400/80",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-zinc-600"
      />
      <div className="flex items-center gap-2">
        <StatusDot className={style.dot} pulse={node.status === "running"} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-zinc-100">{node.name}</div>
          <div className="font-mono text-[10px] text-zinc-500">{node.id}</div>
        </div>
        {node.status === "quarantined" ? (
          <span title="quarantined">🛑</span>
        ) : node.status === "suspicious" ? (
          <span title="suspicious">⚠️</span>
        ) : node.role ? (
          <Badge>{node.role}</Badge>
        ) : null}
      </div>
      <div className="mt-2.5 grid grid-cols-4 gap-1 text-center">
        <NodeStat label="in" value={node.messages_in} />
        <NodeStat label="out" value={node.messages_out} />
        <NodeStat label="tools" value={node.tool_calls} />
        <NodeStat label="errs" value={node.errors} danger={node.errors > 0} />
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-zinc-600">trust</span>
        <TrustBar value={node.trust_score} />
      </div>
      {node.risk_score > 0 ? (
        <div className="mt-1.5 flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-600">risk</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
            <div
              className="h-full rounded-full bg-rose-400"
              style={{ width: `${Math.round(node.risk_score * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[11px] text-rose-300">{node.risk_score.toFixed(2)}</span>
        </div>
      ) : null}
      {(() => {
        const t = tierStyle(node.trust_score, node.risk_score);
        return (
          <div className="mt-2 flex justify-center">
            <span className={`rounded-full border px-2 py-0.5 text-[9.5px] font-medium uppercase tracking-wider ${t.badge}`}>
              {t.label}
            </span>
          </div>
        );
      })()}
      {node.avg_latency_ms != null ? (
        <div className="mt-1.5 text-[10px] text-zinc-500">
          avg task {fmtMs(node.avg_latency_ms)}
          {node.tokens > 0 ? ` · ${node.tokens.toLocaleString()} tok` : ""}
        </div>
      ) : null}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-zinc-600"
      />
    </div>
  );
}

function NodeStat({
  label,
  value,
  danger,
}: {
  label: string;
  value: number;
  danger?: boolean;
}) {
  return (
    <div className="rounded-md bg-surface-3/70 px-1 py-1">
      <div className={clsx("font-mono text-[12px] font-semibold", danger ? "text-red-300" : "text-zinc-200")}>
        {value}
      </div>
      <div className="text-[9px] uppercase tracking-wider text-zinc-600">{label}</div>
    </div>
  );
}
