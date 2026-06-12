// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RuntimeTask, RuntimeWorkflow, RuntimeWorkflowPlan } from "../../lib/types";

const workflow: RuntimeWorkflow = {
  workflow_id: "wf-1",
  workspace_id: "ws-abc123",
  goal: "Build a website that sells water bottles.",
  status: "planned",
  created_by: "user",
  task_count: 0,
  completed_task_count: 0,
  has_plan: false,
  metadata: {},
  created_at: "2026-06-12T10:00:00Z",
  updated_at: "2026-06-12T10:00:00Z",
};

const plan: RuntimeWorkflowPlan = {
  plan_id: "plan-1",
  workflow_id: "wf-1",
  summary: "Deterministic 5-step pipeline for: Build a website that sells water bottles.",
  steps: [],
  dependencies: {},
  required_agents: ["planner"],
  risk_assessment: null,
  validation_requirements: [],
  approval_requirements: [],
  created_at: "2026-06-12T10:00:00Z",
};

function task(overrides: Partial<RuntimeTask>): RuntimeTask {
  return {
    task_id: "task-1",
    workflow_id: "wf-1",
    workspace_id: "ws-abc123",
    assigned_agent_id: "agent-1",
    assigned_agent_name: "Planner",
    title: "Draft the project plan",
    description: "Break the goal into work items.",
    status: "pending",
    dependencies: [],
    expected_artifacts: ["plan"],
    risk_level: "low",
    requires_validation: false,
    requires_approval: false,
    blocked_reason: null,
    latest_result: null,
    metadata: {},
    created_at: "2026-06-12T10:00:00Z",
    updated_at: "2026-06-12T10:00:00Z",
    ...overrides,
  };
}

const workspaceWorkflows = vi.fn();
const createWorkflow = vi.fn();
const workflowPlan = vi.fn();
const createWorkflowPlan = vi.fn();
const workflowAction = vi.fn();
const workflowTasks = vi.fn();
const recordTaskResult = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    workspaceWorkflows: (...a: unknown[]) => workspaceWorkflows(...a),
    createWorkflow: (...a: unknown[]) => createWorkflow(...a),
    workflowPlan: (...a: unknown[]) => workflowPlan(...a),
    createWorkflowPlan: (...a: unknown[]) => createWorkflowPlan(...a),
    workflowAction: (...a: unknown[]) => workflowAction(...a),
    workflowTasks: (...a: unknown[]) => workflowTasks(...a),
    recordTaskResult: (...a: unknown[]) => recordTaskResult(...a),
  },
}));

