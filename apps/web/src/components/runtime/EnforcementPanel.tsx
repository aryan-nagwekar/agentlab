import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { EnforcementDecision, RuntimeActionProposal } from "../../lib/types";
import { fmtClock } from "../../lib/format";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

const DECISION_STYLE: Record<EnforcementDecision, string> = {
  allow: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  allow_readonly: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  allow_sandbox_only: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  block: "border-red-400/40 bg-red-400/10 text-red-300",
  require_human_approval: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  reroute_to_verifier: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  retry_with_constraints: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  downgrade_permissions: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  quarantine_agent: "border-red-400/40 bg-red-400/10 text-red-300",
};

const DECISION_LABEL: Record<EnforcementDecision, string> = {
  allow: "allowed",
  allow_readonly: "allowed (read-only)",
  allow_sandbox_only: "allowed (sandbox-only)",
  block: "blocked",
  require_human_approval: "approval required",
  reroute_to_verifier: "rerouted",
  retry_with_constraints: "retry required",
  downgrade_permissions: "permissions downgraded",
  quarantine_agent: "quarantine triggered",
};

// A small, safe set for the developer test form — the generic proposal API
// never executes anything regardless of outcome.
const TEST_ACTION_TYPES = [
  "file.read",
  "file.write",
  "command.run",
  "data.save",
  "payment.modify",
  "final_output.publish",
];

export function EnforcementPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const decisionsState = useFetch(
    () => api.enforcementDecisions(workspaceId),
    [workspaceId],
  );
  const policiesState = useFetch(() => api.runtimePolicies(), []);

  const [testType, setTestType] = useState(TEST_ACTION_TYPES[0]);
  const [testTarget, setTestTarget] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<RuntimeActionProposal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;
  const decisions = decisionsState.data ?? [];

  const runTest = async () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const proposal = await api.proposeAction(workspaceId, {
        action_type: testType,
        target: testTarget.trim(),
      });
      setTestResult(proposal);
      decisionsState.refetch(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  if (decisionsState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Enforcement</SectionLabel>
        <Spinner label="Loading decisions…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Enforcement</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          {policiesState.data?.length ?? "—"} deterministic policies · decided before execution
        </span>
      </div>

      <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
        Every file, command, and workflow action is proposed to the gateway and resolved
        into an explainable decision before anything executes. Approval{" "}
        <em>resolution</em> arrives in v1.6 — approval-required actions are recorded and
        halted, not resumed.
      </p>

      {/* Test proposal (never executes) */}
      {!readOnly ? (
        <div className="mt-3 flex flex-wrap items-end gap-2 rounded-lg border border-edge bg-surface-0 px-3 py-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
              Test an action
            </span>
            <select
              value={testType}
              onChange={(e) => setTestType(e.target.value)}
              disabled={disabled}
              className="rounded-lg border border-edge bg-surface-2 px-2 py-1.5 font-mono text-[12px] text-zinc-200 disabled:opacity-60"
            >
              {TEST_ACTION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[160px] flex-1 flex-col gap-1">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
              Target
            </span>
            <input
              value={testTarget}
              onChange={(e) => setTestTarget(e.target.value)}
              placeholder="src/checkout.ts"
              disabled={disabled}
              className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200 disabled:opacity-60"
            />
          </label>
          <button
            type="button"
            disabled={disabled || testing}
            title={hintTitle}
            onClick={runTest}
            className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
          >
            {testing ? "Evaluating…" : "Propose (never executes)"}
          </button>
        </div>
      ) : null}

      {testResult?.decision ? (
        <div
          data-testid="test-decision"
          className="mt-2 rounded-lg border border-edge bg-surface-0 px-3 py-2 text-[11.5px]"
        >
          <span
            className={`rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${DECISION_STYLE[testResult.decision.decision]}`}
          >
            {DECISION_LABEL[testResult.decision.decision]}
          </span>
          <span className="ml-2 text-zinc-400">{testResult.decision.reason}</span>
        </div>
      ) : null}
      {error ? <div className="mt-2"><ErrorNote message={error} /></div> : null}

      {/* Recent decisions */}
      {decisions.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="enforcement-empty">
          No decisions yet — run a file, command, or workflow action and the gateway's
          verdicts will appear here.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {decisions.slice(0, 8).map((record) => (
            <div
              key={record.decision_id}
              data-testid="decision-card"
              className="rounded-lg border border-edge bg-surface-0 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${DECISION_STYLE[record.decision]}`}
                >
                  {DECISION_LABEL[record.decision]}
                </span>
                <span className="font-mono text-[11.5px] text-zinc-300">
                  {record.action_type}
                </span>
                {record.target ? (
                  <span className="truncate font-mono text-[11px] text-zinc-500">
                    {record.target}
                  </span>
                ) : null}
                <span className="ml-auto shrink-0 font-mono text-[10px] text-zinc-600">
                  {fmtClock(record.created_at)}
                </span>
              </div>
              <p className="mt-1 text-[11.5px] text-zinc-400">{record.reason}</p>
              {record.matched_rules.length > 0 ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {record.matched_rules.map((rule) => (
                    <span
                      key={rule.id}
                      data-testid="matched-rule"
                      className="rounded border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500"
                      title={rule.name}
                    >
                      {rule.id}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
