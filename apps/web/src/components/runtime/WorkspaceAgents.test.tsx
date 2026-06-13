// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceAgent, WorkspaceAgentTemplate } from "../../lib/types";

const agent: WorkspaceAgent = {
  agent_id: "wsagent-1",
  workspace_id: "ws-abc123",
  name: "Backend Coder",
  role: "backend",
  description: "Builds APIs and schemas.",
  system_prompt: "You are the Backend Coder.",
  model_provider: "mock",
  model_name: "mock:claude-sonnet",
  allowed_tools: [],
  denied_tools: [],
  permissions: {
    can_read_files: true,
    can_write_files: true,
    can_delete_files: false,
    can_run_commands: false,
    can_call_web: false,
    can_access_database: true,
    can_modify_auth: false,
    can_modify_payment: false,
    can_modify_deployment: false,
    can_send_to_agents: true,
    can_send_to_user: true,
    can_save_product_data: false,
    can_use_unverified_research: false,
  },
  max_tokens_per_call: 2048,
  max_calls_per_run: 25,
  max_tool_calls_per_run: 25,
  requires_verification: true,
  trust_score: 1,
  risk_score: 0.4,
  status: "caution",
  quarantine: null,
  metadata: { risk_notes: ["Touches database and server logic."] },
  created_at: "2026-06-12T10:00:00Z",
  updated_at: "2026-06-12T10:00:00Z",
};

const template: WorkspaceAgentTemplate = {
  template_id: "planner",
  name: "Planner Agent",
  role: "planner",
  description: "Breaks a goal into a task plan.",
  system_prompt: "You are the Planner.",
  model_provider: "mock",
  model_name: "mock:claude-sonnet",
  permissions: {
    can_read_files: true,
    can_write_files: false,
    can_delete_files: false,
    can_run_commands: false,
    can_call_web: false,
    can_access_database: false,
    can_modify_auth: false,
    can_modify_payment: false,
    can_modify_deployment: false,
    can_send_to_agents: true,
    can_send_to_user: true,
    can_save_product_data: false,
    can_use_unverified_research: false,
  },
  allowed_tools: [],
  denied_tools: [],
  max_tokens_per_call: 2048,
  max_calls_per_run: 25,
  max_tool_calls_per_run: 25,
  requires_verification: false,
  trust_score: 1,
  risk_score: 0,
  status: "ready",
  risk_notes: ["Cannot write files or run commands."],
  future_approval_required: [],
};

const workspaceAgents = vi.fn();
const workspaceAgentTemplates = vi.fn();
const createWorkspaceAgentFromTemplate = vi.fn();
const patchWorkspaceAgent = vi.fn();
const deleteWorkspaceAgent = vi.fn();
const quarantineAgent = vi.fn();
const unquarantineAgent = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    workspaceAgents: (...a: unknown[]) => workspaceAgents(...a),
    workspaceAgentTemplates: (...a: unknown[]) => workspaceAgentTemplates(...a),
    createWorkspaceAgentFromTemplate: (...a: unknown[]) =>
      createWorkspaceAgentFromTemplate(...a),
    patchWorkspaceAgent: (...a: unknown[]) => patchWorkspaceAgent(...a),
    deleteWorkspaceAgent: (...a: unknown[]) => deleteWorkspaceAgent(...a),
    quarantineAgent: (...a: unknown[]) => quarantineAgent(...a),
    unquarantineAgent: (...a: unknown[]) => unquarantineAgent(...a),
  },
}));

const quarantinedAgent: WorkspaceAgent = {
  ...agent,
  agent_id: "wsagent-q",
  name: "Risky Agent",
  status: "quarantined",
  quarantine: {
    reason: "repeated high-risk violations",
    requested_by: "admin",
    quarantined_at: "2026-06-12T10:00:00Z",
    source_action_id: null,
    source_approval_id: null,
    policy_rules: [],
    previous_status: "ready",
    lifted_at: null,
    lifted_by: null,
    lift_reason: null,
  },
};

