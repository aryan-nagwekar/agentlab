// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DebugIssue, DebugMap, DebugSummary } from "../../lib/types";

function summary(overrides: Partial<DebugSummary> = {}): DebugSummary {
  return {
    workspace_id: "ws-abc123",
    workspace_status: "active",
    health: { state: "safe_to_continue", label: "Safe to continue", severity: "ok", active_labels: ["Safe to continue"] },
    recommended_actions: [{ action: "none", label: "No action needed — safe to continue", link: "" }],
    counts: { agents: 1 },
    agents_overview: {
      total: 1,
      by_status: { ready: [{ agent_id: "a1", name: "Planner", role: "Planner", trust_score: 1, risk_score: 0, current_assignment: null, restricted: false }] },
    },
    workflow_progress: { workflow_count: 1, active_workflows: [], task_status_counts: { completed: 2 }, blocked_tasks: [] },
    validation_summary: { total: 1, failed: 0, recent: [{ result_id: "v1", validator_type: "code_syntax", passed: true, target_ref: "a.py", explanation: "Python syntax is valid.", suggested_action: null }] },
    enforcement_summary: { pending_approvals: 0, recent_decisions: [] },
    recent_changes: [{ category: "files", label: "File created", detail: "index.html", event_type: "sandbox.file.created", timestamp: "2026-06-13T10:00:00Z", event_id: "e1" }],
    ...overrides,
  };
}

const debugSummary = vi.fn();
const debugIssues = vi.fn();
const debugProjectMap = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    debugSummary: (...a: unknown[]) => debugSummary(...a),
    debugIssues: (...a: unknown[]) => debugIssues(...a),
    debugProjectMap: (...a: unknown[]) => debugProjectMap(...a),
  },
}));

import { ProjectDebugPanel } from "./ProjectDebugPanel";

function renderPanel() {
  return render(
    <MemoryRouter>
      <ProjectDebugPanel workspaceId="ws-abc123" activityRunId="ws-abc123-activity" />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  debugSummary.mockResolvedValue(summary());
  debugIssues.mockResolvedValue([]);
  debugProjectMap.mockResolvedValue({ nodes: [], edges: [] } satisfies DebugMap);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProjectDebugPanel", () => {
  it("renders the health banner and recommended actions", async () => {
    renderPanel();
    expect((await screen.findByTestId("project-health")).textContent).toContain("Safe to continue");
    expect(screen.getByTestId("recommended-actions").textContent).toContain("No action needed");
  });

  it("renders the no-issues state when there is nothing to attend to", async () => {
    renderPanel();
    expect(await screen.findByTestId("no-issues")).toBeTruthy();
  });

  it("renders recent changes", async () => {
    renderPanel();
    expect((await screen.findByTestId("recent-changes")).textContent).toContain("File created");
  });

  it("renders pending-approval health and issue", async () => {
    debugSummary.mockResolvedValue(
      summary({
        health: { state: "approval_needed", label: "Needs approval", severity: "high", active_labels: ["Needs approval"] },
        recommended_actions: [{ action: "review_approval", label: "Review 1 pending approval", link: "approvals" }],
      }),
    );
    debugIssues.mockResolvedValue([
      { severity: "high", kind: "approval_needed", title: "Needs approval: file.write: src/payment/checkout.ts", detail: "AgentLab paused this action.", suggested_action: "recommended: approve_once", link: "approvals", ref: "apr-1" },
    ] satisfies DebugIssue[]);
    renderPanel();
    expect((await screen.findByTestId("project-health")).textContent).toContain("Needs approval");
    expect(screen.getByTestId("recommended-actions").textContent).toContain("Review 1 pending approval");
    const issue = await screen.findByTestId("issue-item");
    expect(issue.textContent).toContain("Needs approval");
    expect(issue.textContent).toContain("recommended: approve_once");
  });

  it("renders the validation-failed issue", async () => {
    debugIssues.mockResolvedValue([
      { severity: "high", kind: "validation_failed", title: "Verification failed: code_syntax", detail: "Python syntax error at line 1.", suggested_action: "fix the syntax error", link: "validators", ref: "v1" },
    ] satisfies DebugIssue[]);
    renderPanel();
    expect((await screen.findByTestId("issue-item")).textContent).toContain("Verification failed");
  });

  it("renders the quarantined-agent issue", async () => {
    debugIssues.mockResolvedValue([
      { severity: "high", kind: "agent_restricted", title: "Agent restricted: Researcher", detail: "repeated risk", suggested_action: "inspect, then unquarantine if safe", link: "agents", ref: "a2" },
    ] satisfies DebugIssue[]);
    renderPanel();
    expect((await screen.findByTestId("issue-item")).textContent).toContain("Agent restricted");
  });

  it("renders the blocked-action issue", async () => {
    debugIssues.mockResolvedValue([
      { severity: "medium", kind: "action_blocked", title: "Action blocked: the target path escapes", detail: "matched rule: Block path escapes", suggested_action: null, link: "enforcement", ref: "dec-1" },
    ] satisfies DebugIssue[]);
    renderPanel();
    expect((await screen.findByTestId("issue-item")).textContent).toContain("Action blocked");
  });

  it("shows advanced diagnostics and the project map on demand", async () => {
    debugProjectMap.mockResolvedValue({
      nodes: [
        { id: "goal", type: "goal", label: "Build a site", status: null, sublabel: null },
        { id: "wf1", type: "workflow", label: "Build a site", status: "running", sublabel: null },
        { id: "a1", type: "agent", label: "Planner", status: "ready", sublabel: "Planner" },
      ],
      edges: [{ from: "goal", to: "wf1", label: "drives" }],
    } satisfies DebugMap);
    renderPanel();
    await screen.findByTestId("project-health");
    expect(screen.queryByTestId("advanced-diagnostics")).toBeNull();
    fireEvent.click(screen.getByText("Advanced diagnostics"));
    expect(await screen.findByTestId("advanced-diagnostics")).toBeTruthy();
    expect((await screen.findByTestId("project-map")).textContent).toContain("Build a site");
    await waitFor(() => expect(debugProjectMap).toHaveBeenCalledWith("ws-abc123"));
  });

  it("renders advanced agent/workflow/validation sections", async () => {
    renderPanel();
    await screen.findByTestId("project-health");
    fireEvent.click(screen.getByText("Advanced diagnostics"));
    const adv = await screen.findByTestId("advanced-diagnostics");
    expect(adv.textContent).toContain("Planner");
    expect(adv.textContent).toContain("2 completed");
    expect(adv.textContent).toContain("code_syntax");
  });

  it("links to the activity run and replay", async () => {
    renderPanel();
    await screen.findByTestId("project-health");
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/runs/ws-abc123-activity");
    expect(hrefs).toContain("/runs/ws-abc123-activity/replay");
  });
});
