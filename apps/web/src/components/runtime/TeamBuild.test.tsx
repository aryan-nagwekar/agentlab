// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TeamBuildResult } from "../../lib/types";

function result(overrides: Partial<TeamBuildResult> = {}): TeamBuildResult {
  return {
    status: "completed",
    goal: "Build a storefront.",
    workflow_id: "wf-1",
    stop_reason: "completed",
    step_count: 3,
    total_written: 1,
    total_held: 0,
    total_blocked: 0,
    steps: [
      {
        agent_id: "a-plan", agent_name: "Planner Agent", role: "planner",
        task_id: "t0", task_title: "Draft the project plan", kind: "contribute",
        status: "ok", note: "Build header, grid, footer.", files: [], validations: [],
      },
      {
        agent_id: "a-ui", agent_name: "UI Agent", role: "frontend",
        task_id: "t3", task_title: "Build the user interface", kind: "build",
        status: "ok", summary: "Built the page.",
        files: [{ path: "index.html", status: "written", reason: null }],
        validations: [{ validator: "secret_exposure", target: "index.html", passed: true }],
      },
    ],
    ...overrides,
  };
}

const teamBuild = vi.fn();
vi.mock("../../lib/api", () => ({
  api: { teamBuild: (...a: unknown[]) => teamBuild(...a) },
}));

import { TeamBuildPanel } from "./TeamBuildPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <TeamBuildPanel
      workspaceId="ws-1"
      goal="Build a storefront."
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TeamBuildPanel", () => {
  it("builds with the team and shows each agent's contribution", async () => {
    teamBuild.mockResolvedValue(result());
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Build with the team" }));
    await waitFor(() => expect(screen.getByTestId("team-result")).toBeTruthy());
    expect(teamBuild).toHaveBeenCalledWith("ws-1", { goal: undefined });
    expect(screen.getAllByTestId("team-step")).toHaveLength(2);
    expect(screen.getByText("Planner Agent")).toBeTruthy();
    expect(screen.getByText("UI Agent")).toBeTruthy();
    expect(screen.getByText(/index\.html/)).toBeTruthy();
  });

  it("surfaces a paused-for-approval team build", async () => {
    teamBuild.mockResolvedValue(
      result({ stop_reason: "halted_for_approval", total_held: 1 }),
    );
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Build with the team" }));
    await waitFor(() => expect(screen.getByText("paused for approval")).toBeTruthy());
  });

  it("disables building in Chat Mode", () => {
    renderPanel({ chatMode: true });
    expect(
      screen.getByRole("button", { name: "Build with the team" }).hasAttribute("disabled"),
    ).toBe(true);
  });
});