import { WorkspaceAgentsPanel } from "./WorkspaceAgentsPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <WorkspaceAgentsPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  workspaceAgents.mockResolvedValue([]);
  workspaceAgentTemplates.mockResolvedValue([template]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkspaceAgentsPanel", () => {
  it("renders the empty state when there are no agents", async () => {
    renderPanel();
    expect(await screen.findByTestId("agents-empty")).toBeTruthy();
  });

  it("renders an agent card with role, status, model, and permission badges", async () => {
    workspaceAgents.mockResolvedValue([agent]);
    renderPanel();
    const card = await screen.findByTestId("agent-card");
    const scoped = within(card);
    expect(scoped.getByText("Backend Coder")).toBeTruthy();
    expect(scoped.getByText("backend")).toBeTruthy();
    expect(scoped.getByText("caution")).toBeTruthy(); // status badge
    expect(scoped.getByText("mock · mock:claude-sonnet")).toBeTruthy();
    // granted permissions render; risky ones get the risky test id
    expect(scoped.getAllByTestId("risky-permission").length).toBeGreaterThan(0);
    expect(scoped.getByTestId("risky-warning")).toBeTruthy();
  });

  it("creates an agent from a template", async () => {
    createWorkspaceAgentFromTemplate.mockResolvedValue(agent);
    renderPanel();
    fireEvent.click(await screen.findByText("+ Add agent"));
    fireEvent.click(await screen.findByText("Add"));
    await waitFor(() =>
      expect(createWorkspaceAgentFromTemplate).toHaveBeenCalledWith("ws-abc123", "planner"),
    );
  });

  it("edits agent metadata and permissions", async () => {
    workspaceAgents.mockResolvedValue([agent]);
    patchWorkspaceAgent.mockResolvedValue(agent);
    renderPanel();
    fireEvent.click(await screen.findByText("Edit"));
    fireEvent.change(screen.getByDisplayValue("Backend Coder"), {
      target: { value: "Lead Backend" },
    });
    fireEvent.click(screen.getByText("Save agent"));
    await waitFor(() => expect(patchWorkspaceAgent).toHaveBeenCalled());
    const [, agentId, body] = patchWorkspaceAgent.mock.calls[0];
    expect(agentId).toBe("wsagent-1");
    expect((body as { name: string }).name).toBe("Lead Backend");
    expect((body as { permissions: unknown }).permissions).toBeTruthy();
  });

  it("disables mutating actions in Chat Mode", async () => {
    workspaceAgents.mockResolvedValue([agent]);
    renderPanel({ chatMode: true });
    const add = (await screen.findByText("+ Add agent")) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    expect(add.title).toBe("Switch to Agent Mode to perform this action.");
    const edit = screen.getByText("Edit") as HTMLButtonElement;
    expect(edit.disabled).toBe(true);
    const del = screen.getByText("Delete") as HTMLButtonElement;
    expect(del.disabled).toBe(true);
  });

  it("hides mutating controls when the workspace is read-only", async () => {
    workspaceAgents.mockResolvedValue([agent]);
    renderPanel({ readOnly: true });
    await screen.findByTestId("agent-card");
    expect(screen.queryByText("+ Add agent")).toBeNull();
    expect(screen.queryByText("Edit")).toBeNull();
  });

  // ---- v1.7 real runtime quarantine ----

  it("quarantines an agent from its card", async () => {
    workspaceAgents.mockResolvedValue([agent]);
    quarantineAgent.mockResolvedValue({ ...agent, status: "quarantined" });
    renderPanel();
    fireEvent.click(await screen.findByTestId("quarantine-btn"));
    await waitFor(() =>
      expect(quarantineAgent).toHaveBeenCalledWith("ws-abc123", "wsagent-1", {
        reason: "manually quarantined from the agents panel",
      }),
    );
  });

  it("renders the quarantined state with reason and an unquarantine button", async () => {
    workspaceAgents.mockResolvedValue([quarantinedAgent]);
    renderPanel();
    const note = await screen.findByTestId("quarantine-note");
    expect(note.textContent).toContain("Quarantined");
    expect(note.textContent).toContain("runtime actions");
    expect(note.textContent).toContain("repeated high-risk violations");
    expect(screen.getByTestId("unquarantine-btn")).toBeTruthy();
    expect(screen.queryByTestId("quarantine-btn")).toBeNull();
  });

  it("unquarantines an agent from its card", async () => {
    workspaceAgents.mockResolvedValue([quarantinedAgent]);
    unquarantineAgent.mockResolvedValue({ ...quarantinedAgent, status: "ready" });
    renderPanel();
    fireEvent.click(await screen.findByTestId("unquarantine-btn"));
    await waitFor(() =>
      expect(unquarantineAgent).toHaveBeenCalledWith("ws-abc123", "wsagent-q", {}),
    );
  });

  it("disables quarantine actions in Chat Mode", async () => {
    workspaceAgents.mockResolvedValue([agent]);
    renderPanel({ chatMode: true });
    const btn = (await screen.findByTestId("quarantine-btn")) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toBe("Switch to Agent Mode to perform this action.");
  });
});
