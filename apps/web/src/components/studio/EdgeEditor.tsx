import type { StudioEdge } from "../../lib/types";
import { SectionLabel } from "../ui";

interface EdgeEditorProps {
  edge: StudioEdge;
  onChange: (edge: StudioEdge) => void;
  onDelete: () => void;
}

export function EdgeEditor({ edge, onChange, onDelete }: EdgeEditorProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <SectionLabel>Edge — {edge.edge_id}</SectionLabel>
        <button
          type="button"
          onClick={onDelete}
          className="rounded-md border border-red-400/30 bg-red-400/10 px-2 py-1 text-[11px] text-red-300 transition-colors hover:bg-red-400/20"
        >
          Delete edge
        </button>
      </div>
      <div className="rounded-lg border border-edge bg-surface-2 px-3 py-2 font-mono text-[12px] text-zinc-300">
        {edge.source_agent_id} <span className="text-zinc-600">→</span> {edge.target_agent_id}
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Label
        </span>
        <input
          className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
          value={edge.label ?? ""}
          onChange={(e) => onChange({ ...edge, label: e.target.value || null })}
        />
      </label>
    </div>
  );
}
