import { useState } from "react";

import { api } from "../../lib/api";
import type { TeamBuildResult } from "../../lib/types";
import { Card, ErrorNote, SectionLabel } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

const FILE_STATUS_STYLE: Record<string, string> = {
  written: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  halted_for_approval: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  blocked: "border-red-400/40 bg-red-400/10 text-red-300",
};

export function TeamBuildPanel({
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
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TeamBuildResult | null>(null);

  const disabled = chatMode || readOnly;

  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const out = await api.teamBuild(workspaceId, { goal: prompt.trim() || undefined });
      setResult(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Build with the team</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          live · governed · multi-agent
        </span>
      </div>

      <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
        One click: the orchestrator plans the goal and assigns each part to the right
        agent, then every agent builds its part through the enforcement gateway, sharing
        one sandbox. Builders write files; the planner, researcher and reviewers add their
        input. Stops cleanly if a step needs your approval.
      </p>

      {!readOnly ? (
        <div className="mt-3 space-y-2 rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
          <label className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
              Goal (optional — defaults to the workspace goal)
            </span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={2}
              placeholder={goal ?? "What the team should build…"}
              disabled={disabled}
              className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12px] text-zinc-200 disabled:opacity-60"
            />
          </label>
          <button
            type="button"
            disabled={disabled || busy}
            title={chatMode ? CHAT_HINT : undefined}
            onClick={run}
            className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
          >
            {busy ? "Team is building…" : "Build with the team"}
          </button>
        </div>
      ) : null}

      {busy ? (
        <p className="mt-3 text-[12px] text-zinc-500">
          Planning the work and running each agent through the governed pipeline…
        </p>
      ) : null}
      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}

      {result ? (
        <div data-testid="team-result" className="mt-3 rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
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
            <span className="text-zinc-500">
              {result.step_count} agents · {result.total_written} written ·{" "}
              {result.total_held} held · {result.total_blocked} blocked
            </span>
            {result.stop_reason === "halted_for_approval" ? (
              <span className="rounded border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[10px] text-amber-300">
                paused for approval
              </span>
            ) : null}
          </div>

          <div className="mt-2 space-y-1.5">
            {result.steps.map((s) => (
              <div
                key={s.task_id}
                data-testid="team-step"
                className="rounded-md bg-surface-2 px-2.5 py-1.5 text-[11.5px]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-400">
                    {s.kind === "build" ? "builds" : "contributes"}
                  </span>
                  <span className="font-medium text-zinc-200">{s.agent_name}</span>
                  <span className="font-mono text-[10.5px] text-zinc-600">{s.role}</span>
                  <span className="text-zinc-600">· {s.task_title}</span>
                </div>
                {s.summary || s.note ? (
                  <p className="mt-1 text-[11px] text-zinc-500">{s.summary ?? s.note}</p>
                ) : null}
                {s.files.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {s.files.map((f) => (
                      <span
                        key={f.path}
                        className={`rounded border px-1.5 py-0.5 text-[10px] ${FILE_STATUS_STYLE[f.status]}`}
                      >
                        {f.status.replace(/_/g, " ")} · {f.path}
                      </span>
                    ))}
                  </div>
                ) : null}
                {s.validations.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {s.validations.map((v, i) => (
                      <span
                        key={`${v.validator}-${i}`}
                        className={`rounded px-1.5 py-0.5 text-[10px] ${
                          v.passed ? "bg-emerald-400/10 text-emerald-300" : "bg-red-400/10 text-red-300"
                        }`}
                      >
                        {v.validator} {v.passed ? "pass" : "FAIL"}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {result.total_written > 0 ? (
            <p className="mt-2 text-[11px] text-indigo-300/90">
              {result.total_written} file(s) written by the team — see the Files and Website
              preview panels below.
            </p>
          ) : null}
          {result.total_held > 0 ? (
            <p className="mt-1 text-[11px] text-amber-300/90">
              {result.total_held} change(s) need approval — resolve them in the Approvals panel.
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
