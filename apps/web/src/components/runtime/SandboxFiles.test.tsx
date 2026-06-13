// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SandboxFileEntry, SandboxStatus } from "../../lib/types";

const uninitialized: SandboxStatus = {
  workspace_id: "ws-abc123",
  initialized: false,
  file_count: 0,
  directory_count: 0,
  total_bytes: 0,
};

const initialized: SandboxStatus = {
  ...uninitialized,
  initialized: true,
  file_count: 2,
  directory_count: 1,
  total_bytes: 2048,
};

const tree: SandboxFileEntry[] = [
  {
    name: "src",
    path: "src",
    type: "directory",
    size_bytes: 0,
    modified_at: 1,
    children: [
      {
        name: "index.html",
        path: "src/index.html",
        type: "file",
        size_bytes: 1024,
        modified_at: 2,
      },
    ],
  },
  { name: "README.md", path: "README.md", type: "file", size_bytes: 1024, modified_at: 3 },
];

const sandboxStatus = vi.fn();
const sandboxTree = vi.fn();
const sandboxInit = vi.fn();
const sandboxRead = vi.fn();
const sandboxWrite = vi.fn();
const sandboxMkdir = vi.fn();
const sandboxDelete = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    sandboxStatus: (...a: unknown[]) => sandboxStatus(...a),
    sandboxTree: (...a: unknown[]) => sandboxTree(...a),
    sandboxInit: (...a: unknown[]) => sandboxInit(...a),
    sandboxRead: (...a: unknown[]) => sandboxRead(...a),
    sandboxWrite: (...a: unknown[]) => sandboxWrite(...a),
    sandboxMkdir: (...a: unknown[]) => sandboxMkdir(...a),
    sandboxDelete: (...a: unknown[]) => sandboxDelete(...a),
  },
}));

