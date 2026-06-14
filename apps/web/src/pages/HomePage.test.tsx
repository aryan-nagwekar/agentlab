// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const createBottleShopDemo = vi.fn();
vi.mock("../lib/api", () => ({
  API_BASE: "",
  api: { createBottleShopDemo: (...a: unknown[]) => createBottleShopDemo(...a) },
}));

import { HomePage } from "./HomePage";

function renderHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/runtime" element={<div>Runtime Page</div>} />
        <Route
          path="/runtime/workspaces/:id"
          element={<div>Workspace Page</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HomePage", () => {
  it("renders the hero, value props, and steps", async () => {
    renderHome();
    expect(screen.getByText("Build with AI. Stay in control.")).toBeTruthy();
    expect(
      screen.getByText(/visual runtime, debugger, and safety control plane/),
    ).toBeTruthy();
    expect(screen.getByText("Observe agent actions")).toBeTruthy();
    expect(screen.getByText("Quarantine restricted agents")).toBeTruthy();
    expect(screen.getByText("How it works")).toBeTruthy();
  });

  it("navigates to runtime via the secondary CTA", () => {
    renderHome();
    fireEvent.click(screen.getByText("Open Runtime"));
    expect(screen.getByText("Runtime Page")).toBeTruthy();
  });

  it("creates the demo and navigates to the new workspace", async () => {
    createBottleShopDemo.mockResolvedValue({ workspace_id: "ws-demo1" });
    renderHome();
    fireEvent.click(screen.getAllByText("Try Bottle Shop Demo")[0]);
    await waitFor(() => expect(createBottleShopDemo).toHaveBeenCalled());
    expect(await screen.findByText("Workspace Page")).toBeTruthy();
  });

  it("shows an error when demo creation fails", async () => {
    createBottleShopDemo.mockRejectedValue(new Error("500 demo failed"));
    renderHome();
    fireEvent.click(screen.getAllByText("Try Bottle Shop Demo")[0]);
    expect(await screen.findByText(/demo failed/)).toBeTruthy();
  });
});
