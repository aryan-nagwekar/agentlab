import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge, Card, EmptyState, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";

const RUN_BADGE: Record<string, string> = {
  completed: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  failed: "border-red-400/40 bg-red-400/10 text-red-300",
};

export function StudioPage() {
  const { data: workflows, loading, error } = useFetch(() => api.studioWorkflows(), []);
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const createWorkflow = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const workflow = await api.createStudioWorkflow({
        name: "Untitled Workflow",
        description: null,
        project_id: "demo-project",
        agents: [
          {
            agent_id: "agent-1",
            name: "Agent 1",
            role: "assistant",
            provider: "mock",
            model_name: "mock:claude-sonnet",
            temperature: 0.2,
            max_tokens: 1000,
            position_x: 0,
            position_y: 0,
          },
        ],
        edges: [],
      });
      navigate(`/studio/workflows/${workflow.workflow_id}`);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  if (loading) return <Spinner label="Loading workflows…" />;
  if (error) return <ErrorNote message={error} />;

  return (
    <>
      <PageHeader
        title="Agent Builder Studio"
        subtitle="Build multi-agent workflows, run them through the Model Gateway, and debug them with the full AgentLab toolchain"
        actions={
          <>
            <Link
              to="/studio/templates"
              className="rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-[12px] font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25"
            >
              Start from template
            </Link>
            <button
              type="button"
              onClick={createWorkflow}
              disabled={creating}
              className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {creating ? "Creating…" : "+ New Workflow"}
            </button>
          </>
        }
      />
      {createError ? <ErrorNote message={createError} /> : null}
      {!workflows || workflows.length === 0 ? (
        <EmptyState title="No workflows yet">
          Create a workflow to start building a multi-agent system — the mock provider works
          without any API keys.
        </EmptyState>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {workflows.map((workflow) => (
            <Link key={workflow.workflow_id} to={`/studio/workflows/${workflow.workflow_id}`}>
              <Card className="h-full px-4 py-4 transition-colors hover:border-edge-strong hover:bg-surface-2">
                <div className="flex items-start gap-2">
                  <div className="text-[15px] font-semibold text-zinc-100">{workflow.name}</div>
                  {workflow.last_run_status ? (
                    <Badge
                      className={`ml-auto ${RUN_BADGE[workflow.last_run_status] ?? "border-zinc-600/30 bg-zinc-600/10 text-zinc-400"}`}
                    >
                      last run {workflow.last_run_status}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-zinc-600">
                  {workflow.workflow_id}
                </div>
                {workflow.description ? (
                  <p className="mt-2 line-clamp-2 text-[12.5px] text-zinc-500">
                    {workflow.description}
                  </p>
                ) : null}
                <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[11px]">
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">{workflow.agent_count}</div>
                    <div className="text-zinc-600">agents</div>
                  </div>
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">{workflow.edge_count}</div>
                    <div className="text-zinc-600">edges</div>
                  </div>
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">
                      {timeAgo(workflow.updated_at)}
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
