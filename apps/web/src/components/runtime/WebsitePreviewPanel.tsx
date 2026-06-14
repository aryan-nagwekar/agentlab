import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import { API_BASE } from "../../lib/api";
import { Card, SectionLabel, Spinner } from "../ui";

export function WebsitePreviewPanel({ workspaceId }: { workspaceId: string }) {
  const statusState = useFetch(() => api.previewStatus(workspaceId), [workspaceId]);
  const [open, setOpen] = useState(false);

  if (statusState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Website preview</SectionLabel>
        <Spinner label="Checking for a previewable site…" />
      </Card>
    );
  }

  const previewable = statusState.data?.previewable ?? false;
  // Same-origin (proxied) URL; the iframe is sandboxed so scripts run isolated.
  const src = `${API_BASE}/api/runtime/workspaces/${workspaceId}/preview/index.html`;

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Website preview</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          read-only · sandbox-bounded
        </span>
      </div>

      {!previewable ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="preview-unavailable">
          No preview available — this workspace has no <code className="text-zinc-400">index.html</code>{" "}
          in its sandbox. Generate a static site (e.g. the Bottle Shop demo) to preview it here.
        </p>
      ) : (
        <>
          <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
            A safe, read-only render of the generated site, served only from this workspace's
            sandbox and isolated in a sandboxed frame.
          </p>
          {!open ? (
            <button
              type="button"
              data-testid="open-preview"
              onClick={() => setOpen(true)}
              className="mt-3 rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25"
            >
              Open Website Preview
            </button>
          ) : (
            <div className="mt-3">
              <div className="flex items-center justify-between gap-2 rounded-t-lg border border-b-0 border-edge bg-surface-2 px-2.5 py-1.5 text-[10.5px] text-zinc-500">
                <span className="font-mono">preview · index.html</span>
                <a
                  href={src}
                  target="_blank"
                  rel="noreferrer"
                  className="text-indigo-300 hover:underline"
                >
                  Open in new tab ↗
                </a>
              </div>
              <iframe
                data-testid="preview-iframe"
                title="Generated website preview"
                src={src}
                sandbox="allow-scripts"
                className="h-[520px] w-full rounded-b-lg border border-edge bg-white"
              />
            </div>
          )}
        </>
      )}
    </Card>
  );
}
