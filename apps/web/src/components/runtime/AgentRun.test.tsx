// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentRunResult, WorkspaceAgent } from "../../lib/types";

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

function result(overrides: Partial<AgentRunResult> = {}): AgentRunResult {
  return {
    status: "completed",
    agent_id: "wsagent-1",
    agent_name: "Builder",
    provider: "ollama",
    model: "llama3.2",
    goal: "Build a small site.",
    stop_reason: "done",
    step_count: 2,
    total_written: 2,
    total_held: 0,
    total_blocked: 0,
    commands_run: 1,
    steps: [
      {
        step: 0,
        summary: "Scaffold the page",
        status: "ok",
        done: false,
        files: [{ path: "index.html", status: "written", reason: null }],
        commands: [{ command: "python3 --version", status: "completed", exit_code: 0 }],
        validations: [
          { validator: "secret_exposure", target: "index.html", passed: true },
          { validator: "command_result", target: "command_run", passed: true },
        ],
      },
      {
        step: 1,
        summary: "Add styles and finish",
        status: "ok",
        done: true,
        files: [{ path: "styles.css", status: "written", reason: null }],
        commands: [],
        validations: [],
      },
    ],
    ...overrides,
  };
}

const workspaceAgents = vi.fn();
const agentRun = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    workspaceAgents: (...a: unknown[]) => workspaceAgents(...a),
    agentRun: (...a: unknown[]) => agentRun(...a),
  },
}));

import { AgentRunPanel } from "./AgentRunPanel";

function renderPanel(
  props: Partial<{ readOnly: boolean; chatMode: boolean; goal: string | null }> = {},
) {
  return render(
    <AgentRunPanel
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

describe("AgentRunPanel", () => {
  it("renders the loop form with the agent and a max-steps control", async () => {
    renderPanel();
    expect(await screen.findByText("live · governed · bounded loop")).toBeTruthy();
    expect(screen.getByText(/Builder · ollama\/llama3.2/)).toBeTruthy();
    expect(screen.getByLabelText("Max steps")).toBeTruthy();
    expect(screen.getByText("Run agent loop")).toBeTruthy();
  });

  it("shows the empty state when there are no assignable agents", async () => {
    workspaceAgents.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByTestId("run-no-agents")).toBeTruthy();
  });

  it("excludes quarantined/disabled agents", async () => {
    workspaceAgents.mockResolvedValue([
      agent({ status: "quarantined" }),
      agent({ agent_id: "wsagent-2", name: "Off", status: "disabled" }),
    ]);
    renderPanel();
    expect(await screen.findByTestId("run-no-agents")).toBeTruthy();
  });

  it("runs the loop and renders each step's files, commands, and validations", async () => {
    agentRun.mockResolvedValue(result());
    renderPanel();
    fireEvent.click(await screen.findByText("Run agent loop"));
    await waitFor(() =>
      expect(agentRun).toHaveBeenCalledWith("ws-abc123", {
        agent_id: "wsagent-1",
        prompt: undefined,
        max_steps: 6,
      }),
    );
    const card = await screen.findByTestId("run-result");
    expect(card.textContent).toContain("2 steps");
    expect(card.textContent).toContain("1 command");
    const steps = screen.getAllByTestId("run-step");
    expect(steps).toHaveLength(2);
    expect(screen.getAllByTestId("run-file")[0].textContent).toContain("index.html");
    expect(screen.getByTestId("run-command").textContent).toContain("python3 --version");
    expect(screen.getAllByTestId("run-validations")[0].textContent).toContain("command_result");
    expect(screen.getByTestId("run-stop-reason").textContent).toContain("goal complete");
  });

  it("sends a custom prompt and max steps", async () => {
    agentRun.mockResolvedValue(result());
    renderPanel();
    fireEvent.change(await screen.findByLabelText("Max steps"), { target: { value: "3" } });
    fireEvent.change(screen.getByPlaceholderText("Build a small site."), {
      target: { value: "Build a landing page" },
    });
    fireEvent.click(screen.getByText("Run agent loop"));
    await waitFor(() =>
      expect(agentRun).toHaveBeenCalledWith("ws-abc123", {
        agent_id: "wsagent-1",
        prompt: "Build a landing page",
        max_steps: 3,
      }),
    );
  });

  it("explains a halted-for-approval stop", async () => {
    agentRun.mockResolvedValue(
      result({
        stop_reason: "halted_for_approval",
        step_count: 1,
        total_held: 1,
        steps: [
          {
            step: 0,
            summary: "Touched payment code",
            status: "ok",
            done: false,
            files: [
              { path: "index.html", status: "written", reason: null },
              { path: "src/payment/pay.js", status: "halted_for_approval", reason: "needs approval" },
            ],
            commands: [],
            validations: [],
          },
        ],
      }),
    );
    renderPanel();
    fireEvent.click(await screen.findByText("Run agent loop"));
    const card = await screen.findByTestId("run-result");
    expect(card.textContent).toContain("needs your approval");
    expect(card.textContent).toContain("need approval — resolve them in the Approvals panel");
  });

  it("disables running in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const button = (await screen.findByText("Run agent loop")) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("Switch to Agent Mode to perform this action.");
  });

  it("hides the form for read-only workspaces", async () => {
    renderPanel({ readOnly: true });
    await screen.findByText("live · governed · bounded loop");
    expect(screen.queryByText("Run agent loop")).toBeNull();
  });
});
