import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { SandboxCommandResult } from "../../lib/types";
import { fmtClock } from "../../lib/format";
import { Card, ErrorNote, SectionLabel } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

type PanelStatus = SandboxCommandResult["status"] | "blocked" | "running";

const STATUS_STYLE: Record<PanelStatus, string> = {
  completed: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  failed: "border-red-400/40 bg-red-400/10 text-red-300",
  timed_out: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  blocked: "border-red-400/40 bg-red-400/10 text-red-300",
  running: "border-sky-400/30 bg-sky-400/10 text-sky-300",
};

/** Split a typed command line into command + args (whitespace only — the
 * backend rejects anything shell-like, so no quoting rules are needed). */
function splitCommandLine(line: string): { command: string; args: string[] } {
  const tokens = line.trim().split(/\s+/).filter(Boolean);
  return { command: tokens[0] ?? "", args: tokens.slice(1) };
}

export function SandboxCommandsPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const statusState = useFetch(() => api.sandboxStatus(workspaceId), [workspaceId]);
  const initialized = statusState.data?.initialized ?? false;
  const allowedState = useFetch(
    () => api.sandboxAllowedCommands(workspaceId),
    [workspaceId],
  );
  const historyState = useFetch(
    () =>
      initialized
        ? api.sandboxCommandHistory(workspaceId)
        : Promise.resolve([]),
    [workspaceId, initialized],
  );

  const [line, setLine] = useState("");
  const [subdir, setSubdir] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SandboxCommandResult | null>(null);
  const [blockedError, setBlockedError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;

  const run = async () => {
    const { command, args } = splitCommandLine(line);
    if (!command) return;
    setRunning(true);
    setResult(null);
    setBlockedError(null);
    try {
      const outcome = await api.sandboxRunCommand(workspaceId, {
        command,
        args,
        working_subdir: subdir.trim(),
      });
      setResult(outcome);
    } catch (e) {
      setBlockedError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
      historyState.refetch(true);
    }
  };

  const status: PanelStatus | null = running
    ? "running"
    : blockedError
      ? "blocked"
      : (result?.status ?? null);

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Commands</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          allowlisted · sandbox-only · no shell
        </span>
      </div>

      {!initialized ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="commands-uninitialized">
          Initialize the workspace sandbox (Files panel) to run commands.
        </p>
      ) : (
        <>
          <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
            Runs a small allowlisted set of development commands inside this workspace's
            sandbox. Every command is safety-checked before execution; unsafe or unknown
            commands are blocked and audited.{" "}
            <button
              type="button"
              onClick={() => setShowHelp((s) => !s)}
              className="text-indigo-300 hover:underline"
            >
              {showHelp ? "Hide allowed commands" : "Show allowed commands"}
            </button>
          </p>

          {showHelp && allowedState.data ? (
            <div
              data-testid="allowed-commands"
              className="mt-2 space-y-1 rounded-lg border border-edge bg-surface-0 px-3 py-2"
            >
              {allowedState.data.map((entry) => (
                <div key={entry.command} className="flex flex-wrap items-baseline gap-2 text-[11.5px]">
                  <button
                    type="button"
                    onClick={() => setLine(entry.examples[0] ?? entry.command)}
                    className="font-mono text-indigo-300 hover:underline"
                  >
                    {entry.command}
                  </button>
                  <span className="text-zinc-500">{entry.description}</span>
                  <span className="ml-auto font-mono text-[10px] text-zinc-600">
                    {entry.examples.join(" · ")}
                  </span>
                </div>
              ))}
            </div>
          ) : null}

          {/* Command input */}
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="flex min-w-[220px] flex-[2] flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Command
              </span>
              <input
                value={line}
                onChange={(e) => setLine(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !disabled && !running && line.trim()) run();
                }}
                placeholder="ls -la"
                disabled={disabled}
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200 disabled:opacity-60"
              />
            </label>
            <label className="flex w-36 flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Subdir (optional)
              </span>
              <input
                value={subdir}
                onChange={(e) => setSubdir(e.target.value)}
                placeholder="src"
                disabled={disabled}
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200 disabled:opacity-60"
              />
            </label>
            <button
              type="button"
              disabled={disabled || running || !line.trim()}
              title={hintTitle}
              onClick={run}
              className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {running ? "Running…" : "Run"}
            </button>
          </div>

          {/* Outcome card */}
          {status ? (
            <div
              data-testid="command-outcome"
              className="mt-3 rounded-lg border border-edge bg-surface-0 px-3 py-2.5"
            >
              <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
                <span
                  className={`rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${STATUS_STYLE[status]}`}
                >
                  {status.replace("_", " ")}
                </span>
                {result ? (
                  <>
                    <span className="font-mono text-zinc-300">{result.command}</span>
                    {result.exit_code !== null ? (
                      <span className="text-zinc-500">exit {result.exit_code}</span>
                    ) : null}
                    <span className="ml-auto text-[10.5px] text-zinc-600">
                      {result.duration_ms} ms · cwd {result.cwd}
                    </span>
                  </>
                ) : null}
              </div>
              {blockedError ? (
                <p data-testid="blocked-reason" className="mt-1.5 text-[11.5px] text-red-300/90">
                  {blockedError} — the command was not executed.
                </p>
              ) : null}
              {result?.stdout ? (
                <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 px-2.5 py-2 font-mono text-[11px] leading-4 text-zinc-300">
                  {result.stdout}
                  {result.stdout_truncated ? "\n… output truncated" : ""}
                </pre>
              ) : null}
              {result?.stderr ? (
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 px-2.5 py-2 font-mono text-[11px] leading-4 text-amber-200/80">
                  {result.stderr}
                  {result.stderr_truncated ? "\n… output truncated" : ""}
                </pre>
              ) : null}
            </div>
          ) : null}

          {/* History (from events — raw events stay the source of truth) */}
          {historyState.data && historyState.data.length > 0 ? (
            <div className="mt-3">
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                History
              </div>
              <div className="space-y-1">
                {historyState.data.slice(0, 10).map((event) => (
                  <div
                    key={event.event_id}
                    data-testid="command-history-row"
                    className="flex items-center gap-2 rounded-md border border-edge bg-surface-2 px-2.5 py-1 text-[11px]"
                  >
                    <span className="font-mono text-zinc-400">
                      {event.event_type.replace("sandbox.command.", "")}
                    </span>
                    <span className="truncate font-mono text-zinc-300">
                      {String(event.payload.command ?? "")}
                    </span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-zinc-600">
                      {fmtClock(event.timestamp)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
      {statusState.error ? <div className="mt-3"><ErrorNote message={statusState.error} /></div> : null}
    </Card>
  );
}
