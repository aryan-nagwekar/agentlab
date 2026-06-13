import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { RuntimeApproval } from "../../lib/types";
import { fmtClock } from "../../lib/format";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

const STATUS_STYLE: Record<string, string> = {
  pending: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  approved: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  denied: "border-red-400/40 bg-red-400/10 text-red-300",
  cancelled: "border-edge bg-surface-2 text-zinc-500",
  rerouted: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  quarantine_requested: "border-red-400/40 bg-red-400/10 text-red-300",
  expired: "border-edge bg-surface-2 text-zinc-500",
};

const RISK_STYLE: Record<string, string> = {
  low: "text-zinc-500",
  medium: "text-amber-300/90",
  high: "text-red-300/90",
};

const EXECUTION_STYLE: Record<string, string> = {
  executed: "text-emerald-300",
  execution_failed: "text-red-300",
  skipped: "text-amber-300/90",
  not_executed: "text-zinc-500",
};

// Resolution buttons offered for a pending approval.
const RESOLUTIONS: Array<{
  action: "approve" | "deny" | "approve-readonly" | "reroute" | "quarantine";
  label: string;
  tone: "primary" | "danger" | "neutral";
}> = [
  { action: "approve", label: "Approve", tone: "primary" },
  { action: "deny", label: "Deny", tone: "danger" },
  { action: "approve-readonly", label: "Approve read-only", tone: "neutral" },
  { action: "reroute", label: "Reroute", tone: "neutral" },
  { action: "quarantine", label: "Quarantine", tone: "danger" },
];

const TONE_CLASS: Record<string, string> = {
  primary:
    "border-indigo-400/40 bg-indigo-500/15 text-indigo-200 hover:bg-indigo-500/25",
  danger: "border-red-400/30 bg-red-400/10 text-red-300 hover:bg-red-400/20",
  neutral: "border-edge bg-surface-1 text-zinc-300 hover:bg-surface-2",
};

export function ApprovalsPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const approvalsState = useFetch(
    () => api.workspaceApprovals(workspaceId),
    [workspaceId],
  );
  const approvals = approvalsState.data ?? [];
  const pending = approvals.filter((a) => a.status === "pending");

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;

  const resolve = async (
    approval: RuntimeApproval,
    action: "approve" | "deny" | "approve-readonly" | "reroute" | "quarantine",
  ) => {
    setBusy(`${approval.approval_id}:${action}`);
    setError(null);
    try {
      await api.resolveApproval(workspaceId, approval.approval_id, action);
      approvalsState.refetch(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (approvalsState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Approvals</SectionLabel>
        <Spinner label="Loading approvals…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Approvals</SectionLabel>
        <span
          data-testid="pending-count"
          className={`rounded-md border px-1.5 py-0.5 text-[10px] ${
            pending.length > 0
              ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
              : "border-edge bg-surface-0 text-zinc-500"
          }`}
        >
          {pending.length} pending
        </span>
      </div>

      <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
        Actions the enforcement gateway halted for a human decision. Approving resumes
        the exact stored action through the existing safe executors; denying keeps it
        blocked. Quarantine/reroute are recorded as decisions only.
      </p>

      {approvals.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="approvals-empty">
          No approvals yet — when a risky file, command, or workflow action is halted, it
          appears here for review.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {approvals.slice(0, 8).map((approval) => (
            <div
              key={approval.approval_id}
              data-testid="approval-card"
              className="rounded-lg border border-edge bg-surface-0 px-3 py-2.5"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${STATUS_STYLE[approval.status] ?? "border-edge bg-surface-2 text-zinc-400"}`}
                >
                  {approval.status.replace(/_/g, " ")}
                </span>
                <span className="font-mono text-[11.5px] text-zinc-300">
                  {approval.action_type}
                </span>
                {approval.target ? (
                  <span className="truncate font-mono text-[11px] text-zinc-500">
                    {approval.target}
                  </span>
                ) : null}
                <span className={`text-[10.5px] ${RISK_STYLE[approval.risk_level] ?? "text-zinc-500"}`}>
                  risk {approval.risk_level}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-zinc-600">
                  {fmtClock(approval.created_at)}
                </span>
              </div>

              <p className="mt-1.5 text-[11.5px] text-zinc-400">
                {approval.plain_english_summary}
              </p>

              {approval.matched_policy_rules.length > 0 ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {approval.matched_policy_rules.map((rule) => (
                    <span
                      key={rule.id}
                      data-testid="approval-rule"
                      className="rounded border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500"
                      title={rule.name}
                    >
                      {rule.id}
                    </span>
                  ))}
                </div>
              ) : null}

              <button
                type="button"
                onClick={() =>
                  setExpanded(expanded === approval.approval_id ? null : approval.approval_id)
                }
                className="mt-1.5 text-[10.5px] text-indigo-300 hover:underline"
              >
                {expanded === approval.approval_id ? "Hide" : "Technical details"}
              </button>
              {expanded === approval.approval_id ? (
                <pre className="mt-1 whitespace-pre-wrap rounded-md bg-surface-2 px-2 py-1.5 font-mono text-[10.5px] text-zinc-400">
                  {approval.technical_summary}
                </pre>
              ) : null}

              {/* Pending → resolution controls */}
              {approval.status === "pending" && !readOnly ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {RESOLUTIONS.filter((r) =>
                    // map button action name to backend option id
                    approval.options.includes(
                      r.action === "approve-readonly" ? "approve_readonly" : r.action,
                    ),
                  ).map((r) => (
                    <button
                      key={r.action}
                      type="button"
                      disabled={disabled || busy !== null}
                      title={hintTitle}
                      onClick={() => resolve(approval, r.action)}
                      className={`rounded-md border px-2.5 py-1 text-[11.5px] font-medium transition-colors disabled:opacity-40 ${TONE_CLASS[r.tone]} ${
                        approval.recommended_decision ===
                        (r.action === "approve-readonly" ? "approve_readonly" : r.action)
                          ? "ring-1 ring-inset ring-current/30"
                          : ""
                      }`}
                    >
                      {busy === `${approval.approval_id}:${r.action}` ? "…" : r.label}
                    </button>
                  ))}
                </div>
              ) : null}

              {/* Resolved → outcome */}
              {approval.status !== "pending" ? (
                <p data-testid="approval-resolution" className="mt-1.5 text-[11px] text-zinc-500">
                  {approval.resolution_decision} by {approval.resolved_by ?? "—"}
                  {approval.execution_status !== "not_executed" ? (
                    <>
                      {" · "}
                      <span className={EXECUTION_STYLE[approval.execution_status]}>
                        {approval.execution_status.replace(/_/g, " ")}
                      </span>
                      {approval.execution_detail ? ` — ${approval.execution_detail}` : ""}
                    </>
                  ) : null}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}
      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}
    </Card>
  );
}
