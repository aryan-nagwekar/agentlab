import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { RuntimeTask, RuntimeWorkflow } from "../../lib/types";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

const WORKFLOW_STATUS_STYLE: Record<RuntimeWorkflow["status"], string> = {
  planned: "border-edge bg-surface-2 text-zinc-300",
  running: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  paused: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  blocked: "border-red-400/40 bg-red-400/10 text-red-300",
  failed: "border-red-400/40 bg-red-400/10 text-red-300",
  completed: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  cancelled: "border-edge bg-surface-2 text-zinc-500",
};

const TASK_STATUS_STYLE: Record<string, string> = {
  pending: "border-edge bg-surface-2 text-zinc-400",
  running: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  blocked: "border-red-400/40 bg-red-400/10 text-red-300",
  failed: "border-red-400/40 bg-red-400/10 text-red-300",
  completed: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  rerouted: "border-amber-400/30 bg-amber-400/10 text-amber-300",
};

const RISK_STYLE: Record<string, string> = {
  low: "text-zinc-500",
  medium: "text-amber-300/90",
  high: "text-red-300/90",
};

// Lifecycle actions offered per workflow status (plan generation is separate).
const ACTIONS: Record<string, Array<"start" | "pause" | "resume" | "cancel">> = {
  planned: ["start", "cancel"],
  running: ["pause", "cancel"],
  paused: ["resume", "cancel"],
  blocked: ["resume", "cancel"],
};