import { SandboxFilesPanel } from "./SandboxFilesPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <SandboxFilesPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  sandboxStatus.mockResolvedValue(initialized);
  sandboxTree.mockResolvedValue(tree);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SandboxFilesPanel", () => {
  it("renders the uninitialized state and initializes the sandbox", async () => {
    sandboxStatus.mockResolvedValue(uninitialized);
    sandboxInit.mockResolvedValue(initialized);
    renderPanel();
    expect(await screen.findByTestId("sandbox-uninitialized")).toBeTruthy();
    fireEvent.click(screen.getByText("Initialize sandbox"));
    await waitFor(() => expect(sandboxInit).toHaveBeenCalledWith("ws-abc123"));
  });

  it("renders the status card and file tree", async () => {
    renderPanel();
    const status = await screen.findByTestId("sandbox-status");
    expect(status.textContent).toContain("2");
    expect(status.textContent).toContain("files");
    expect(screen.getByText("sandboxed · workspace-bounded")).toBeTruthy();
    expect(await screen.findByText("src/")).toBeTruthy();
    expect(screen.getByText("index.html")).toBeTruthy();
    expect(screen.getByText("README.md")).toBeTruthy();
  });

  it("renders the empty state when there are no files", async () => {
    sandboxTree.mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByTestId("files-empty")).toBeTruthy();
  });

  it("creates a file through the new-file flow", async () => {
    sandboxWrite.mockResolvedValue({
      path: "notes.md",
      size_bytes: 0,
      sha256: "x",
      created: true,
    });
    renderPanel();
    fireEvent.click(await screen.findByText("+ New file"));
    fireEvent.change(screen.getByPlaceholderText("src/index.html"), {
      target: { value: "notes.md" },
    });
    fireEvent.click(screen.getByText("Create"));
    await waitFor(() =>
      expect(sandboxWrite).toHaveBeenCalledWith("ws-abc123", {
        path: "notes.md",
        content: "",
      }),
    );
  });

  it("creates a folder through the new-folder flow", async () => {
    sandboxMkdir.mockResolvedValue({ path: "assets", created: true });
    renderPanel();
    fireEvent.click(await screen.findByText("+ New folder"));
    fireEvent.change(screen.getByPlaceholderText("src"), { target: { value: "assets" } });
    fireEvent.click(screen.getByText("Create"));
    await waitFor(() => expect(sandboxMkdir).toHaveBeenCalledWith("ws-abc123", "assets"));
  });

  it("opens a file, edits it, and saves", async () => {
    sandboxRead.mockResolvedValue({
      path: "README.md",
      content: "# hello",
      size_bytes: 7,
      sha256: "abcd1234abcd1234",
    });
    sandboxWrite.mockResolvedValue({
      path: "README.md",
      size_bytes: 9,
      sha256: "y",
      created: false,
    });
    renderPanel();
    fireEvent.click(await screen.findByText("README.md"));
    const editor = await screen.findByDisplayValue("# hello");
    fireEvent.change(editor, { target: { value: "# changed" } });
    fireEvent.click(screen.getByText("Save file"));
    await waitFor(() =>
      expect(sandboxWrite).toHaveBeenCalledWith("ws-abc123", {
        path: "README.md",
        content: "# changed",
      }),
    );
  });

  it("deletes a file from the tree", async () => {
    sandboxDelete.mockResolvedValue({ path: "README.md", kind: "file" });
    renderPanel();
    await screen.findByText("README.md");
    const row = screen
      .getAllByTestId("file-row")
      .find((r) => r.textContent?.includes("README.md"))!;
    fireEvent.click(row.querySelector("button:last-child")!);
    await waitFor(() => expect(sandboxDelete).toHaveBeenCalledWith("ws-abc123", "README.md"));
  });

  it("surfaces the enforcement approval-required reason and links to the approval (v1.6)", async () => {
    sandboxWrite.mockRejectedValue(
      new Error(
        "403 Forbidden — approval required (approval-sensitive-file): the file touches auth/payment/deployment-sensitive paths and needs human approval — approval apr-1234567890 is waiting in the Approvals panel",
      ),
    );
    renderPanel();
    fireEvent.click(await screen.findByText("+ New file"));
    fireEvent.change(screen.getByPlaceholderText("src/index.html"), {
      target: { value: "src/payment/checkout.ts" },
    });
    fireEvent.click(screen.getByText("Create"));
    expect(
      await screen.findByText(/approval required \(approval-sensitive-file\)/),
    ).toBeTruthy();
    expect(screen.getByText(/is waiting in the Approvals panel/)).toBeTruthy();
  });

  it("shows the safe error when a path is blocked", async () => {
    sandboxWrite.mockRejectedValue(
      new Error("400 Bad Request — blocked (traversal): path traversal ('..') is not allowed"),
    );
    renderPanel();
    fireEvent.click(await screen.findByText("+ New file"));
    fireEvent.change(screen.getByPlaceholderText("src/index.html"), {
      target: { value: "../escape.txt" },
    });
    fireEvent.click(screen.getByText("Create"));
    expect(await screen.findByText(/blocked \(traversal\)/)).toBeTruthy();
  });

  it("disables mutating actions in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const newFile = (await screen.findByText("+ New file")) as HTMLButtonElement;
    expect(newFile.disabled).toBe(true);
    expect(newFile.title).toBe("Switch to Agent Mode to perform this action.");
    const newFolder = screen.getByText("+ New folder") as HTMLButtonElement;
    expect(newFolder.disabled).toBe(true);
    const del = screen.getAllByText("delete")[0] as HTMLButtonElement;
    expect(del.disabled).toBe(true);
  });

  it("disables the initialize button in Chat Mode", async () => {
    sandboxStatus.mockResolvedValue(uninitialized);
    renderPanel({ chatMode: true });
    const init = (await screen.findByText("Initialize sandbox")) as HTMLButtonElement;
    expect(init.disabled).toBe(true);
    expect(init.title).toBe("Switch to Agent Mode to perform this action.");
  });

  it("hides mutating controls when the workspace is read-only", async () => {
    renderPanel({ readOnly: true });
    await screen.findByTestId("sandbox-status");
    expect(screen.queryByText("+ New file")).toBeNull();
    expect(screen.queryByText("delete")).toBeNull();
  });
});
