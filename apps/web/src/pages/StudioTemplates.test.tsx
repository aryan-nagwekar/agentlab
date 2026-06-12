// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioTemplate, StudioTemplateSummary } from "../lib/types";

const summaries: StudioTemplateSummary[] = [
  "Code Review Agent Team",
  "Research Agent Team",
  "Resume Tailoring Agent Team",
  "SOC Investigation Agent Team",
  "Customer Support Agent Team",
  "Data Analysis Agent Team",
].map((name, i) => ({
  template_id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
  name,
  description: `${name} description`,
  category: ["engineering", "research", "careers", "security", "support", "analytics"][i],
  tags: ["tag-a", `tag-${i}`],
  difficulty: "beginner",
  use_case: `Good for: ${name} things.`,
  agent_count: 5,
}));

const template: StudioTemplate = {
  ...summaries[0],
  default_input: "Build a simple FastAPI endpoint that accepts a username.",
  agents: [
    {
      agent_id: "planner-agent",
      name: "Planner Agent",
      role: "planner",
      description: "Breaks the request into a plan.",
      system_prompt: "Break the request into a short plan.",
      provider: "mock",
      model_name: "mock:claude-sonnet",
      temperature: 0.2,
      max_tokens: 1000,
      position_x: 0,
      position_y: 0,
    },
    {
      agent_id: "coder-agent",
      name: "Coder Agent",
      role: "coder",
      description: "Implements the plan.",
      system_prompt: "Implement the plan.",
      provider: "mock",
      model_name: "mock:gpt-4.1",
      temperature: 0.2,
      max_tokens: 1000,
      position_x: 250,
      position_y: 110,
    },
  ],
  edges: [
    {
      source_agent_name: "Planner Agent",
      target_agent_name: "Coder Agent",
      source_agent_id: "planner-agent",
      target_agent_id: "coder-agent",
      label: "plan",
    },
  ],
  expected_outputs: ["A plan", "Code"],
  demo_notes: "Run it and open Replay.",
};

const createWorkflowFromTemplate = vi.fn();
vi.mock("../lib/api", () => ({
  api: {
    studioTemplates: () => Promise.resolve(summaries),
    studioTemplate: () => Promise.resolve(template),
    providers: () => Promise.resolve({ providers: [] }),
    createWorkflowFromTemplate: (...args: unknown[]) => createWorkflowFromTemplate(...args),
  },
}));

// The canvas is React Flow — exercised in the live browser, stubbed in jsdom.
vi.mock("../components/studio/StudioCanvas", () => ({
  StudioCanvas: ({ agents }: { agents: unknown[] }) => (
    <div data-testid="canvas-preview">canvas: {agents.length} agents</div>
  ),
}));

import { StudioTemplatePage } from "./StudioTemplate";
import { StudioTemplatesPage } from "./StudioTemplates";

afterEach(() => {
  cleanup();
  createWorkflowFromTemplate.mockReset();
});

describe("StudioTemplatesPage", () => {
  it("renders all six required template cards", async () => {
    render(
      <MemoryRouter>
        <StudioTemplatesPage />
      </MemoryRouter>,
    );
    for (const summary of summaries) {
      expect(await screen.findByText(summary.name)).toBeTruthy();
    }
    expect(screen.getByText("Start from template")).toBeTruthy();
    expect(screen.getAllByText("Create workflow").length).toBe(6);
    expect(screen.getAllByText("Preview").length).toBe(6);
    expect(screen.getAllByText(/5 agents/).length).toBe(6);
  });

  it("creates a workflow and navigates to the editor with the template param", async () => {
    createWorkflowFromTemplate.mockResolvedValue({
      workflow_id: "workflow-new",
      template_id: "code-review-agent-team",
      open_url: "/studio/workflows/workflow-new",
    });
    render(
      <MemoryRouter initialEntries={["/studio/templates"]}>
        <Routes>
          <Route path="/studio/templates" element={<StudioTemplatesPage />} />
          <Route
            path="/studio/workflows/:workflowId"
            element={<div data-testid="editor">editor opened</div>}
          />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click((await screen.findAllByText("Create workflow"))[0]);
    await waitFor(() => expect(screen.getByTestId("editor")).toBeTruthy());
    expect(createWorkflowFromTemplate).toHaveBeenCalledWith("code-review-agent-team", {});
  });
});

describe("StudioTemplatePage", () => {
  function renderPreview() {
    return render(
      <MemoryRouter initialEntries={["/studio/templates/code-review-agent-team"]}>
        <Routes>
          <Route path="/studio/templates/:templateId" element={<StudioTemplatePage />} />
          <Route
            path="/studio/workflows/:workflowId"
            element={<div data-testid="editor">editor opened</div>}
          />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("renders the agent list, graph preview, default input, and notes", async () => {
    renderPreview();
    expect(await screen.findByText("Planner Agent")).toBeTruthy();
    expect(screen.getByText("Coder Agent")).toBeTruthy();
    expect(screen.getByText("mock · mock:gpt-4.1")).toBeTruthy();
    expect(screen.getByTestId("canvas-preview").textContent).toContain("2 agents");
    expect(screen.getByText(/Build a simple FastAPI endpoint/)).toBeTruthy();
    expect(screen.getByText("· A plan")).toBeTruthy();
    expect(screen.getByText("Run it and open Replay.")).toBeTruthy();
    // raw system prompts are behind the advanced toggle
    expect(screen.queryByText("Break the request into a short plan.")).toBeNull();
    fireEvent.click(screen.getByText("▸ Show system prompts"));
    expect(screen.getByText("Break the request into a short plan.")).toBeTruthy();
  });

  it("creates a workflow with an optional custom name", async () => {
    createWorkflowFromTemplate.mockResolvedValue({
      workflow_id: "workflow-custom",
      template_id: "code-review-agent-team",
      open_url: "/studio/workflows/workflow-custom",
    });
    renderPreview();
    const nameInput = await screen.findByPlaceholderText("Code Review Agent Team");
    fireEvent.change(nameInput, { target: { value: "My Review Team" } });
    fireEvent.click(screen.getByText("Create workflow → Open in Studio"));
    await waitFor(() => expect(screen.getByTestId("editor")).toBeTruthy());
    expect(createWorkflowFromTemplate).toHaveBeenCalledWith("code-review-agent-team", {
      name: "My Review Team",
    });
  });
});
