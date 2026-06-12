import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { clsx } from "clsx";

import type { StudioAgent } from "../../lib/types";

export interface StudioNodeData {
  agent: StudioAgent;
  providerConfigured: boolean;
  [key: string]: unknown;
}

export type StudioFlowNode = Node<StudioNodeData, "studioAgent">;

export function StudioAgentNode({ data, selected }: NodeProps<StudioFlowNode>) {
  const { agent, providerConfigured } = data;
  return (
    <div
      className={clsx(
        "min-w-[190px] rounded-xl border bg-surface-1 px-3.5 py-3 shadow-lg transition-colors",
        selected ? "border-indigo-400/70" : "border-edge hover:border-edge-strong",
      )}
    >
      <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-edge !bg-zinc-500" />
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-semibold text-zinc-100">{agent.name}</span>
      </div>
      <div className="mt-0.5 text-[10.5px] font-medium uppercase tracking-wider text-zinc-500">
        {agent.role}
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        <span className="rounded-md border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
          {agent.provider}
        </span>
        <span className="truncate font-mono text-[10px] text-zinc-500">{agent.model_name}</span>
      </div>
      {!providerConfigured ? (
        <div className="mt-2 rounded-md border border-amber-400/25 bg-amber-400/5 px-1.5 py-1 text-[10px] leading-4 text-amber-200/90">
          provider not configured
        </div>
      ) : null}
      <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-edge !bg-indigo-400" />
    </div>
  );
}