import { WorkflowsPanel } from "./WorkflowsPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <WorkflowsPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  workspaceWorkflows.mockResolvedValue([workflow]);
  workflowTasks.mockResolvedValue([]);
  workflowPlan.mockResolvedValue(plan);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkflowsPanel", () => {
  it("renders the empty state when there are no workflows", async () => {
    workspaceWorkflows.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByTestId("workflows-empty")).toBeTruthy();
    expect(screen.getByText("orchestration · no auto-execution")).toBeTruthy();
  });

  it("creates a workflow from the workspace goal", async () => {
    workspaceWorkflows.mockResolvedValue([]);
    createWorkflow.mockResolvedValue(workflow);
    renderPanel();
    fireEvent.click(await screen.findByText("+ New workflow"));
    await waitFor(() =>
      expect(createWorkflow).toHaveBeenCalledWith("ws-abc123", {}),
    );
  });

  it("renders workflow status and generates a plan", async () => {
    createWorkflowPlan.mockResolvedValue(plan);
    renderPanel();
    const status = await screen.findByTestId("workflow-status");
    expect(status.textContent).toBe("planned");
    fireEvent.click(screen.getByText("Generate plan"));
    await waitFor(() =>
      expect(createWorkflowPlan).toHaveBeenCalledWith("ws-abc123", "wf-1"),
    );
  });

  it("renders the plan summary and task cards with agents", async () => {
    workspaceWorkflows.mockResolvedValue([
      { ...workflow, has_plan: true, task_count: 2 },
    ]);
    workflowTasks.mockResolvedValue([
      task({}),
      task({
        task_id: "task-2",
        title: "Build the backend",
        assigned_agent_name: "Backend Coder",
        risk_level: "high",
        dependencies: ["task-1"],
      }),
    ]);
    renderPanel();
    expect((await screen.findByTestId("plan-summary")).textContent).toContain(
      "Deterministic 5-step pipeline",
    );
    const cards = screen.getAllByTestId("task-card");
    expect(cards).toHaveLength(2);
    expect(cards[0].textContent).toContain("Planner");
    expect(cards[1].textContent).toContain("Backend Coder");
    expect(cards[1].textContent).toContain("risk high");
    expect(cards[1].textContent).toContain("after: Draft the project plan");
  });

  it("shows the blocked reason for unassigned tasks", async () => {
    workspaceWorkflows.mockResolvedValue([
      { ...workflow, has_plan: true, task_count: 1 },
    ]);
    workflowTasks.mockResolvedValue([
      task({
        status: "blocked",
        assigned_agent_id: null,
        assigned_agent_name: null,
        blocked_reason: "no assignable backend coder agent",
      }),
    ]);
    renderPanel();
    const reason = await screen.findByTestId("task-blocked-reason");
    expect(reason.textContent).toContain("no assignable backend coder agent");
    expect(screen.getByText("unassigned")).toBeTruthy();
  });

  it("runs lifecycle actions", async () => {
    workspaceWorkflows.mockResolvedValue([
      { ...workflow, status: "running", has_plan: true },
    ]);
    workflowAction.mockResolvedValue({ ...workflow, status: "paused" });
    renderPanel();
    fireEvent.click(await screen.findByText("pause"));
    await waitFor(() =>
      expect(workflowAction).toHaveBeenCalledWith("ws-abc123", "wf-1", "pause"),
    );
  });

  it("records a task result for a running task", async () => {
    workspaceWorkflows.mockResolvedValue([
      { ...workflow, status: "running", has_plan: true, task_count: 1 },
    ]);
    workflowTasks.mockResolvedValue([task({ status: "running" })]);
    recordTaskResult.mockResolvedValue(task({ status: "completed" }));
    renderPanel();
    const draft = await screen.findByPlaceholderText(
      "Record what was produced for this task…",
    );
    fireEvent.change(draft, { target: { value: "Plan drafted." } });
    fireEvent.click(screen.getByText("Record result"));
    await waitFor(() =>
      expect(recordTaskResult).toHaveBeenCalledWith("ws-abc123", "wf-1", "task-1", {
        output: "Plan drafted.",
      }),
    );
  });

  it("renders the latest result on completed tasks", async () => {
    workspaceWorkflows.mockResolvedValue([
      { ...workflow, status: "completed", has_plan: true, task_count: 1 },
    ]);
    workflowTasks.mockResolvedValue([
      task({
        status: "completed",
        latest_result: {
          result_id: "tr-1",
          task_id: "task-1",
          agent_id: "agent-1",
          output: "Plan drafted with 5 steps.",
          artifacts: [],
          validation_status: "not_validated",
          created_at: "2026-06-12T10:05:00Z",
        },
      }),
    ]);
    renderPanel();
    expect((await screen.findByTestId("task-result")).textContent).toContain(
      "Plan drafted with 5 steps.",
    );
  });

  it("disables workflow mutations in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const newWorkflow = (await screen.findByText("+ New workflow")) as HTMLButtonElement;
    expect(newWorkflow.disabled).toBe(true);
    expect(newWorkflow.title).toBe("Switch to Agent Mode to perform this action.");
    const generate = screen.getByText("Generate plan") as HTMLButtonElement;
    expect(generate.disabled).toBe(true);
  });

  it("hides mutating controls for read-only workspaces", async () => {
    renderPanel({ readOnly: true });
    await screen.findByTestId("workflow-status");
    expect(screen.queryByText("+ New workflow")).toBeNull();
    expect(screen.queryByText("Generate plan")).toBeNull();
    expect(screen.queryByText("cancel")).toBeNull();
  });
});
