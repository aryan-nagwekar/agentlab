import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ModeSwitcher } from "../components/assistant/ModeSwitcher";
import { WorkspaceStatusBadge } from "../components/runtime/WorkspaceStatusBadge";
import { Card, EmptyState, ErrorNote, PageHeader, SectionLabel, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import { useAppStore } from "../store/app";

export function RuntimeWorkspacesPage() {
  const { data: workspaces, loading, error } = useFetch(() => api.runtimeWorkspaces(), []);
  const navigate = useNavigate();
  const chatMode = useAppStore((s) => s.studioMode) === "chat";
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const create = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const workspace = await api.createRuntimeWorkspace({
        name: name.trim(),
        goal: goal.trim() || null,
      });
      navigate(`/runtime/workspaces/${workspace.workspace_id}`);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
      setCreating(false);
    }
  };

  if (loading) return <Spinner label="Loading workspaces…" />;
  if (error) return <ErrorNote message={error} />;

  return (
    <>
      <PageHeader
        title="Runtime Workspaces"
        subtitle="Project areas for future AI-built software — v1.0 is metadata and history only: no commands, files, or enforcement yet"
        actions={
          <>
            <ModeSwitcher />
            <button
              type="button"
              onClick={() => setShowCreate((s) => !s)}
              disabled={chatMode}
              title={chatMode ? "Switch to Agent Mode to perform this action." : undefined}
              className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              + New Workspace
            </button>
          </>
        }
      />

      {showCreate ? (
        <Card className="mb-4 px-4 py-4">
          <SectionLabel>Create workspace</SectionLabel>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Name
              </span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My project workspace"
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Goal (optional)
              </span>
              <input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="What this workspace should eventually build"
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
              />
            </label>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={create}
              disabled={creating || !name.trim()}
              className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {creating ? "Creating…" : "Create workspace"}
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="rounded-lg px-2 py-1.5 text-[12px] text-zinc-500 hover:text-zinc-300"
            >
              Cancel
            </button>
          </div>
          {createError ? <div className="mt-2"><ErrorNote message={createError} /></div> : null}
        </Card>
      ) : null}

      {!workspaces || workspaces.length === 0 ? (
        <EmptyState title="No workspaces yet">
          A workspace is the future home of an AI-built project. Create one to start tracking its
          goal, status, artifacts, and activity — execution arrives in later Runtime versions.
        </EmptyState>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((workspace) => (
            <Link
              key={workspace.workspace_id}
              to={`/runtime/workspaces/${workspace.workspace_id}`}
            >
              <Card className="h-full px-4 py-4 transition-colors hover:border-edge-strong hover:bg-surface-2">
                <div className="flex items-start gap-2">
                  <div className="text-[15px] font-semibold text-zinc-100">{workspace.name}</div>
                  <WorkspaceStatusBadge status={workspace.status} className="ml-auto shrink-0" />
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-zinc-600">
                  {workspace.workspace_id}
                </div>
                {workspace.goal ? (
                  <p className="mt-2 line-clamp-2 text-[12.5px] text-zinc-500">{workspace.goal}</p>
                ) : null}
                <div className="mt-4 grid grid-cols-2 gap-2 text-center text-[11px]">
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">
                      {workspace.artifact_count}
                    </div>
                    <div className="text-zinc-600">artifacts</div>
                  </div>
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">
                      {timeAgo(workspace.updated_at)}
                    </div>
                    <div className="text-zinc-600">updated</div>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
