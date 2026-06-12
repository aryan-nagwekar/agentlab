import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { SandboxFileEntry, SandboxFileRead, SandboxStatus } from "../../lib/types";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function SandboxFilesPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const statusState = useFetch(() => api.sandboxStatus(workspaceId), [workspaceId]);
  const status: SandboxStatus | null = statusState.data ?? null;
  const treeState = useFetch(
    () => (status?.initialized ? api.sandboxTree(workspaceId) : Promise.resolve([])),
    [workspaceId, status?.initialized],
  );

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<"file" | "folder" | null>(null);
  const [newPath, setNewPath] = useState("");
  const [selected, setSelected] = useState<SandboxFileRead | null>(null);
  const [editContent, setEditContent] = useState("");
  const [dirty, setDirty] = useState(false);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;

  const refresh = () => {
    statusState.refetch(true);
    treeState.refetch(true);
  };

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const openFile = async (path: string) => {
    setError(null);
    try {
      const file = await api.sandboxRead(workspaceId, path);
      setSelected(file);
      setEditContent(file.content);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (statusState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Files</SectionLabel>
        <Spinner label="Loading sandbox…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Files</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          sandboxed · workspace-bounded
        </span>
      </div>

      {/* Status card / init flow */}
      {!status?.initialized ? (
        <div
          data-testid="sandbox-uninitialized"
          className="mt-3 rounded-lg border border-edge bg-surface-0 px-3 py-3 text-[12px] text-zinc-500"
        >
          <p>
            No sandbox yet. Initializing creates an isolated, workspace-bounded file area —
            every operation is confined to this workspace and path escapes are blocked.
            Nothing here runs commands or builds.
          </p>
          {!readOnly ? (
            <button
              type="button"
              disabled={disabled || busy !== null}
              title={hintTitle}
              onClick={() => act("init", () => api.sandboxInit(workspaceId))}
              className="mt-2 rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {busy === "init" ? "Initializing…" : "Initialize sandbox"}
            </button>
          ) : null}
        </div>
      ) : (
        <>
          <div
            data-testid="sandbox-status"
            className="mt-3 grid grid-cols-3 gap-2 text-center text-[11px]"
          >
            <div className="rounded-md bg-surface-2 px-2 py-1.5">
              <div className="font-mono text-[13px] text-zinc-200">{status.file_count}</div>
              <div className="text-zinc-600">files</div>
            </div>
            <div className="rounded-md bg-surface-2 px-2 py-1.5">
              <div className="font-mono text-[13px] text-zinc-200">
                {status.directory_count}
              </div>
              <div className="text-zinc-600">folders</div>
            </div>
            <div className="rounded-md bg-surface-2 px-2 py-1.5">
              <div className="font-mono text-[13px] text-zinc-200">
                {fmtBytes(status.total_bytes)}
              </div>
              <div className="text-zinc-600">total</div>
            </div>
          </div>

          {!readOnly ? (
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={disabled || busy !== null}
                title={hintTitle}
                onClick={() => {
                  setCreating(creating === "file" ? null : "file");
                  setNewPath("");
                }}
                className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
              >
                + New file
              </button>
              <button
                type="button"
                disabled={disabled || busy !== null}
                title={hintTitle}
                onClick={() => {
                  setCreating(creating === "folder" ? null : "folder");
                  setNewPath("");
                }}
                className="rounded-md border border-edge bg-surface-1 px-2.5 py-1 text-[11.5px] text-zinc-300 transition-colors hover:bg-surface-2 disabled:opacity-40"
              >
                + New folder
              </button>
            </div>
          ) : null}

          {creating ? (
            <div className="mt-2 flex items-end gap-2">
              <label className="flex min-w-[180px] flex-1 flex-col gap-1">
                <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                  {creating === "file" ? "File path" : "Folder path"}
                </span>
                <input
                  value={newPath}
                  onChange={(e) => setNewPath(e.target.value)}
                  placeholder={creating === "file" ? "src/index.html" : "src"}
                  className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200"
                />
              </label>
              <button
                type="button"
                disabled={disabled || busy !== null || !newPath.trim()}
                title={hintTitle}
                onClick={() =>
                  act("create", async () => {
                    if (creating === "file") {
                      await api.sandboxWrite(workspaceId, {
                        path: newPath.trim(),
                        content: "",
                      });
                    } else {
                      await api.sandboxMkdir(workspaceId, newPath.trim());
                    }
                    setCreating(null);
                    setNewPath("");
                  })
                }
                className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
              >
                {busy === "create" ? "Creating…" : "Create"}
              </button>
            </div>
          ) : null}

          {/* File tree */}
          {treeState.data && treeState.data.length > 0 ? (
            <div className="mt-3 rounded-lg border border-edge bg-surface-0 px-2 py-1.5">
              <FileTree
                nodes={treeState.data}
                depth={0}
                disabled={disabled}
                hintTitle={hintTitle}
                readOnly={readOnly}
                busy={busy}
                onOpen={openFile}
                onDelete={(path) =>
                  act(`del-${path}`, async () => {
                    await api.sandboxDelete(workspaceId, path);
                    if (selected?.path === path) setSelected(null);
                  })
                }
              />
            </div>
          ) : (
            <p className="mt-3 text-[12px] text-zinc-600" data-testid="files-empty">
              No files yet — create the first file in this workspace sandbox.
            </p>
          )}
        </>
      )}

      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}

      {/* View / edit panel */}
      {selected ? (
        <div className="mt-3 rounded-lg border border-edge bg-surface-0 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[12px] text-zinc-200">{selected.path}</span>
            <span className="text-[10.5px] text-zinc-600">
              {fmtBytes(selected.size_bytes)} · sha256 {selected.sha256}
            </span>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="ml-auto rounded-md px-2 py-0.5 text-[11px] text-zinc-500 hover:text-zinc-300"
            >
              Close
            </button>
          </div>
          <textarea
            value={editContent}
            onChange={(e) => {
              setEditContent(e.target.value);
              setDirty(true);
            }}
            rows={10}
            readOnly={disabled}
            spellCheck={false}
            className="mt-2 w-full rounded-lg border border-edge bg-surface-2 px-2.5 py-2 font-mono text-[12px] leading-5 text-zinc-200"
          />
          {dirty && !readOnly ? (
            <button
              type="button"
              disabled={disabled || busy !== null}
              title={hintTitle}
              onClick={() =>
                act("save", async () => {
                  await api.sandboxWrite(workspaceId, {
                    path: selected.path,
                    content: editContent,
                  });
                  await openFile(selected.path);
                })
              }
              className="mt-2 rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {busy === "save" ? "Saving…" : "Save file"}
            </button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function FileTree({
  nodes,
  depth,
  disabled,
  hintTitle,
  readOnly,
  busy,
  onOpen,
  onDelete,
}: {
  nodes: SandboxFileEntry[];
  depth: number;
  disabled: boolean;
  hintTitle: string | undefined;
  readOnly: boolean;
  busy: string | null;
  onOpen: (path: string) => void;
  onDelete: (path: string) => void;
}) {
  return (
    <div>
      {nodes.map((node) => (
        <div key={node.path}>
          <div
            data-testid="file-row"
            className="group flex items-center gap-2 rounded px-1.5 py-1 text-[12px] hover:bg-surface-2"
            style={{ paddingLeft: `${6 + depth * 14}px` }}
          >
            <span className="text-zinc-600">{node.type === "directory" ? "▸" : "·"}</span>
            {node.type === "file" ? (
              <button
                type="button"
                onClick={() => onOpen(node.path)}
                className="font-mono text-zinc-300 hover:text-indigo-300 hover:underline"
              >
                {node.name}
              </button>
            ) : (
              <span className="font-mono text-zinc-400">{node.name}/</span>
            )}
            {node.type === "file" ? (
              <span className="text-[10px] text-zinc-600">{fmtBytes(node.size_bytes)}</span>
            ) : null}
            {!readOnly ? (
              <button
                type="button"
                disabled={disabled || busy !== null}
                title={hintTitle}
                onClick={() => onDelete(node.path)}
                className="ml-auto rounded px-1.5 text-[10.5px] text-red-300/0 transition-colors hover:bg-red-400/10 group-hover:text-red-300/90 disabled:opacity-40"
              >
                delete
              </button>
            ) : null}
          </div>
          {node.children && node.children.length > 0 ? (
            <FileTree
              nodes={node.children}
              depth={depth + 1}
              disabled={disabled}
              hintTitle={hintTitle}
              readOnly={readOnly}
              busy={busy}
              onOpen={onOpen}
              onDelete={onDelete}
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}
