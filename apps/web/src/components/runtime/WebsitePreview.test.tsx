// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const previewStatus = vi.fn();
vi.mock("../../lib/api", () => ({
  API_BASE: "",
  api: { previewStatus: (...a: unknown[]) => previewStatus(...a) },
}));

import { WebsitePreviewPanel } from "./WebsitePreviewPanel";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WebsitePreviewPanel", () => {
  it("shows the unavailable state when there is no index.html", async () => {
    previewStatus.mockResolvedValue({ workspace_id: "ws-1", previewable: false });
    render(<WebsitePreviewPanel workspaceId="ws-1" />);
    expect(await screen.findByTestId("preview-unavailable")).toBeTruthy();
    expect(screen.queryByTestId("open-preview")).toBeNull();
  });

  it("shows the open-preview button and lazily renders a sandboxed iframe", async () => {
    previewStatus.mockResolvedValue({ workspace_id: "ws-1", previewable: true });
    render(<WebsitePreviewPanel workspaceId="ws-1" />);
    const open = await screen.findByTestId("open-preview");
    // iframe is not rendered until the user opts in
    expect(screen.queryByTestId("preview-iframe")).toBeNull();
    fireEvent.click(open);
    const iframe = screen.getByTestId("preview-iframe") as HTMLIFrameElement;
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("src")).toBe(
      "/api/runtime/workspaces/ws-1/preview/index.html",
    );
  });

  it("shows the read-only / sandbox-bounded label", async () => {
    previewStatus.mockResolvedValue({ workspace_id: "ws-1", previewable: true });
    render(<WebsitePreviewPanel workspaceId="ws-1" />);
    expect(await screen.findByText("read-only · sandbox-bounded")).toBeTruthy();
  });
});
