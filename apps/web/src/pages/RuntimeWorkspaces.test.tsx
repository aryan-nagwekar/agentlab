// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentLabEvent, RuntimeArtifact, RuntimeWorkspace } from "../lib/types";
import { useAppStore } from "../store/app";

const workspace: RuntimeWorkspace = {
  workspace_id: "ws-abc123",
  name: "Storefront Project",
  goal: "Eventually build a small storefront site.",
  status: "draft",
  project_id: "demo-project",
  activity_run_id: "ws-abc123-activity",
  metadata: {},
  artifact_count: 1,
  agent_count: 0,
  created_at: "2026-06-12T10:00:00Z",
  updated_at: "2026-06-12T10:05:00Z",
};

const activity: AgentLabEvent[] = [
  {
    event_id: "evt-2",
    event_type: "workspace.updated",
    timestamp: "2026-06-12T10:05:00Z",
    project_id: "demo-project",
    run_id: "ws-abc123-activity",
    source_agent_id: null,
    target_agent_id: null,
    payload: { workspace_id: "ws-abc123", changed_fields: ["goal"] },
    metadata: { source: "runtime", workspace_id: "ws-abc123" },
  },
  {
    event_id: "evt-1",
    event_type: "workspace.created",
    timestamp: "2026-06-12T10:00:00Z",
    project_id: "demo-project",
    run_id: "ws-abc123-activity",
    source_agent_id: null,
    target_agent_id: null,
    payload: { workspace_id: "ws-abc123" },
    metadata: { source: "runtime", workspace_id: "ws-abc123" },
  },
] as unknown as AgentLabEvent[];

const artifacts: RuntimeArtifact[] = [
  {
    artifact_id: "artifact-1",
    workspace_id: "ws-abc123",
    name: "index.html",
    type: "file",
    path: "site/index.html",
    metadata: {},
    created_at: "2026-06-12T10:04:00Z",
    updated_at: "2026-06-12T10:04:00Z",
  },
];

const createRuntimeWorkspace = vi.fn();
const patchRuntimeWorkspace = vi.fn();
const archiveRuntimeWorkspace = vi.fn();
const registerRuntimeArtifact = vi.fn();
vi.mock("../lib/api", () => ({
  api: {
    runtimeWorkspaces: () => Promise.resolve([workspace]),
    runtimeWorkspace: () => Promise.resolve(workspace),
    runtimeWorkspaceActivity: () => Promise.resolve(activity),
    runtimeWorkspaceArtifacts: () => Promise.resolve(artifacts),
    createRuntimeWorkspace: (...args: unknown[]) => createRuntimeWorkspace(...args),
    patchRuntimeWorkspace: (...args: unknown[]) => patchRuntimeWorkspace(...args),
    archiveRuntimeWorkspace: (...args: unknown[]) => archiveRuntimeWorkspace(...args),
    registerRuntimeArtifact: (...args: unknown[]) => registerRuntimeArtifact(...args),
    // v1.1 agents panel — detail page renders it; default to no agents here.
    workspaceAgents: () => Promise.resolve([]),
    workspaceAgentTemplates: () => Promise.resolve([]),
    // v1.2 files panel — default to an uninitialized sandbox here.
    sandboxStatus: () =>
      Promise.resolve({
        workspace_id: "ws-abc123",
        initialized: false,
        file_count: 0,
        directory_count: 0,
        total_bytes: 0,
      }),
    sandboxTree: () => Promise.resolve([]),
    // v1.3 commands panel — uninitialized sandbox shows the hint only.
    sandboxAllowedCommands: () => Promise.resolve([]),
    sandboxCommandHistory: () => Promise.resolve([]),
    // v1.4 workflows panel — default to no workflows here.
    workspaceWorkflows: () => Promise.resolve([]),
    // v1.5 enforcement panel — default to no decisions here.
    enforcementDecisions: () => Promise.resolve([]),
    runtimePolicies: () => Promise.resolve([]),
    // v1.6 approvals panel — default to no approvals here.
    workspaceApprovals: () => Promise.resolve([]),
  },
}));

import { RuntimeWorkspacePage } from "./RuntimeWorkspace";
import { RuntimeWorkspacesPage } from "./RuntimeWorkspaces";

