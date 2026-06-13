// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RuntimeApproval } from "../../lib/types";

function approval(overrides: Partial<RuntimeApproval> = {}): RuntimeApproval {
  return {
    approval_id: "apr-1",
    workspace_id: "ws-abc123",
    workflow_id: null,
    task_id: null,
    action_id: "act-1",
    agent_id: null,
    title: "file.write: src/payment/checkout.ts",
    plain_english_summary:
      "AgentLab paused this action because the file touches auth/payment/deployment-sensitive paths.",
    technical_summary: "action_type=file.write target=src/payment/checkout.ts",
    risk_level: "high",
    matched_policy_rules: [
      { id: "approval-sensitive-file", name: "Sensitive file changes need approval" },
    ],
    recommended_decision: "approve_once",
    options: ["approve", "approve_once", "approve_readonly", "deny", "reroute", "quarantine"],
    status: "pending",
    action_type: "file.write",
    target: "src/payment/checkout.ts",
    resolution_decision: null,
    resolved_at: null,
    resolved_by: null,
    resolution_reason: null,
    execution_status: "not_executed",
    execution_detail: null,
    created_at: "2026-06-12T10:00:00Z",
    ...overrides,
  };
}

const workspaceApprovals = vi.fn();
const resolveApproval = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    workspaceApprovals: (...a: unknown[]) => workspaceApprovals(...a),
    resolveApproval: (...a: unknown[]) => resolveApproval(...a),
  },
}));

import { ApprovalsPanel } from "./ApprovalsPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <ApprovalsPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  workspaceApprovals.mockResolvedValue([approval()]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ApprovalsPanel", () => {
  it("renders the pending count and an approval card", async () => {
    renderPanel();
    expect((await screen.findByTestId("pending-count")).textContent).toBe("1 pending");
    const card = screen.getByTestId("approval-card");
    expect(card.textContent).toContain("file.write");
    expect(card.textContent).toContain("src/payment/checkout.ts");
    expect(card.textContent).toContain("risk high");
  });

  it("renders the empty state", async () => {
    workspaceApprovals.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByTestId("approvals-empty")).toBeTruthy();
    expect(screen.getByTestId("pending-count").textContent).toBe("0 pending");
  });

  it("renders the plain-English summary and matched rules", async () => {
    renderPanel();
    await screen.findByTestId("approval-card");
    expect(screen.getByText(/AgentLab paused this action/)).toBeTruthy();
    const rules = screen.getAllByTestId("approval-rule");
    expect(rules.map((r) => r.textContent)).toContain("approval-sensitive-file");
  });

  it("expands technical details", async () => {
    renderPanel();
    fireEvent.click(await screen.findByText("Technical details"));
    expect(screen.getByText(/action_type=file.write/)).toBeTruthy();
  });

  it("renders approve / deny / reroute / quarantine options", async () => {
    renderPanel();
    await screen.findByTestId("approval-card");
    for (const label of ["Approve", "Deny", "Approve read-only", "Reroute", "Quarantine"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("runs the approve flow", async () => {
    resolveApproval.mockResolvedValue(approval({ status: "approved" }));
    renderPanel();
    fireEvent.click(await screen.findByText("Approve"));
    await waitFor(() =>
      expect(resolveApproval).toHaveBeenCalledWith("ws-abc123", "apr-1", "approve"),
    );
  });

  it("runs the deny flow", async () => {
    resolveApproval.mockResolvedValue(approval({ status: "denied" }));
    renderPanel();
    fireEvent.click(await screen.findByText("Deny"));
    await waitFor(() =>
      expect(resolveApproval).toHaveBeenCalledWith("ws-abc123", "apr-1", "deny"),
    );
  });

  it("renders the resolved status and execution outcome", async () => {
    workspaceApprovals.mockResolvedValue([
      approval({
        status: "approved",
        resolution_decision: "approve",
        resolved_by: "alice",
        execution_status: "executed",
        execution_detail: "wrote src/payment/checkout.ts (10 B)",
      }),
    ]);
    renderPanel();
    const resolution = await screen.findByTestId("approval-resolution");
    expect(resolution.textContent).toContain("approve by alice");
    expect(resolution.textContent).toContain("executed");
    expect(resolution.textContent).toContain("wrote src/payment/checkout.ts");
  });

  it("disables resolution actions in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const approve = (await screen.findByText("Approve")) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    expect(approve.title).toBe("Switch to Agent Mode to perform this action.");
  });

  it("hides resolution actions for read-only workspaces", async () => {
    renderPanel({ readOnly: true });
    await screen.findByTestId("approval-card");
    expect(screen.queryByText("Approve")).toBeNull();
    expect(screen.queryByText("Deny")).toBeNull();
  });
});
