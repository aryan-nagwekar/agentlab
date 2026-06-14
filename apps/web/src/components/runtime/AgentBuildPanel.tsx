import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { AgentBuildResult } from "../../lib/types";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

const FILE_STATUS_STYLE: Record<string, string> = {
  written: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  halted_for_approval: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  blocked: "border-red-400/40 bg-red-400/10 text-red-300",
};

export function AgentBuildPanel({
  workspaceId,
  goal,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  goal: string | null;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const agentsState = useFetch(() => api.workspaceAgents(workspaceId), [workspaceId]);
  const agents = (agentsState.data ?? []).filter(
    (a) => a.status !== "quarantined" && a.status !== "disabled",
  );

  const [agentId, setAgentId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentBuildResult | null>(null);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;
  const selectedAgent = agentId || agents[0]?.agent_id || "";

  const run = async () => {
    if (!selectedAgent) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const out = await api.agentBuild(workspaceId, {
        agent_id: selectedAgent,
        prompt: prompt.trim() || undefined,
      });
      setResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (agentsState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Agent build</SectionLabel>
        <Spinner label="Loading agents…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Agent build</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          live · governed · single pass
        </span>
      </div>

      <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
        The selected agent's model proposes files for this goal. Every file is routed
        through the enforcement gateway before it's written — safe files land in the
        sandbox, sensitive paths wait for your approval, unsafe paths are blocked.
      </p>

      {agents.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="build-no-agents">
          No assignable agents — add an agent (with a provider/model) to this workspace
          first, then it can build here.
        </p>
      ) : !readOnly ? (
        <div className="mt-3 space-y-2 rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Agent
              </span>
              <select
                value={selectedAgent}
                onChange={(e) => setAgentId(e.target.value)}
                disabled={disabled}
                className="rounded-lg border border-edge bg-surface-2 px-2 py-1.5 text-[12px] text-zinc-200 disabled:opacity-60"
              >
                {agents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.name} · {a.model_provider}/{a.model_name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={disabled || busy}
              title={hintTitle}
              onClick={run}
              className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {busy ? "Building…" : "Build with agent"}
            </button>
          </div>
          <label className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
              Prompt (optional — defaults to the workspace goal)
            </span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={2}
              placeholder={goal ?? "Build a small static site…"}
              disabled={disabled}
              className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12px] text-zinc-200 disabled:opacity-60"
            />
          </label>
        </div>
      ) : null}

      {busy ? (
        <p className="mt-3 text-[12px] text-zinc-500">
          Calling the model and routing each proposed file through enforcement…
        </p>
      ) : null}
      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}

      {result ? (
        <div data-testid="build-result" className="mt-3 rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
            <span
              className={`rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${
                result.status === "completed"
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                  : "border-red-400/40 bg-red-400/10 text-red-300"
              }`}
            >
              {result.status}
            </span>
            <span className="font-mono text-zinc-400">
              {result.provider}/{result.model}
            </span>
            <span className="text-zinc-500">
              {result.written} written · {result.halted_for_approval} held · {result.blocked} blocked
            </span>
            {result.output_tokens != null ? (
              <span className="ml-auto text-[10.5px] text-zinc-600">
                {result.input_tokens}/{result.output_tokens} tok · {result.latency_ms} ms
              </span>
            ) : null}
          </div>
          {result.summary ? (
            <p className="mt-1.5 text-[11.5px] text-zinc-400">{result.summary}</p>
          ) : null}
          {result.files.length > 0 ? (
            <div className="mt-2 space-y-1">
              {result.files.map((f) => (
                <div
                  key={f.path}
                  data-testid="build-file"
                  className="flex flex-wrap items-center gap-2 rounded-md bg-surface-2 px-2 py-1 text-[11px]"
                >
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] ${FILE_STATUS_STYLE[f.status]}`}
                  >
                    {f.status.replace(/_/g, " ")}
                  </span>
                  <span className="font-mono text-zinc-300">{f.path}</span>
                  {f.reason ? <span className="text-zinc-600">— {f.reason}</span> : null}
                </div>
              ))}
            </div>
          ) : null}
          {result.written > 0 ? (
            <p className="mt-2 text-[11px] text-indigo-300/90">
              {result.written} file(s) written — see the Files and Website preview panels below.
            </p>
          ) : null}
          {result.halted_for_approval > 0 ? (
            <p className="mt-1 text-[11px] text-amber-300/90">
              {result.halted_for_approval} file(s) need approval — resolve them in the Approvals panel.
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
