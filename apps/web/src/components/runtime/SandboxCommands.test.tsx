// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AgentLabEvent,
  AllowedCommand,
  SandboxCommandResult,
  SandboxStatus,
} from "../../lib/types";

const initialized: SandboxStatus = {
  workspace_id: "ws-abc123",
  initialized: true,
  file_count: 1,
  directory_count: 0,
  total_bytes: 10,
};

const allowed: AllowedCommand[] = [
  { command: "ls", description: "List workspace files", examples: ["ls", "ls -la"] },
  { command: "pwd", description: "Print the working directory", examples: ["pwd"] },
];

const completedResult: SandboxCommandResult = {
  command: "ls -la",
  argv: ["ls", "-la"],
  cwd: ".",
  status: "completed",
  exit_code: 0,
  duration_ms: 12,
  stdout: "total 0\nREADME.md",
  stderr: "",
  stdout_truncated: false,
  stderr_truncated: false,
};

const historyEvents = [
  {
    event_id: "evt-cmd-1",
    event_type: "sandbox.command.completed",
    timestamp: "2026-06-12T10:00:00Z",
    project_id: "demo-project",
    run_id: "ws-abc123-activity",
    source_agent_id: null,
    target_agent_id: null,
    payload: { command: "pwd", exit_code: 0 },
    metadata: { source: "runtime", workspace_id: "ws-abc123" },
  },
] as unknown as AgentLabEvent[];

const sandboxStatus = vi.fn();
const sandboxAllowedCommands = vi.fn();
const sandboxRunCommand = vi.fn();
const sandboxCommandHistory = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    sandboxStatus: (...a: unknown[]) => sandboxStatus(...a),
    sandboxAllowedCommands: (...a: unknown[]) => sandboxAllowedCommands(...a),
    sandboxRunCommand: (...a: unknown[]) => sandboxRunCommand(...a),
    sandboxCommandHistory: (...a: unknown[]) => sandboxCommandHistory(...a),
  },
}));

import { SandboxCommandsPanel } from "./SandboxCommandsPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <SandboxCommandsPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  sandboxStatus.mockResolvedValue(initialized);
  sandboxAllowedCommands.mockResolvedValue(allowed);
  sandboxCommandHistory.mockResolvedValue(historyEvents);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SandboxCommandsPanel", () => {
  it("renders the panel with the sandbox-only badge", async () => {
    renderPanel();
    expect(await screen.findByText("allowlisted · sandbox-only · no shell")).toBeTruthy();
    expect(screen.getByPlaceholderText("ls -la")).toBeTruthy();
  });

  it("shows the uninitialized hint when there is no sandbox", async () => {
    sandboxStatus.mockResolvedValue({ ...initialized, initialized: false });
    renderPanel();
    expect(await screen.findByTestId("commands-uninitialized")).toBeTruthy();
  });

  it("shows the allowed-commands help", async () => {
    renderPanel();
    fireEvent.click(await screen.findByText("Show allowed commands"));
    const help = await screen.findByTestId("allowed-commands");
    expect(help.textContent).toContain("List workspace files");
    expect(help.textContent).toContain("pwd");
  });

  it("runs an allowed command and renders the output", async () => {
    sandboxRunCommand.mockResolvedValue(completedResult);
    renderPanel();
    fireEvent.change(await screen.findByPlaceholderText("ls -la"), {
      target: { value: "ls -la" },
    });
    fireEvent.click(screen.getByText("Run"));
    await waitFor(() =>
      expect(sandboxRunCommand).toHaveBeenCalledWith("ws-abc123", {
        command: "ls",
        args: ["-la"],
        working_subdir: "",
      }),
    );
    const outcome = await screen.findByTestId("command-outcome");
    expect(outcome.textContent).toContain("completed");
    expect(outcome.textContent).toContain("exit 0");
    expect(outcome.textContent).toContain("README.md");
  });

  it("renders the blocked reason when a command is rejected", async () => {
    sandboxRunCommand.mockRejectedValue(
      new Error(
        "400 Bad Request — blocked (dangerous_command): 'rm' is a blocked command class in the sandbox",
      ),
    );
    renderPanel();
    fireEvent.change(await screen.findByPlaceholderText("ls -la"), {
      target: { value: "rm -rf /" },
    });
    fireEvent.click(screen.getByText("Run"));
    const reason = await screen.findByTestId("blocked-reason");
    expect(reason.textContent).toContain("blocked (dangerous_command)");
    expect(reason.textContent).toContain("not executed");
  });

  it("renders a timed-out result", async () => {
    sandboxRunCommand.mockResolvedValue({
      ...completedResult,
      status: "timed_out",
      exit_code: null,
      stdout: "",
      stderr: "command exceeded the 1s timeout and was terminated",
    });
    renderPanel();
    fireEvent.change(await screen.findByPlaceholderText("ls -la"), {
      target: { value: "npm test" },
    });
    fireEvent.click(screen.getByText("Run"));
    const outcome = await screen.findByTestId("command-outcome");
    expect(outcome.textContent).toContain("timed out");
    expect(outcome.textContent).toContain("exceeded the 1s timeout");
  });

  it("renders the command history from events", async () => {
    renderPanel();
    const rows = await screen.findAllByTestId("command-history-row");
    expect(rows[0].textContent).toContain("completed");
    expect(rows[0].textContent).toContain("pwd");
  });

  it("disables execution in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const runButton = (await screen.findByText("Run")) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
    expect(runButton.title).toBe("Switch to Agent Mode to perform this action.");
    const input = screen.getByPlaceholderText("ls -la") as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });

  it("disables execution for archived (read-only) workspaces", async () => {
    renderPanel({ readOnly: true });
    const runButton = (await screen.findByText("Run")) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
  });
});
