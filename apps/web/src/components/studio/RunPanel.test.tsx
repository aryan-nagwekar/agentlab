// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const runStudioWorkflow = vi.fn();
vi.mock("../../lib/api", () => ({
  api: { runStudioWorkflow: (...args: unknown[]) => runStudioWorkflow(...args) },
}));

import { RunPanel } from "./RunPanel";

afterEach(() => {
  cleanup();
  runStudioWorkflow.mockReset();
});

function renderPanel(overrides: Partial<Parameters<typeof RunPanel>[0]> = {}) {
  return render(
    <MemoryRouter>
      <RunPanel
        workflowId="workflow-1"
        dirty={false}
        unconfiguredProviders={[]}
        onRunComplete={vi.fn()}
        {...overrides}
      />
    </MemoryRouter>,
  );
}

describe("RunPanel", () => {
  it("runs the workflow and shows run/replay/cost links", async () => {
    runStudioWorkflow.mockResolvedValue({
      workflow_id: "workflow-1",
      run_id: "run-xyz",
      status: "completed",
      open_run_url: "/runs/run-xyz",
    });
    renderPanel();
    fireEvent.click(screen.getByText("▶ Run Workflow"));
    await waitFor(() => expect(screen.getByText("run completed")).toBeTruthy());
    expect(runStudioWorkflow).toHaveBeenCalledWith(
      "workflow-1",
      expect.objectContaining({ input: expect.stringContaining("FastAPI") }),
    );
    expect(screen.getByText("Open Run Detail").closest("a")!.getAttribute("href")).toBe(
      "/runs/run-xyz",
    );
    expect(screen.getByText("View Replay").closest("a")!.getAttribute("href")).toBe(
      "/runs/run-xyz?tab=replay",
    );
    expect(screen.getByText("View Cost & Tokens").closest("a")!.getAttribute("href")).toBe(
      "/runs/run-xyz?tab=cost",
    );
  });

  it("shows a failed run status", async () => {
    runStudioWorkflow.mockResolvedValue({
      workflow_id: "workflow-1",
      run_id: "run-bad",
      status: "failed",
      open_run_url: "/runs/run-bad",
    });
    renderPanel();
    fireEvent.click(screen.getByText("▶ Run Workflow"));
    await waitFor(() => expect(screen.getByText("run failed")).toBeTruthy());
  });

  it("surfaces validation errors from the API", async () => {
    runStudioWorkflow.mockRejectedValue(
      new Error("422 — Cycles are not supported in v0.8. Please use a DAG workflow."),
    );
    renderPanel();
    fireEvent.click(screen.getByText("▶ Run Workflow"));
    await waitFor(() => expect(screen.getByText(/Cycles are not supported/)).toBeTruthy());
  });

  it("warns about unconfigured providers before running", () => {
    renderPanel({ unconfiguredProviders: ["anthropic"] });
    expect(screen.getByText(/not configured/)).toBeTruthy();
    expect(screen.getByText("anthropic")).toBeTruthy();
  });

  it("notes unsaved changes when dirty", () => {
    renderPanel({ dirty: true });
    expect(screen.getByText(/Unsaved changes/)).toBeTruthy();
  });
});
