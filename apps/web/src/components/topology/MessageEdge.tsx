import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { clsx } from "clsx";

import { fmtMs } from "../../lib/format";
import type { GraphEdge } from "../../lib/types";

export type MessageFlowEdge = Edge<
  { edge: GraphEdge; onSelect?: (edgeId: string) => void },
  "message"
>;

export function MessageEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  markerEnd,
}: EdgeProps<MessageFlowEdge>) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 16,
  });
  const edge = data?.edge;
  const failed = edge?.last_status === "failed";
  const flagged = edge?.last_status === "flagged";
  const stroke = selected ? "#818cf8" : failed ? "#f87171" : flagged ? "#fbbf24" : "#41414b";
  const width = selected
    ? 2.4
    : flagged
      ? 2.2
      : Math.min(1.3 + (edge?.message_count ?? 1) * 0.3, 3);

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={{ stroke, strokeWidth: width }} />
      {edge ? (
        <EdgeLabelRenderer>
          <button
            type="button"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "all",
            }}
            className={clsx(
              "absolute z-10 rounded-full border px-2 py-0.5 font-mono text-[10px] transition-colors",
              selected
                ? "border-indigo-400/60 bg-indigo-500/20 text-indigo-200"
                : failed
                  ? "border-red-400/40 bg-surface-2 text-red-300 hover:border-red-400/70"
                  : flagged
                    ? "border-amber-400/50 bg-surface-2 text-amber-300 hover:border-amber-400/80"
                    : "border-edge bg-surface-2 text-zinc-400 hover:border-edge-strong hover:text-zinc-200",
            )}
            onClick={(event) => {
              event.stopPropagation();
              data?.onSelect?.(id);
            }}
          >
            {flagged ? "⚠ " : ""}
            {edge.message_count} msg{edge.message_count === 1 ? "" : "s"}
            {edge.avg_latency_ms != null ? ` · ${fmtMs(edge.avg_latency_ms)}` : ""}
          </button>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
