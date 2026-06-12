// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioWorkflowSummary } from "../lib/types";

const workflows: StudioWorkflowSummary[] = [
  {
    workflow_id: "workflow-seeded01",
    project_id: "demo-project",
    name: "Code Review Agent Team",
    description: "Plan → code → security-review → report.",
    agent_count: 4,
    edge_count: 3,
    updated_at: "2026-06-12T10:00:00Z",
    last_run_id: "run-abc",
    last_run_status: "completed",
  },
];

const createStudioWorkflow = vi.fn();
vi.mock("../lib/api", () => ({
  api: {
    studioWorkflows: () => Promise.resolve(workflows),
    createStudioWorkflow: (...args: unknown[]) => createStudioWorkflow(...args),
  },
}));

import { StudioPage } from "./Studio";

afterEach(() => {
  cleanup();
  createStudioWorkflow.mockReset();
});

describe("StudioPage", () => {
  it("renders the workflow list with the seeded workflow", async () => {
    render(
      <MemoryRouter>
        <StudioPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Code Review Agent Team")).toBeTruthy();
    expect(screen.getByText("Agent Builder Studio")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy(); // agent count
    expect(screen.getByText("last run completed")).toBeTruthy();
    const link = screen.getByText("Code Review Agent Team").closest("a")!;
    expect(link.getAttribute("href")).toBe("/studio/workflows/workflow-seeded01");
  });

  it("creates a new workflow from the header action", async () => {
    createStudioWorkflow.mockResolvedValue({ workflow_id: "workflow-new" });
    render(
      <MemoryRouter>
        <StudioPage />
      </MemoryRouter>,
    );
    const button = await screen.findByText("+ New Workflow");
    button.click();
    await waitFor(() => expect(createStudioWorkflow).toHaveBeenCalledTimes(1));
    const body = createStudioWorkflow.mock.calls[0][0] as { agents: { provider: string }[] };
    expect(body.agents[0].provider).toBe("mock"); // new workflows never need keys
  });
});
