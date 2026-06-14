// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentBuildResult, WorkspaceAgent } from "../../lib/types";

function agent(overrides: Partial<WorkspaceAgent> = {}): WorkspaceAgent {
  return {
    agent_id: "wsagent-1",
    workspace_id: "ws-abc123",
    name: "Builder",
    role: "UI Agent",
    description: null,
    system_prompt: null,
    model_provider: "ollama",
    model_name: "llama3.2",
    allowed_tools: [],
    denied_tools: [],
    permissions: {},
    max_tokens_per_call: 2048,
    max_calls_per_run: 25,
    max_tool_calls_per_run: 25,
    requires_verification: false,
    trust_score: 1,
    risk_score: 0,
    status: "ready",
    quarantine: null,
    metadata: {},
    created_at: "2026-06-14T10:00:00Z",
    updated_at: "2026-06-14T10:00:00Z",
    ...overrides,
  } as unknown as WorkspaceAgent;
}

function result(overrides: Partial<AgentBuildResult> = {}): AgentBuildResult {
  return {
    status: "completed",
    agent_id: "wsagent-1",
    agent_name: "Builder",
    provider: "ollama",
    model: "llama3.2",
    summary: "A small storefront.",
    input_tokens: 30,
    output_tokens: 200,
    latency_ms: 5400,
    files: [
      { path: "index.html", status: "written", reason: null },
      { path: "src/payment/pay.js", status: "halted_for_approval", reason: "needs approval" },
      { path: "../escape.html", status: "blocked", reason: "path traversal" },
    ],
    written: 1,
    halted_for_approval: 1,
    blocked: 1,
    ...overrides,
  };
}

const workspaceAgents = vi.fn();
const agentBuild = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    workspaceAgents: (...a: unknown[]) => workspaceAgents(...a),
    agentBuild: (...a: unknown[]) => agentBuild(...a),
  },
}));

import { AgentBuildPanel } from "./AgentBuildPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean; goal: string | null }> = {}) {
  return render(
    <AgentBuildPanel
      workspaceId="ws-abc123"
      goal={props.goal ?? "Build a small site."}
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  workspaceAgents.mockResolvedValue([agent()]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AgentBuildPanel", () => {
  it("renders the build form with the agent and its model", async () => {
    renderPanel();
    expect(await screen.findByText("live · governed · single pass")).toBeTruthy();
    expect(screen.getByText(/Builder · ollama\/llama3.2/)).toBeTruthy();
    expect(screen.getByText("Build with agent")).toBeTruthy();
  });

  it("shows the empty state when there are no assignable agents", async () => {
    workspaceAgents.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByTestId("build-no-agents")).toBeTruthy();
  });

  it("excludes quarantined/disabled agents", async () => {
    workspaceAgents.mockResolvedValue([
      agent({ status: "quarantined" }),
      agent({ agent_id: "wsagent-2", name: "Disabled One", status: "disabled" }),
    ]);
    renderPanel();
    expect(await screen.findByTestId("build-no-agents")).toBeTruthy();
  });

  it("runs the build and renders per-file governance outcomes", async () => {
    agentBuild.mockResolvedValue(result());
    renderPanel();
    fireEvent.click(await screen.findByText("Build with agent"));
    await waitFor(() =>
      expect(agentBuild).toHaveBeenCalledWith("ws-abc123", { agent_id: "wsagent-1", prompt: undefined }),
    );
    const card = await screen.findByTestId("build-result");
    expect(card.textContent).toContain("1 written");
    const files = screen.getAllByTestId("build-file");
    expect(files[0].textContent).toContain("index.html");
    expect(files[0].textContent).toContain("written");
    expect(files[1].textContent).toContain("halted for approval");
    expect(files[2].textContent).toContain("blocked");
    expect(card.textContent).toContain("need approval — resolve them in the Approvals panel");
  });

  it("passes a custom prompt when typed", async () => {
    agentBuild.mockResolvedValue(result({ files: [], written: 0, halted_for_approval: 0, blocked: 0 }));
    renderPanel();
    fireEvent.change(await screen.findByPlaceholderText("Build a small site."), {
      target: { value: "Build a landing page" },
    });
    fireEvent.click(screen.getByText("Build with agent"));
    await waitFor(() =>
      expect(agentBuild).toHaveBeenCalledWith("ws-abc123", {
        agent_id: "wsagent-1",
        prompt: "Build a landing page",
      }),
    );
  });

  it("renders a failed build", async () => {
    agentBuild.mockResolvedValue(
      result({ status: "failed", summary: "the model did not return a valid JSON file manifest", files: [], written: 0, halted_for_approval: 0, blocked: 0 }),
    );
    renderPanel();
    fireEvent.click(await screen.findByText("Build with agent"));
    const card = await screen.findByTestId("build-result");
    expect(card.textContent).toContain("failed");
    expect(card.textContent).toContain("did not return a valid JSON");
  });

  it("disables building in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const button = (await screen.findByText("Build with agent")) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("Switch to Agent Mode to perform this action.");
  });

  it("hides the form for read-only workspaces", async () => {
    renderPanel({ readOnly: true });
    await screen.findByText("live · governed · single pass");
    expect(screen.queryByText("Build with agent")).toBeNull();
  });
});