beforeEach(() => {
  useAppStore.setState({ studioMode: "agent" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/runtime/workspaces/ws-abc123"]}>
      <Routes>
        <Route path="/runtime/workspaces/:workspaceId" element={<RuntimeWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RuntimeWorkspacesPage", () => {
  it("renders the workspace list with status and artifact count", async () => {
    render(
      <MemoryRouter>
        <RuntimeWorkspacesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Storefront Project")).toBeTruthy();
    expect(screen.getByText("draft")).toBeTruthy();
    expect(screen.getByText("Runtime Workspaces")).toBeTruthy();
    const link = screen.getByText("Storefront Project").closest("a")!;
    expect(link.getAttribute("href")).toBe("/runtime/workspaces/ws-abc123");
  });

  it("creates a workspace through the create flow", async () => {
    createRuntimeWorkspace.mockResolvedValue({ ...workspace, workspace_id: "ws-new" });
    render(
      <MemoryRouter initialEntries={["/runtime"]}>
        <Routes>
          <Route path="/runtime" element={<RuntimeWorkspacesPage />} />
          <Route
            path="/runtime/workspaces/:workspaceId"
            element={<div data-testid="detail">detail</div>}
          />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("+ New Workspace"));
    fireEvent.change(screen.getByPlaceholderText("My project workspace"), {
      target: { value: "Fresh Workspace" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => expect(screen.getByTestId("detail")).toBeTruthy());
    expect(createRuntimeWorkspace).toHaveBeenCalledWith({ name: "Fresh Workspace", goal: null });
  });

  it("blocks creation in Chat Mode", async () => {
    useAppStore.setState({ studioMode: "chat" });
    render(
      <MemoryRouter>
        <RuntimeWorkspacesPage />
      </MemoryRouter>,
    );
    const button = (await screen.findByText("+ New Workspace")) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("Switch to Agent Mode to perform this action.");
  });
});

describe("RuntimeWorkspacePage", () => {
  it("renders status banner, goal, activity, artifacts, and health placeholder", async () => {
    renderDetail();
    const banner = await screen.findByTestId("workspace-status-banner");
    expect(banner.textContent).toContain("draft");
    expect(banner.textContent).toContain("Draft — define the goal");
    expect(screen.getByDisplayValue("Eventually build a small storefront site.")).toBeTruthy();
    expect(screen.getByText("workspace.created")).toBeTruthy();
    expect(screen.getByText("workspace.updated")).toBeTruthy();
    expect(screen.getByText("index.html")).toBeTruthy();
    expect(screen.getByText("Project health")).toBeTruthy();
    expect(screen.getByText(/Health signals arrive with later Runtime versions/)).toBeTruthy();
    // links back to the activity run's timeline + replay
    expect(screen.getByText("timeline ↗").closest("a")!.getAttribute("href")).toBe(
      "/runs/ws-abc123-activity?tab=timeline",
    );
    expect(screen.getByText("Replay history").closest("a")!.getAttribute("href")).toBe(
      "/runs/ws-abc123-activity?tab=replay",
    );
  });

  it("changes status from the banner actions", async () => {
    patchRuntimeWorkspace.mockResolvedValue({ ...workspace, status: "active" });
    renderDetail();
    fireEvent.click(await screen.findByText("Activate"));
    await waitFor(() =>
      expect(patchRuntimeWorkspace).toHaveBeenCalledWith("ws-abc123", { status: "active" }),
    );
  });

  it("archives from the banner", async () => {
    archiveRuntimeWorkspace.mockResolvedValue({ ...workspace, status: "archived" });
    renderDetail();
    fireEvent.click(await screen.findByText("Archive"));
    await waitFor(() => expect(archiveRuntimeWorkspace).toHaveBeenCalledWith("ws-abc123"));
  });

  it("saves an edited goal", async () => {
    patchRuntimeWorkspace.mockResolvedValue(workspace);
    renderDetail();
    const textarea = await screen.findByDisplayValue("Eventually build a small storefront site.");
    fireEvent.change(textarea, { target: { value: "A sharper goal." } });
    fireEvent.click(screen.getByText("Save goal"));
    await waitFor(() =>
      expect(patchRuntimeWorkspace).toHaveBeenCalledWith("ws-abc123", { goal: "A sharper goal." }),
    );
  });

  it("registers an artifact", async () => {
    registerRuntimeArtifact.mockResolvedValue(artifacts[0]);
    renderDetail();
    fireEvent.change(await screen.findByPlaceholderText("index.html"), {
      target: { value: "styles.css" },
    });
    fireEvent.click(screen.getByText("Register artifact"));
    await waitFor(() =>
      expect(registerRuntimeArtifact).toHaveBeenCalledWith("ws-abc123", {
        name: "styles.css",
        type: "file",
        path: null,
      }),
    );
  });

  it("disables actions in Chat Mode", async () => {
    useAppStore.setState({ studioMode: "chat" });
    renderDetail();
    const activate = (await screen.findByText("Activate")) as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    const register = screen.getByText("Register artifact") as HTMLButtonElement;
    expect(register.disabled).toBe(true);
  });
});
