import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { AgentRunResult } from "../../lib/types";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

const FILE_STATUS_STYLE: Record<string, string> = {
  written: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  approved: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  halted_for_approval: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  blocked: "border-red-400/40 bg-red-400/10 text-red-300",
  denied: "border-red-400/40 bg-red-400/10 text-red-300",
  completed: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  failed: "border-red-400/40 bg-red-400/10 text-red-300",
  timed_out: "border-red-400/40 bg-red-400/10 text-red-300",
};

const STOP_REASON_LABEL: Record<string, string> = {
  done: "the agent reported the goal complete",
  halted_for_approval: "an action needs your approval — the loop paused here",
  no_actions: "the agent proposed no further actions",
  max_steps: "the step limit was reached",
  model_failed: "the model call failed",
  malformed: "the model did not return a valid step",
};

export function AgentRunPanel({
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
  const [maxSteps, setMaxSteps] = useState(6);
  const [busy, setBusy] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentRunResult | null>(null);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;
  const selectedAgent = agentId || agents[0]?.agent_id || "";

  const run = async () => {
    if (!selectedAgent) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const out = await api.agentRun(workspaceId, {
        agent_id: selectedAgent,
        prompt: prompt.trim() || undefined,
        max_steps: maxSteps,
      });
      setResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const resume = async () => {
    if (!result?.run_id) return;
    setResuming(true);
    setError(null);
    try {
      const out = await api.agentRunResume(workspaceId, result.run_id);
      setResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResuming(false);
    }
  };

  if (agentsState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Agent run</SectionLabel>
        <Spinner label="Loading agents…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Agent run</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          live · governed · bounded loop
        </span>
      </div>

      <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
        The agent builds over several steps. Each step proposes files and safe commands —
        all routed through the enforcement gateway — then validators check the result and
        feed the next step. The loop stops when the agent is done, the step limit is hit,
        or an action needs your approval.
      </p>

      {agents.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="run-no-agents">
          No assignable agents — add an agent (with a provider/model) to this workspace
          first, then it can run here.
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
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Max steps
              </span>
              <select
                value={maxSteps}
                onChange={(e) => setMaxSteps(Number(e.target.value))}
                disabled={disabled}
                className="rounded-lg border border-edge bg-surface-2 px-2 py-1.5 text-[12px] text-zinc-200 disabled:opacity-60"
              >
                {[2, 3, 4, 5, 6, 7, 8].map((n) => (
                  <option key={n} value={n}>
                    {n}
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
              {busy ? "Running…" : "Run agent loop"}
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
          Running the bounded loop — each step calls the model and routes its actions
          through enforcement…
        </p>
      ) : null}
      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}

      {result ? (
        <div data-testid="run-result" className="mt-3 rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
            <span
              className={`rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${
                result.status === "completed"
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                  : result.status === "awaiting_approval"
                    ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
                    : "border-red-400/40 bg-red-400/10 text-red-300"
              }`}
            >
              {result.status.replace(/_/g, " ")}
            </span>
            <span className="font-mono text-zinc-400">
              {result.provider}/{result.model}
            </span>
            <span className="text-zinc-500">
              {result.step_count} step{result.step_count === 1 ? "" : "s"} ·{" "}
              {result.total_written} written · {result.total_held} held ·{" "}
              {result.total_blocked} blocked · {result.commands_run} command
              {result.commands_run === 1 ? "" : "s"}
            </span>
          </div>
          <p className="mt-1.5 text-[11.5px] text-zinc-400" data-testid="run-stop-reason">
            Stopped: {STOP_REASON_LABEL[result.stop_reason] ?? result.stop_reason}.
          </p>

          {result.status === "awaiting_approval" ? (
            <div
              data-testid="run-awaiting"
              className="mt-2 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2"
            >
              <p className="text-[11.5px] text-amber-200">
                The loop paused with {result.pending_approval_ids.length} action
                {result.pending_approval_ids.length === 1 ? "" : "s"} waiting for approval.
                Resolve {result.pending_approval_ids.length === 1 ? "it" : "them"} in the
                Approvals panel, then resume — the loop continues from the next step.
              </p>
              <button
                type="button"
                disabled={disabled || resuming}
                title={hintTitle}
                onClick={resume}
                data-testid="run-resume"
                className="mt-2 rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-[12px] font-medium text-amber-100 transition-colors hover:bg-amber-500/25 disabled:opacity-40"
              >
                {resuming ? "Resuming…" : "Resume agent loop"}
              </button>
            </div>
          ) : null}

          <div className="mt-2 space-y-2">
            {result.steps.map((s) => (
              <div
                key={s.step}
                data-testid="run-step"
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-2"
              >
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="rounded border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-400">
                    step {s.step + 1}
                  </span>
                  {s.done ? (
                    <span className="rounded border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] text-emerald-300">
                      done
                    </span>
                  ) : null}
                  <span className="text-zinc-400">{s.summary}</span>
                </div>
                {s.files.length > 0 ? (
                  <div className="mt-1.5 space-y-1">
                    {s.files.map((f) => (
                      <div
                        key={f.path}
                        data-testid="run-file"
                        className="flex flex-wrap items-center gap-2 text-[11px]"
                      >
                        <span className={`rounded border px-1.5 py-0.5 text-[10px] ${FILE_STATUS_STYLE[f.status]}`}>
                          {f.status.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono text-zinc-300">{f.path}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {s.commands.length > 0 ? (
                  <div className="mt-1.5 space-y-1">
                    {s.commands.map((c, idx) => (
                      <div
                        key={idx}
                        data-testid="run-command"
                        className="flex flex-wrap items-center gap-2 text-[11px]"
                      >
                        <span className={`rounded border px-1.5 py-0.5 text-[10px] ${FILE_STATUS_STYLE[c.status]}`}>
                          {c.status.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono text-zinc-300">{c.command}</span>
                        {c.exit_code != null ? (
                          <span className="text-zinc-600">exit {c.exit_code}</span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                {s.validations.length > 0 ? (
                  <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="run-validations">
                    {s.validations.map((v, idx) => (
                      <span
                        key={idx}
                        className={`rounded border px-1.5 py-0.5 text-[10px] ${
                          v.passed
                            ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                            : "border-red-400/40 bg-red-400/10 text-red-300"
                        }`}
                      >
                        {v.validator} {v.passed ? "✓" : "✗"}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {result.total_written > 0 ? (
            <p className="mt-2 text-[11px] text-indigo-300/90">
              {result.total_written} file(s) written — see the Files and Website preview panels below.
            </p>
          ) : null}
          {result.total_held > 0 ? (
            <p className="mt-1 text-[11px] text-amber-300/90">
              {result.total_held} action(s) need approval — resolve them in the Approvals panel.
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