export function WorkflowsPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const workflowsState = useFetch(
    () => api.workspaceWorkflows(workspaceId),
    [workspaceId],
  );
  const workflows = workflowsState.data ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected =
    workflows.find((w) => w.workflow_id === selectedId) ?? workflows[0] ?? null;

  const tasksState = useFetch(
    () =>
      selected
        ? api.workflowTasks(workspaceId, selected.workflow_id)
        : Promise.resolve([]),
    [workspaceId, selected?.workflow_id, selected?.status, selected?.task_count],
  );
  const planState = useFetch(
    () =>
      selected?.has_plan
        ? api.workflowPlan(workspaceId, selected.workflow_id)
        : Promise.resolve(null),
    [workspaceId, selected?.workflow_id, selected?.has_plan],
  );

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultDrafts, setResultDrafts] = useState<Record<string, string>>({});

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      workflowsState.refetch(true);
      tasksState.refetch(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (workflowsState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Workflows</SectionLabel>
        <Spinner label="Loading workflows…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Workflows</SectionLabel>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
            orchestration · no auto-execution
          </span>
          {!readOnly ? (
            <button
              type="button"
              disabled={disabled || busy}
              title={hintTitle}
              onClick={() => act(() => api.createWorkflow(workspaceId, {}))}
              className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              + New workflow
            </button>
          ) : null}
        </div>
      </div>

      {workflows.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="workflows-empty">
          No workflows yet — create one from the workspace goal. The planner builds a
          task pipeline and assigns your workspace agents; nothing runs files or
          commands automatically in v1.4.
        </p>
      ) : (
        <>
          {workflows.length > 1 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {workflows.map((wf) => (
                <button
                  key={wf.workflow_id}
                  type="button"
                  onClick={() => setSelectedId(wf.workflow_id)}
                  className={`rounded-md border px-2 py-0.5 font-mono text-[10.5px] transition-colors ${
                    wf.workflow_id === selected?.workflow_id
                      ? "border-indigo-400/50 bg-indigo-500/15 text-indigo-200"
                      : "border-edge bg-surface-2 text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {wf.workflow_id}
                </button>
              ))}
            </div>
          ) : null}

          {selected ? (
            <div data-testid="workflow-detail" className="mt-3">
              {/* Status banner + lifecycle controls */}
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-edge bg-surface-0 px-3 py-2">
                <span
                  data-testid="workflow-status"
                  className={`rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${WORKFLOW_STATUS_STYLE[selected.status]}`}
                >
                  {selected.status}
                </span>
                <span className="text-[11.5px] text-zinc-400">
                  {selected.completed_task_count}/{selected.task_count} tasks done
                </span>
                {!readOnly ? (
                  <span className="ml-auto flex gap-1.5">
                    {!selected.has_plan && selected.status === "planned" ? (
                      <button
                        type="button"
                        disabled={disabled || busy}
                        title={hintTitle}
                        onClick={() =>
                          act(() =>
                            api.createWorkflowPlan(workspaceId, selected.workflow_id),
                          )
                        }
                        className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
                      >
                        Generate plan
                      </button>
                    ) : null}
                    {(ACTIONS[selected.status] ?? [])
                      .filter((action) => action !== "start" || selected.has_plan)
                      .map((action) => (
                        <button
                          key={action}
                          type="button"
                          disabled={disabled || busy}
                          title={hintTitle}
                          onClick={() =>
                            act(() =>
                              api.workflowAction(
                                workspaceId,
                                selected.workflow_id,
                                action,
                              ),
                            )
                          }
                          className={`rounded-md border px-2.5 py-1 text-[11.5px] transition-colors disabled:opacity-40 ${
                            action === "cancel"
                              ? "border-red-400/30 bg-red-400/10 text-red-300 hover:bg-red-400/20"
                              : "border-edge bg-surface-1 text-zinc-300 hover:bg-surface-2"
                          }`}
                        >
                          {action}
                        </button>
                      ))}
                  </span>
                ) : null}
              </div>

              <p className="mt-2 text-[12px] text-zinc-400">
                <span className="text-zinc-600">Goal:</span> {selected.goal}
              </p>

              {planState.data ? (
                <p className="mt-1 text-[11.5px] text-zinc-500" data-testid="plan-summary">
                  {planState.data.summary}
                </p>
              ) : null}

              {/* Task cards */}
              {tasksState.data && tasksState.data.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {tasksState.data.map((task) => (
                    <TaskCard
                      key={task.task_id}
                      task={task}
                      allTasks={tasksState.data!}
                      disabled={disabled}
                      hintTitle={hintTitle}
                      readOnly={readOnly}
                      busy={busy}
                      draft={resultDrafts[task.task_id] ?? ""}
                      setDraft={(value) =>
                        setResultDrafts((d) => ({ ...d, [task.task_id]: value }))
                      }
                      onRecord={() =>
                        act(async () => {
                          await api.recordTaskResult(
                            workspaceId,
                            selected.workflow_id,
                            task.task_id,
                            { output: resultDrafts[task.task_id] ?? "" },
                          );
                          setResultDrafts((d) => ({ ...d, [task.task_id]: "" }));
                        })
                      }
                    />
                  ))}
                </div>
              ) : selected.has_plan ? null : (
                <p className="mt-3 text-[12px] text-zinc-600" data-testid="tasks-empty">
                  No tasks yet — generate the plan to create and assign tasks.
                </p>
              )}
            </div>
          ) : null}
        </>
      )}
      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}
    </Card>
  );
}

function TaskCard({
  task,
  allTasks,
  disabled,
  hintTitle,
  readOnly,
  busy,
  draft,
  setDraft,
  onRecord,
}: {
  task: RuntimeTask;
  allTasks: RuntimeTask[];
  disabled: boolean;
  hintTitle: string | undefined;
  readOnly: boolean;
  busy: boolean;
  draft: string;
  setDraft: (value: string) => void;
  onRecord: () => void;
}) {
  const titleById = new Map(allTasks.map((t) => [t.task_id, t.title]));
  return (
    <div
      data-testid="task-card"
      className="rounded-lg border border-edge bg-surface-0 px-3 py-2.5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12.5px] font-medium text-zinc-200">{task.title}</span>
        <span
          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${TASK_STATUS_STYLE[task.status] ?? "border-edge bg-surface-2 text-zinc-400"}`}
        >
          {task.status.replace(/_/g, " ")}
        </span>
        <span className={`text-[10.5px] ${RISK_STYLE[task.risk_level] ?? "text-zinc-500"}`}>
          risk {task.risk_level}
        </span>
        <span className="ml-auto text-[11px] text-zinc-500">
          {task.assigned_agent_name ?? task.assigned_agent_id ?? "unassigned"}
        </span>
      </div>
      {task.description ? (
        <p className="mt-1 text-[11.5px] text-zinc-500">{task.description}</p>
      ) : null}
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[10.5px] text-zinc-600">
        {task.dependencies.length > 0 ? (
          <span>
            after: {task.dependencies.map((d) => titleById.get(d) ?? d).join(", ")}
          </span>
        ) : null}
        {task.expected_artifacts.length > 0 ? (
          <span>produces: {task.expected_artifacts.join(", ")}</span>
        ) : null}
      </div>
      {task.blocked_reason ? (
        <p data-testid="task-blocked-reason" className="mt-1.5 text-[11.5px] text-red-300/90">
          {task.blocked_reason}
        </p>
      ) : null}
      {task.latest_result ? (
        <p
          data-testid="task-result"
          className="mt-1.5 rounded-md bg-surface-2 px-2 py-1.5 font-mono text-[11px] text-zinc-300"
        >
          {task.latest_result.output}
        </p>
      ) : null}
      {task.status === "running" && !readOnly ? (
        <div className="mt-2 flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder="Record what was produced for this task…"
            readOnly={disabled}
            className="min-w-0 flex-1 rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[11.5px] text-zinc-200"
          />
          <button
            type="button"
            disabled={disabled || busy || !draft.trim()}
            title={hintTitle}
            onClick={onRecord}
            className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1.5 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
          >
            Record result
          </button>
        </div>
      ) : null}
    </div>
  );
}
