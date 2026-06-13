import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ModeSwitcher } from "../components/assistant/ModeSwitcher";
import { ApprovalsPanel } from "../components/runtime/ApprovalsPanel";
import { ValidatorsPanel } from "../components/runtime/ValidatorsPanel";
import { EnforcementPanel } from "../components/runtime/EnforcementPanel";
import { SandboxCommandsPanel } from "../components/runtime/SandboxCommandsPanel";
import { SandboxFilesPanel } from "../components/runtime/SandboxFilesPanel";
import { WorkflowsPanel } from "../components/runtime/WorkflowsPanel";
import { WorkspaceAgentsPanel } from "../components/runtime/WorkspaceAgentsPanel";
import { WorkspaceStatusBadge } from "../components/runtime/WorkspaceStatusBadge";
import { Card, ErrorNote, PageHeader, SectionLabel, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { fmtClock, timeAgo } from "../lib/format";
import type { WorkspaceStatus } from "../lib/types";
import { useAppStore } from "../store/app";

const STATUS_BANNER: Record<WorkspaceStatus, { text: string; className: string }> = {
  draft: {
    text: "Draft — define the goal, then activate the workspace.",
    className: "border-zinc-600/30 bg-zinc-700/10 text-zinc-300",
  },
  active: {
    text: "Active — this workspace is the current focus.",
    className: "border-emerald-400/30 bg-emerald-400/5 text-emerald-200",
  },
  paused: {
    text: "Paused — work is on hold; resume when ready.",
    className: "border-amber-400/30 bg-amber-400/5 text-amber-200",
  },
  completed: {
    text: "Completed — the goal has been met.",
    className: "border-sky-400/30 bg-sky-400/5 text-sky-200",
  },
  archived: {
    text: "Archived — read-only history. Workspace history is never deleted.",
    className: "border-zinc-600/30 bg-zinc-800/40 text-zinc-400",
  },
  failed: {
    text: "Failed — mark active again to retry, or archive it.",
    className: "border-red-400/40 bg-red-400/5 text-red-200",
  },
};

/** Status actions offered from each state (v1.0 lifecycle is intentionally permissive). */
const STATUS_ACTIONS: Record<WorkspaceStatus, { label: string; to: WorkspaceStatus }[]> = {
  draft: [{ label: "Activate", to: "active" }],
  active: [
    { label: "Pause", to: "paused" },
    { label: "Mark completed", to: "completed" },
    { label: "Mark failed", to: "failed" },
  ],
  paused: [{ label: "Resume", to: "active" }],
  completed: [{ label: "Reopen", to: "active" }],
  failed: [{ label: "Reactivate", to: "active" }],
  archived: [],
};

export function RuntimeWorkspacePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const workspaceState = useFetch(() => api.runtimeWorkspace(workspaceId!), [workspaceId]);
  const activityState = useFetch(() => api.runtimeWorkspaceActivity(workspaceId!), [workspaceId]);
  const artifactsState = useFetch(
    () => api.runtimeWorkspaceArtifacts(workspaceId!),
    [workspaceId],
  );
  const chatMode = useAppStore((s) => s.studioMode) === "chat";

  const [goal, setGoal] = useState("");
  const [goalDirty, setGoalDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [artifactName, setArtifactName] = useState("");
  const [artifactType, setArtifactType] = useState("file");
  const [artifactPath, setArtifactPath] = useState("");

  useEffect(() => {
    if (workspaceState.data) {
      setGoal(workspaceState.data.goal ?? "");
      setGoalDirty(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceState.data?.workspace_id, workspaceState.data?.updated_at]);

  const refreshAll = () => {
    workspaceState.refetch(true);
    activityState.refetch(true);
    artifactsState.refetch(true);
  };

  const act = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setActionError(null);
    try {
      await action();
      refreshAll();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (workspaceState.loading) return <Spinner label="Loading workspace…" />;
  if (workspaceState.error) return <ErrorNote message={workspaceState.error} />;
  const workspace = workspaceState.data!;
  const banner = STATUS_BANNER[workspace.status];
  const actions = STATUS_ACTIONS[workspace.status];

  return (
    <>
      <PageHeader
        title={workspace.name}
        subtitle={
          <span className="font-mono text-[11.5px]">
            {workspace.workspace_id} · project{" "}
            <Link to={`/projects/${workspace.project_id}`} className="text-indigo-300 hover:underline">
              {workspace.project_id}
            </Link>
          </span>
        }
        actions={
          <>
            <ModeSwitcher />
            <Link
              to="/runtime"
              className="rounded-lg border border-edge bg-surface-1 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-2"
            >
              ← Workspaces
            </Link>
          </>
        }
      />

      {/* Status banner */}
      <div
        data-testid="workspace-status-banner"
        className={`mb-4 flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-[12.5px] ${banner.className}`}
      >
        <WorkspaceStatusBadge status={workspace.status} />
        <span>{banner.text}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {actions.map((action) => (
            <button
              key={action.to + action.label}
              type="button"
              disabled={chatMode || busy !== null}
              title={chatMode ? "Switch to Agent Mode to perform this action." : undefined}
              onClick={() =>
                act(action.label, () =>
                  api.patchRuntimeWorkspace(workspace.workspace_id, { status: action.to }),
                )
              }
              className="rounded-md border border-edge bg-surface-1 px-2.5 py-1 text-[11.5px] font-medium text-zinc-300 transition-colors hover:bg-surface-2 disabled:opacity-40"
            >
              {busy === action.label ? "…" : action.label}
            </button>
          ))}
          {workspace.status !== "archived" ? (
            <button
              type="button"
              disabled={chatMode || busy !== null}
              title={chatMode ? "Switch to Agent Mode to perform this action." : undefined}
              onClick={() =>
                act("Archive", () => api.archiveRuntimeWorkspace(workspace.workspace_id))
              }
              className="rounded-md border border-red-400/25 bg-red-400/5 px-2.5 py-1 text-[11.5px] text-red-300/90 transition-colors hover:bg-red-400/15 disabled:opacity-40"
            >
              {busy === "Archive" ? "…" : "Archive"}
            </button>
          ) : null}
        </div>
      </div>
      {actionError ? <div className="mb-4"><ErrorNote message={actionError} /></div> : null}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="min-w-0 flex-1 space-y-4">
          {/* Goal summary */}
          <Card className="px-4 py-4">
            <SectionLabel>Goal</SectionLabel>
            <textarea
              value={goal}
              onChange={(e) => {
                setGoal(e.target.value);
                setGoalDirty(true);
              }}
              rows={3}
              placeholder="What should this workspace eventually build?"
              disabled={workspace.status === "archived"}
              className="w-full rounded-lg border border-edge bg-surface-0 px-2.5 py-1.5 text-[12.5px] leading-5 text-zinc-200 disabled:opacity-60"
            />
            {goalDirty ? (
              <button
                type="button"
                disabled={chatMode || busy !== null}
                title={chatMode ? "Switch to Agent Mode to perform this action." : undefined}
                onClick={() =>
                  act("goal", () =>
                    api.patchRuntimeWorkspace(workspace.workspace_id, { goal: goal.trim() || null }),
                  )
                }
                className="mt-2 rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
              >
                {busy === "goal" ? "Saving…" : "Save goal"}
              </button>
            ) : null}
          </Card>

          {/* Agents (v1.1) */}
          <WorkspaceAgentsPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Orchestration (v1.4) */}
          <WorkflowsPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Sandboxed files (v1.2) */}
          <SandboxFilesPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Sandbox commands (v1.3) */}
          <SandboxCommandsPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Enforcement gateway (v1.5) */}
          <EnforcementPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Human approvals (v1.6) */}
          <ApprovalsPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Deterministic validators (v1.8) */}
          <ValidatorsPanel
            workspaceId={workspace.workspace_id}
            readOnly={workspace.status === "archived"}
            chatMode={chatMode}
          />

          {/* Project health placeholder */}
          <Card className="px-4 py-4">
            <SectionLabel>Project health</SectionLabel>
            <div className="grid grid-cols-3 gap-2 text-center">
              {["build", "tests", "policy"].map((label) => (
                <div key={label} className="rounded-md bg-surface-2 px-2 py-3">
                  <div className="font-mono text-[15px] text-zinc-600">—</div>
                  <div className="mt-0.5 text-[10.5px] uppercase tracking-wider text-zinc-600">
                    {label}
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11.5px] leading-5 text-zinc-600">
              Health signals arrive with later Runtime versions — v1.0 workspaces do not run
              commands, write files, or enforce policies yet.
            </p>
          </Card>

          {/* Artifacts */}
          <Card className="px-4 py-4">
            <SectionLabel>Artifacts</SectionLabel>
            {artifactsState.data && artifactsState.data.length > 0 ? (
              <div className="space-y-1.5">
                {artifactsState.data.map((artifact) => (
                  <div
                    key={artifact.artifact_id}
                    className="flex flex-wrap items-center gap-2 rounded-md border border-edge bg-surface-2 px-2.5 py-1.5 text-[12px]"
                  >
                    <span className="font-medium text-zinc-200">{artifact.name}</span>
                    <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500">
                      {artifact.type}
                    </span>
                    {artifact.path ? (
                      <span className="font-mono text-[11px] text-zinc-500">{artifact.path}</span>
                    ) : null}
                    <span className="ml-auto text-[10.5px] text-zinc-600">
                      {timeAgo(artifact.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-zinc-600">
                No artifacts registered yet — entries here are metadata pointers for future
                project outputs.
              </p>
            )}
            {workspace.status !== "archived" ? (
              <div className="mt-3 flex flex-wrap items-end gap-2">
                <label className="flex min-w-[160px] flex-1 flex-col gap-1">
                  <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                    Name
                  </span>
                  <input
                    value={artifactName}
                    onChange={(e) => setArtifactName(e.target.value)}
                    placeholder="index.html"
                    className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12px] text-zinc-200"
                  />
                </label>
                <label className="flex w-28 flex-col gap-1">
                  <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                    Type
                  </span>
                  <input
                    value={artifactType}
                    onChange={(e) => setArtifactType(e.target.value)}
                    className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200"
                  />
                </label>
                <label className="flex min-w-[160px] flex-1 flex-col gap-1">
                  <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                    Path (logical)
                  </span>
                  <input
                    value={artifactPath}
                    onChange={(e) => setArtifactPath(e.target.value)}
                    placeholder="site/index.html"
                    className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200"
                  />
                </label>
                <button
                  type="button"
                  disabled={chatMode || busy !== null || !artifactName.trim()}
                  title={chatMode ? "Switch to Agent Mode to perform this action." : undefined}
                  onClick={() =>
                    act("artifact", async () => {
                      await api.registerRuntimeArtifact(workspace.workspace_id, {
                        name: artifactName.trim(),
                        type: artifactType.trim() || "file",
                        path: artifactPath.trim() || null,
                      });
                      setArtifactName("");
                      setArtifactPath("");
                    })
                  }
                  className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
                >
                  {busy === "artifact" ? "Registering…" : "Register artifact"}
                </button>
              </div>
            ) : null}
          </Card>
        </div>

        {/* Recent activity */}
        <div className="w-full shrink-0 space-y-4 lg:w-[360px]">
          <Card className="px-4 py-4">
            <div className="flex items-center justify-between">
              <SectionLabel>Recent activity</SectionLabel>
              <Link
                to={`/runs/${workspace.activity_run_id}?tab=timeline`}
                className="text-[11px] text-indigo-300 hover:underline"
              >
                timeline ↗
              </Link>
            </div>
            {activityState.data && activityState.data.length > 0 ? (
              <div className="space-y-1.5">
                {activityState.data.slice(0, 12).map((event) => (
                  <div
                    key={event.event_id}
                    className="flex items-center gap-2 rounded-md border border-edge bg-surface-2 px-2.5 py-1.5 text-[11.5px]"
                  >
                    <span className="font-mono text-zinc-300">{event.event_type}</span>
                    <span className="ml-auto shrink-0 font-mono text-[10.5px] text-zinc-600">
                      {fmtClock(event.timestamp)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-zinc-600">No activity yet.</p>
            )}
            <div className="mt-3 flex gap-2 text-[11.5px]">
              <Link
                to={`/runs/${workspace.activity_run_id}?tab=replay`}
                className="rounded-md border border-edge bg-surface-1 px-2 py-1 text-zinc-300 transition-colors hover:bg-surface-2"
              >
                Replay history
              </Link>
              <Link
                to={`/runs/${workspace.activity_run_id}`}
                className="rounded-md border border-edge bg-surface-1 px-2 py-1 text-zinc-300 transition-colors hover:bg-surface-2"
              >
                Open activity run
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
