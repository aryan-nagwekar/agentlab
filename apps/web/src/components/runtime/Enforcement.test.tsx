// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  EnforcementDecisionRecord,
  RuntimeActionProposal,
  RuntimePolicyRule,
} from "../../lib/types";

const policies: RuntimePolicyRule[] = [
  {
    id: "block-path-escape",
    name: "Block path escapes",
    description: "…",
    enabled: true,
    priority: 20,
    action_types: ["*"],
    decision: "block",
    reason: "the target path escapes the workspace sandbox",
  },
];

function record(overrides: Partial<EnforcementDecisionRecord>): EnforcementDecisionRecord {
  return {
    decision_id: "dec-1",
    action_id: "act-1",
    decision: "allow",
    matched_rules: [{ id: "allow-file-write", name: "Allow safe sandbox writes" }],
    trust_score_before: null,
    risk_score_before: null,
    reason: "a normal workspace file change inside the sandbox",
    evidence: {},
    created_at: "2026-06-12T10:00:00Z",
    action_type: "file.write",
    actor_type: "user",
    target: "src/app.py",
    action_status: "completed",
    ...overrides,
  };
}

const enforcementDecisions = vi.fn();
const runtimePolicies = vi.fn();
const proposeAction = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    enforcementDecisions: (...a: unknown[]) => enforcementDecisions(...a),
    runtimePolicies: (...a: unknown[]) => runtimePolicies(...a),
    proposeAction: (...a: unknown[]) => proposeAction(...a),
  },
}));

import { EnforcementPanel } from "./EnforcementPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <EnforcementPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  enforcementDecisions.mockResolvedValue([
    record({}),
    record({
      decision_id: "dec-2",
      decision: "block",
      matched_rules: [{ id: "block-path-escape", name: "Block path escapes" }],
      reason: "the target path escapes the workspace sandbox",
      action_type: "file.write",
      target: "../escape.txt",
      action_status: "blocked",
    }),
    record({
      decision_id: "dec-3",
      decision: "require_human_approval",
      matched_rules: [{ id: "approval-sensitive-file", name: "Sensitive file changes need approval" }],
      reason: "the file touches auth/payment/deployment-sensitive paths and needs human approval",
      target: "src/payment/checkout.ts",
      action_status: "approval_required",
    }),
  ]);
  runtimePolicies.mockResolvedValue(policies);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("EnforcementPanel", () => {
  it("renders the policy summary and decision list", async () => {
    renderPanel();
    expect(
      await screen.findByText("1 deterministic policies · decided before execution"),
    ).toBeTruthy();
    const cards = screen.getAllByTestId("decision-card");
    expect(cards).toHaveLength(3);
    expect(cards[0].textContent).toContain("allowed");
    expect(cards[0].textContent).toContain("file.write");
  });

  it("renders the empty state when there are no decisions", async () => {
    enforcementDecisions.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByTestId("enforcement-empty")).toBeTruthy();
  });

  it("renders matched rules as chips", async () => {
    renderPanel();
    const rules = await screen.findAllByTestId("matched-rule");
    expect(rules.map((r) => r.textContent)).toContain("block-path-escape");
    expect(rules.map((r) => r.textContent)).toContain("approval-sensitive-file");
  });

  it("renders the blocked decision reason", async () => {
    renderPanel();
    const cards = await screen.findAllByTestId("decision-card");
    const blocked = cards.find((c) => c.textContent?.includes("blocked"))!;
    expect(blocked.textContent).toContain("the target path escapes the workspace sandbox");
    expect(blocked.textContent).toContain("../escape.txt");
  });

  it("renders the approval-required badge", async () => {
    renderPanel();
    const cards = await screen.findAllByTestId("decision-card");
    const approval = cards.find((c) => c.textContent?.includes("approval required"))!;
    expect(approval.textContent).toContain("src/payment/checkout.ts");
    expect(approval.textContent).toContain("needs human approval");
  });

  it("runs a test proposal and shows the resulting decision", async () => {
    proposeAction.mockResolvedValue({
      action_id: "act-9",
      status: "approval_required",
      decision: {
        decision_id: "dec-9",
        action_id: "act-9",
        decision: "require_human_approval",
        matched_rules: [{ id: "approval-protected-action", name: "Protected domains need approval" }],
        trust_score_before: null,
        risk_score_before: null,
        reason: "this action touches a protected domain and needs human approval",
        evidence: {},
        created_at: "2026-06-12T10:01:00Z",
      },
    } as unknown as RuntimeActionProposal);
    renderPanel();
    fireEvent.change((await screen.findAllByRole("combobox"))[0], {
      target: { value: "payment.modify" },
    });
    fireEvent.click(screen.getByText("Propose (never executes)"));
    await waitFor(() =>
      expect(proposeAction).toHaveBeenCalledWith("ws-abc123", {
        action_type: "payment.modify",
        target: "",
      }),
    );
    const result = await screen.findByTestId("test-decision");
    expect(result.textContent).toContain("approval required");
  });

  it("disables the test proposal in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const button = (await screen.findByText("Propose (never executes)")) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("Switch to Agent Mode to perform this action.");
  });

  it("hides the test proposal for read-only workspaces", async () => {
    renderPanel({ readOnly: true });
    await screen.findAllByTestId("decision-card");
    expect(screen.queryByText("Propose (never executes)")).toBeNull();
  });
});
