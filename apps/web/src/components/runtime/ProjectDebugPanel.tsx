import { useState } from "react";
import { Link } from "react-router-dom";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { DebugHealth, DebugMap, DebugSummary } from "../../lib/types";
import { Card, SectionLabel, Spinner } from "../ui";

const HEALTH_STYLE: Record<string, string> = {
  high: "border-red-400/40 bg-red-400/10 text-red-200",
  medium: "border-amber-400/30 bg-amber-400/10 text-amber-200",
  ok: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
  none: "border-edge bg-surface-2 text-zinc-400",
};

const HEALTH_DOT: Record<string, string> = {
  high: "bg-red-400",
  medium: "bg-amber-400",
  ok: "bg-emerald-400",
  none: "bg-zinc-500",
};

const NODE_STYLE: Record<string, string> = {
  goal: "border-indigo-400/40 bg-indigo-500/10 text-indigo-200",
  workflow: "border-sky-400/30 bg-sky-400/10 text-sky-200",
  task: "border-edge bg-surface-2 text-zinc-300",
  agent: "border-violet-400/30 bg-violet-400/10 text-violet-200",
  artifact: "border-edge bg-surface-0 text-zinc-400",
  validation: "border-amber-400/30 bg-amber-400/10 text-amber-200",
};

function HealthBanner({ health }: { health: DebugHealth }) {
  return (
    <div
      data-testid="project-health"
      className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2.5 ${HEALTH_STYLE[health.severity] ?? HEALTH_STYLE.none}`}
    >
      <span className={`h-2 w-2 rounded-full ${HEALTH_DOT[health.severity] ?? HEALTH_DOT.none}`} />
      <span className="text-[13px] font-semibold">{health.label}</span>
      {health.active_labels.length > 1 ? (
        <span className="flex flex-wrap gap-1">
          {health.active_labels.slice(1).map((l) => (
            <span
              key={l}
              className="rounded border border-current/20 px-1.5 py-0.5 text-[10px] opacity-80"
            >
              {l}
            </span>
          ))}
        </span>
      ) : null}
    </div>
  );
}

export function ProjectDebugPanel({
  workspaceId,
  activityRunId,
}: {
  workspaceId: string;
  activityRunId: string;
}) {
  const summaryState = useFetch(() => api.debugSummary(workspaceId), [workspaceId]);
  const issuesState = useFetch(() => api.debugIssues(workspaceId), [workspaceId]);
  const [advanced, setAdvanced] = useState(false);
  const mapState = useFetch(
    () => (advanced ? api.debugProjectMap(workspaceId) : Promise.resolve(null)),
    [workspaceId, advanced],
  );

  if (summaryState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Project debugging</SectionLabel>
        <Spinner label="Reading project health…" />
      </Card>
    );
  }
  const summary = summaryState.data;
  if (!summary) return null;
  const issues = issuesState.data ?? [];

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Project debugging</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          read-only · grounded in real events
        </span>
      </div>

      {/* 1 — Health */}
      <div className="mt-3">
        <HealthBanner health={summary.health} />
      </div>

      {/* 2 — Recommended next action */}
      <div className="mt-3" data-testid="recommended-actions">
        <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Recommended next
        </div>
        <ul className="space-y-1">
          {summary.recommended_actions.map((a) => (
            <li
              key={a.action}
              className="flex items-center gap-2 rounded-md border border-edge bg-surface-0 px-2.5 py-1.5 text-[12px] text-zinc-300"
            >
              <span className="text-indigo-300">→</span>
              {a.label}
              {a.link ? (
                <span className="ml-auto font-mono text-[10px] text-zinc-600">{a.link}</span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      {/* 4 — What is broken / needs attention */}
      {issues.length > 0 ? (
        <div className="mt-3" data-testid="issues">
          <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
            Needs attention
          </div>
          <div className="space-y-1.5">
            {issues.slice(0, 6).map((issue) => (
              <div
                key={`${issue.kind}:${issue.ref}`}
                data-testid="issue-item"
                className={`rounded-md border px-2.5 py-1.5 ${
                  issue.severity === "high"
                    ? "border-red-400/30 bg-red-400/[0.04]"
                    : "border-amber-400/20 bg-amber-400/[0.03]"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span
                    className={`rounded px-1 py-0.5 text-[9.5px] font-medium ${
                      issue.severity === "high"
                        ? "bg-red-400/15 text-red-300"
                        : "bg-amber-400/15 text-amber-300"
                    }`}
                  >
                    {issue.severity}
                  </span>
                  <span className="font-medium text-zinc-200">{issue.title}</span>
                  <span className="ml-auto font-mono text-[10px] text-zinc-600">{issue.link}</span>
                </div>
                {issue.detail ? (
                  <p className="mt-0.5 text-[11px] text-zinc-500">{issue.detail}</p>
                ) : null}
                {issue.suggested_action ? (
                  <p className="mt-0.5 text-[11px] text-amber-200/70">
                    Suggested: {issue.suggested_action}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="no-issues">
          Nothing needs attention right now.
        </p>
      )}

      {/* 3 — What changed recently */}
      {summary.recent_changes.length > 0 ? (
        <div className="mt-3" data-testid="recent-changes">
          <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
            Recent changes
          </div>
          <div className="space-y-0.5">
            {summary.recent_changes.slice(0, 6).map((c) => (
              <div
                key={c.event_id}
                className="flex items-center gap-2 rounded px-1.5 py-1 text-[11.5px] hover:bg-surface-2"
              >
                <span className="text-zinc-500">{c.label}</span>
                {c.detail ? (
                  <span className="truncate font-mono text-[10.5px] text-zinc-400">{c.detail}</span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Diagnostics links */}
      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          to={`/runs/${activityRunId}`}
          className="rounded-md border border-edge bg-surface-1 px-2.5 py-1 text-[11px] text-zinc-300 hover:bg-surface-2"
        >
          Open activity run
        </Link>
        <Link
          to={`/runs/${activityRunId}/replay`}
          className="rounded-md border border-edge bg-surface-1 px-2.5 py-1 text-[11px] text-zinc-300 hover:bg-surface-2"
        >
          Replay this
        </Link>
        <button
          type="button"
          onClick={() => setAdvanced((v) => !v)}
          className="ml-auto rounded-md border border-edge bg-surface-1 px-2.5 py-1 text-[11px] text-indigo-300 hover:bg-surface-2"
        >
          {advanced ? "Hide advanced" : "Advanced diagnostics"}
        </button>
      </div>

      {/* Advanced (progressive disclosure): sections + project map */}
      {advanced ? (
        <div className="mt-3 space-y-3" data-testid="advanced-diagnostics">
          <AdvancedSections summary={summary} />
          {mapState.data ? <ProjectMap map={mapState.data} /> : null}
        </div>
      ) : null}
    </Card>
  );
}

function AdvancedSections({ summary }: { summary: DebugSummary }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {/* Agents overview */}
      <div className="rounded-lg border border-edge bg-surface-0 px-3 py-2">
        <div className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Agents ({summary.agents_overview.total})
        </div>
        {Object.entries(summary.agents_overview.by_status).map(([status, agents]) => (
          <div key={status} className="mt-1 text-[11.5px]">
            <span className="font-mono text-zinc-500">{status}:</span>{" "}
            <span className="text-zinc-300">{agents.map((a) => a.name).join(", ")}</span>
          </div>
        ))}
        {summary.agents_overview.total === 0 ? (
          <p className="mt-1 text-[11px] text-zinc-600">No agents yet.</p>
        ) : null}
      </div>

      {/* Workflow progress */}
      <div className="rounded-lg border border-edge bg-surface-0 px-3 py-2">
        <div className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Workflows ({summary.workflow_progress.workflow_count})
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
          {Object.entries(summary.workflow_progress.task_status_counts).map(([s, n]) => (
            <span key={s} className="rounded border border-edge bg-surface-2 px-1.5 py-0.5 text-zinc-400">
              {n} {s}
            </span>
          ))}
          {Object.keys(summary.workflow_progress.task_status_counts).length === 0 ? (
            <span className="text-zinc-600">No tasks yet.</span>
          ) : null}
        </div>
      </div>

      {/* Validation summary */}
      <div className="rounded-lg border border-edge bg-surface-0 px-3 py-2">
        <div className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Validation ({summary.validation_summary.failed} failed / {summary.validation_summary.total})
        </div>
        {summary.validation_summary.recent.slice(0, 3).map((r) => (
          <div key={r.result_id} className="mt-1 text-[11px]">
            <span className={r.passed ? "text-emerald-300" : "text-red-300"}>
              {r.passed ? "✓" : "✗"}
            </span>{" "}
            <span className="font-mono text-zinc-400">{r.validator_type}</span>{" "}
            <span className="text-zinc-500">{r.explanation}</span>
          </div>
        ))}
        {summary.validation_summary.total === 0 ? (
          <p className="mt-1 text-[11px] text-zinc-600">No validations yet.</p>
        ) : null}
      </div>

      {/* Enforcement / approval */}
      <div className="rounded-lg border border-edge bg-surface-0 px-3 py-2">
        <div className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
          Enforcement ({summary.enforcement_summary.pending_approvals} pending approvals)
        </div>
        {summary.enforcement_summary.recent_decisions.slice(0, 3).map((d) => (
          <div key={d.decision_id} className="mt-1 text-[11px]">
            <span className="font-mono text-zinc-400">{d.decision.replace(/_/g, " ")}</span>{" "}
            <span className="text-zinc-500">{d.reason}</span>
          </div>
        ))}
        {summary.enforcement_summary.recent_decisions.length === 0 ? (
          <p className="mt-1 text-[11px] text-zinc-600">No recent decisions.</p>
        ) : null}
      </div>
    </div>
  );
}

function ProjectMap({ map }: { map: DebugMap }) {
  const byType: Record<string, DebugMap["nodes"]> = {};
  for (const node of map.nodes) {
    (byType[node.type] ??= []).push(node);
  }
  const order = ["goal", "workflow", "task", "agent", "artifact", "validation"];
  const columns = order.filter((t) => byType[t]?.length);
  return (
    <div data-testid="project-map" className="rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
        Project map
      </div>
      <div className="mt-2 flex gap-2 overflow-x-auto">
        {columns.map((type, i) => (
          <div key={type} className="flex items-center gap-2">
            <div className="min-w-[120px] space-y-1">
              <div className="text-[9.5px] uppercase tracking-wider text-zinc-600">{type}</div>
              {byType[type].slice(0, 6).map((node) => (
                <div
                  key={node.id}
                  className={`rounded border px-2 py-1 text-[10.5px] ${NODE_STYLE[node.type] ?? NODE_STYLE.task}`}
                >
                  <div className="truncate">{node.label}</div>
                  {node.status ? (
                    <div className="text-[9px] opacity-70">{node.status}</div>
                  ) : null}
                </div>
              ))}
            </div>
            {i < columns.length - 1 ? <span className="text-zinc-600">→</span> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
