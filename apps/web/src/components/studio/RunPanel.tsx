import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../lib/api";
import type { StudioRunResult } from "../../lib/types";
import { Badge, ErrorNote, SectionLabel } from "../ui";

interface RunPanelProps {
  workflowId: string;
  defaultInput?: string;
  /** Unsaved canvas changes — the run executes the stored definition. */
  dirty: boolean;
  unconfiguredProviders: string[];
  onRunComplete: (result: StudioRunResult) => void;
}

export function RunPanel({
  workflowId,
  defaultInput,
  dirty,
  unconfiguredProviders,
  onRunComplete,
}: RunPanelProps) {
  const [input, setInput] = useState(
    defaultInput ??
      "Build a simple FastAPI endpoint that accepts a username and returns a greeting. Then review it for basic security issues.",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StudioRunResult | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const runResult = await api.runStudioWorkflow(workflowId, { input });
      setResult(runResult);
      onRunComplete(runResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <SectionLabel>Run workflow</SectionLabel>
      <label className="flex flex-col gap-1">
        <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Workflow input
        </span>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={3}
          className="rounded-lg border border-edge bg-surface-0 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
        />
      </label>
      {unconfiguredProviders.length > 0 ? (
        <div className="rounded-md border border-amber-400/25 bg-amber-400/5 px-2.5 py-2 text-[11.5px] leading-5 text-amber-200/90">
          Warning: provider{unconfiguredProviders.length > 1 ? "s" : ""}{" "}
          <span className="font-mono">{unconfiguredProviders.join(", ")}</span>{" "}
          {unconfiguredProviders.length > 1 ? "are" : "is"} not configured — those agents will fail
          cleanly with <span className="font-mono">model.failed</span>.
        </div>
      ) : null}
      {dirty ? (
        <div className="text-[11px] text-zinc-500">
          Unsaved changes — the run uses the last saved version of the workflow.
        </div>
      ) : null}
      <button
        type="button"
        onClick={run}
        disabled={busy || !input.trim()}
        className="rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-[12px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Running…" : "▶ Run Workflow"}
      </button>

      {error ? <ErrorNote message={error} /> : null}
      {result ? (
        <div className="rounded-lg border border-edge bg-surface-2 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <Badge
              className={
                result.status === "completed"
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                  : "border-red-400/40 bg-red-400/10 text-red-300"
              }
            >
              run {result.status}
            </Badge>
            <span className="font-mono text-[11px] text-zinc-400">{result.run_id}</span>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2 text-[11.5px]">
            <Link
              to={result.open_run_url}
              className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-2 py-1 font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25"
            >
              Open Run Detail
            </Link>
            <Link
              to={`${result.open_run_url}?tab=replay`}
              className="rounded-md border border-edge bg-surface-1 px-2 py-1 text-zinc-300 transition-colors hover:bg-surface-2"
            >
              View Replay
            </Link>
            <Link
              to={`${result.open_run_url}?tab=cost`}
              className="rounded-md border border-edge bg-surface-1 px-2 py-1 text-zinc-300 transition-colors hover:bg-surface-2"
            >
              View Cost &amp; Tokens
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
