// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store/app";

const configureProvider = vi.fn();
const runStudioWorkflow = vi.fn();
const studioWorkflowRuns = vi.fn();
const runCosts = vi.fn();
const testCall = vi.fn();
const clearProvider = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    configureProvider: (...args: unknown[]) => configureProvider(...args),
    clearProvider: (...args: unknown[]) => clearProvider(...args),
    runStudioWorkflow: (...args: unknown[]) => runStudioWorkflow(...args),
    studioWorkflowRuns: (...args: unknown[]) => studioWorkflowRuns(...args),
    runCosts: (...args: unknown[]) => runCosts(...args),
    runEvents: () => Promise.resolve([]),
    runRiskSummary: () => Promise.resolve({}),
    testCall: (...args: unknown[]) => testCall(...args),
  },
}));

import { AssistantPanel } from "./AssistantPanel";

const FAKE_KEY = "AIzaSyFakeKeyValue1234567890";

function sendMessage(text: string) {
  fireEvent.change(screen.getByLabelText("Assistant message"), { target: { value: text } });
  fireEvent.click(screen.getByText("Send"));
}

beforeEach(() => {
  useAppStore.setState({ studioMode: "agent" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AssistantPanel modes", () => {
  it("renders both modes and switching works", () => {
    render(<AssistantPanel workflowName="Team" />);
    expect(screen.getByRole("tab", { name: "Chat Mode" })).toBeTruthy();
    const agentTab = screen.getByRole("tab", { name: "Agent Mode" });
    expect(agentTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText(/Agent Mode —/)).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Chat Mode" }));
    expect(screen.getByRole("tab", { name: "Chat Mode" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(screen.getByText(/Chat Mode —/)).toBeTruthy();
  });

  it("Chat Mode blocks action requests with the exact switch message", async () => {
    useAppStore.setState({ studioMode: "chat" });
    render(<AssistantPanel workflowName="Team" />);
    sendMessage("run the workflow now");
    await waitFor(() =>
      expect(screen.getByText("Switch to Agent Mode to perform this action.")).toBeTruthy(),
    );
    expect(runStudioWorkflow).not.toHaveBeenCalled();
  });

  it("Chat Mode blocks slash commands too", async () => {
    useAppStore.setState({ studioMode: "chat" });
    render(<AssistantPanel />);
    sendMessage("/connect gemini");
    await waitFor(() =>
      expect(screen.getByText("Switch to Agent Mode to perform this action.")).toBeTruthy(),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("Chat Mode answers cost questions from run data", async () => {
    useAppStore.setState({ studioMode: "chat" });
    studioWorkflowRuns.mockResolvedValue([{ run_id: "run-1", status: "completed" }]);
    runCosts.mockResolvedValue({
      total_tokens: 1898,
      estimated_cost_usd: 0.0123,
      most_expensive_agent: "planner",
      most_token_heavy_agent: "coder",
    });
    render(<AssistantPanel workflowId="workflow-1" />);
    sendMessage("what did the last run cost?");
    await waitFor(() => expect(screen.getByText(/1898 tokens/)).toBeTruthy());
    expect(screen.getByText(/Most expensive agent: planner/)).toBeTruthy();
  });
});

describe("/connect provider flow", () => {
  it("/connect gemini in Agent Mode opens the secure modal", async () => {
    render(<AssistantPanel />);
    sendMessage("/connect gemini");
    const dialog = await screen.findByRole("dialog", { name: "Configure Gemini" });
    expect(dialog).toBeTruthy();
    expect(screen.getByText(/Never paste API keys into chat\. Use this secure setup field\./)).toBeTruthy();
    const keyInput = screen.getByPlaceholderText("paste your API key");
    expect(keyInput.getAttribute("type")).toBe("password");
  });

  it("saving shows only the redacted key, never the raw one", async () => {
    configureProvider.mockResolvedValue({
      name: "gemini",
      status: "available",
      configured: true,
      detail: "Configured.",
      key_redacted: "AIz...7890",
    });
    render(<AssistantPanel />);
    sendMessage("/connect gemini");
    const keyInput = await screen.findByPlaceholderText("paste your API key");
    fireEvent.change(keyInput, { target: { value: FAKE_KEY } });
    fireEvent.click(screen.getByText("Save locally"));
    await waitFor(() => expect(screen.getByText(/configured: AIz\.\.\.7890/)).toBeTruthy());
    expect(configureProvider).toHaveBeenCalledWith("gemini", { api_key: FAKE_KEY });
    // the raw key is gone from the document (input cleared, never rendered)
    expect(document.body.innerHTML).not.toContain(FAKE_KEY);
  });

  it("unknown provider gets a helpful reply, no modal", async () => {
    render(<AssistantPanel />);
    sendMessage("/connect ghost");
    await waitFor(() => expect(screen.getByText(/Unknown provider ghost/)).toBeTruthy());
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("API-key paste guard", () => {
  it("blocks key-like text in chat with a warning, in both modes", async () => {
    render(<AssistantPanel />);
    sendMessage(`here is my key ${FAKE_KEY}`);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "This looks like an API key. For safety, use Settings → Model Gateway or /connect provider in Agent Mode.",
    );
    // the message was not sent: transcript stays empty and no api call happened
    expect(screen.getByTestId("assistant-transcript").textContent).not.toContain(FAKE_KEY);
    expect(configureProvider).not.toHaveBeenCalled();

    useAppStore.setState({ studioMode: "chat" });
    sendMessage(`sk-abcdef1234567890xyz please use this`);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByTestId("assistant-transcript").textContent).not.toContain("sk-abcdef");
  });
});

describe("Agent Mode actions", () => {
  it("/run executes the workflow and reports the run", async () => {
    runStudioWorkflow.mockResolvedValue({
      workflow_id: "workflow-1",
      run_id: "run-77",
      status: "completed",
      open_run_url: "/runs/run-77",
    });
    render(<AssistantPanel workflowId="workflow-1" />);
    sendMessage("/run");
    await waitFor(() => expect(screen.getByText(/Run completed: run-77/)).toBeTruthy());
    expect(runStudioWorkflow).toHaveBeenCalledTimes(1);
  });
});
