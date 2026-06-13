import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import {
  AGENT_PERMISSION_KEYS,
  RISKY_PERMISSION_KEYS,
  type AgentPermissionKey,
  type WorkspaceAgent,
  type WorkspaceAgentStatus,
} from "../../lib/types";
import { Card, ErrorNote, SectionLabel } from "../ui";
import { AgentStatusBadge } from "./AgentStatusBadge";

const AGENT_STATUSES: WorkspaceAgentStatus[] = [
  "ready",
  "running",
  "caution",
  "suspicious",
  "quarantined",
  "disabled",
];

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

/** "can_write_files" → "write files" */
function permissionLabel(key: string): string {
  return key.replace(/^can_/, "").replace(/_/g, " ");
}

function grantedPermissions(agent: WorkspaceAgent): AgentPermissionKey[] {
  return AGENT_PERMISSION_KEYS.filter((key) => agent.permissions[key]);
}

export function WorkspaceAgentsPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const agentsState = useFetch(() => api.workspaceAgents(workspaceId), [workspaceId]);
  const templatesState = useFetch(() => api.workspaceAgentTemplates(), []);

  const [showTemplates, setShowTemplates] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      agentsState.refetch(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const agents = agentsState.data ?? [];

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Agents</SectionLabel>
        {!readOnly ? (
          <button
            type="button"
            disabled={disabled}
            title={hintTitle}
            onClick={() => setShowTemplates((s) => !s)}
            className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
          >
            + Add agent
          </button>
        ) : null}
      </div>

      {/* Template picker */}
      {showTemplates && !readOnly ? (
        <div className="mt-3 rounded-lg border border-edge bg-surface-0 p-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
            Create from template
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {(templatesState.data ?? []).map((template) => {
              const riskyCount = AGENT_PERMISSION_KEYS.filter(
                (k) => template.permissions[k] && RISKY_PERMISSION_KEYS.has(k),
              ).length;
              return (
                <div
                  key={template.template_id}
                  className="flex flex-col gap-1.5 rounded-md border border-edge bg-surface-2 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[12.5px] font-semibold text-zinc-100">
                      {template.name}
                    </span>
                    <AgentStatusBadge status={template.status} className="ml-auto shrink-0" />
                  </div>
                  <p className="line-clamp-2 text-[11.5px] text-zinc-500">
                    {template.description}
                  </p>
                  {riskyCount > 0 ? (
                    <span className="text-[10.5px] text-amber-400/90">
                      ⚠ {riskyCount} risky permission{riskyCount > 1 ? "s" : ""}
                    </span>
                  ) : null}
                  <button
                    type="button"
                    disabled={disabled || busy !== null}
                    title={hintTitle}
                    onClick={() =>
                      act(`tpl-${template.template_id}`, async () => {
                        await api.createWorkspaceAgentFromTemplate(
                          workspaceId,
                          template.template_id,
                        );
                        setShowTemplates(false);
                      })
                    }
                    className="mt-1 self-start rounded-md border border-edge bg-surface-1 px-2 py-0.5 text-[11px] text-zinc-300 transition-colors hover:bg-surface-0 disabled:opacity-40"
                  >
                    {busy === `tpl-${template.template_id}` ? "Adding…" : "Add"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}

      {/* Agent list */}
      {agents.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="agents-empty">
          No agents defined yet — add agents like Planner, UI, Backend Coder, or Safety Reviewer.
          In v1.1 these are definitions and permissions only; nothing executes yet.
        </p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {agents.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              workspaceId={workspaceId}
              readOnly={readOnly}
              chatMode={chatMode}
              busy={busy}
              isEditing={editingId === agent.agent_id}
              onEdit={() =>
                setEditingId(editingId === agent.agent_id ? null : agent.agent_id)
              }
              onSaved={() => {
                setEditingId(null);
                agentsState.refetch(true);
              }}
              act={act}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

function AgentCard({
  agent,
  workspaceId,
  readOnly,
  chatMode,
  busy,
  isEditing,
  onEdit,
  onSaved,
  act,
}: {
  agent: WorkspaceAgent;
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
  busy: string | null;
  isEditing: boolean;
  onEdit: () => void;
  onSaved: () => void;
  act: (key: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;
  const granted = grantedPermissions(agent);
  const riskyGranted = granted.filter((k) => RISKY_PERMISSION_KEYS.has(k));
  const gated = agent.status === "quarantined" || agent.status === "disabled";
  const riskNotes = (agent.metadata.risk_notes as string[] | undefined) ?? [];

  return (
    <div
      data-testid="agent-card"
      className={`rounded-lg border px-3 py-2.5 transition-colors ${
        gated
          ? "border-edge bg-surface-2/40 opacity-70"
          : "border-edge bg-surface-2"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold text-zinc-100">{agent.name}</span>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-400">
          {agent.role}
        </span>
        <AgentStatusBadge status={agent.status} />
        {agent.requires_verification ? (
          <span className="rounded-md border border-sky-400/30 bg-sky-400/5 px-1.5 py-0.5 text-[10px] text-sky-300">
            verify required
          </span>
        ) : null}
        <span className="ml-auto font-mono text-[10.5px] text-zinc-500">
          {agent.model_provider} · {agent.model_name}
        </span>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-zinc-500">
        <span>
          trust <span className="font-mono text-emerald-300/90">{agent.trust_score.toFixed(2)}</span>
        </span>
        <span>
          risk{" "}
          <span className="font-mono text-red-300/90">{agent.risk_score.toFixed(2)}</span>
        </span>
      </div>

      {/* Permission badges */}
      {granted.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {granted.map((key) => {
            const risky = RISKY_PERMISSION_KEYS.has(key);
            return (
              <span
                key={key}
                data-testid={risky ? "risky-permission" : "permission"}
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  risky
                    ? "border border-amber-400/40 bg-amber-400/10 text-amber-300"
                    : "border border-edge bg-surface-0 text-zinc-400"
                }`}
              >
                {risky ? "⚠ " : ""}
                {permissionLabel(key)}
              </span>
            );
          })}
        </div>
      ) : null}

      {riskyGranted.length > 0 ? (
        <p className="mt-1.5 text-[10.5px] text-amber-400/90" data-testid="risky-warning">
          ⚠ {riskyGranted.length} sensitive permission{riskyGranted.length > 1 ? "s" : ""} —
          a future enforcement gateway will gate these.
        </p>
      ) : null}

      {riskNotes.length > 0 ? (
        <p className="mt-1 text-[10.5px] leading-4 text-zinc-600">{riskNotes.join(" ")}</p>
      ) : null}

      {agent.status === "quarantined" ? (
        <p className="mt-1 text-[10.5px] text-red-300/90" data-testid="quarantine-note">
          🔒 Quarantined — runtime actions (file writes, commands, task
          assignment/results) are blocked before execution.
          {agent.quarantine?.reason ? ` Reason: ${agent.quarantine.reason}` : ""}
          {agent.quarantine?.requested_by ? ` (by ${agent.quarantine.requested_by})` : ""}
        </p>
      ) : agent.status === "disabled" ? (
        <p className="mt-1 text-[10.5px] text-zinc-500" data-testid="gated-note">
          Disabled — excluded from task assignment.
        </p>
      ) : null}

      {!readOnly ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={disabled || busy !== null}
            title={hintTitle}
            onClick={onEdit}
            className="rounded-md border border-edge bg-surface-1 px-2 py-0.5 text-[10.5px] text-zinc-300 transition-colors hover:bg-surface-0 disabled:opacity-40"
          >
            {isEditing ? "Close" : "Edit"}
          </button>
          {agent.status === "quarantined" ? (
            <button
              type="button"
              data-testid="unquarantine-btn"
              disabled={disabled || busy !== null}
              title={hintTitle}
              onClick={() =>
                act(`unq-${agent.agent_id}`, () =>
                  api.unquarantineAgent(workspaceId, agent.agent_id, {}),
                )
              }
              className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10.5px] text-emerald-300 transition-colors hover:bg-emerald-400/20 disabled:opacity-40"
            >
              {busy === `unq-${agent.agent_id}` ? "…" : "Unquarantine"}
            </button>
          ) : (
            <button
              type="button"
              data-testid="quarantine-btn"
              disabled={disabled || busy !== null}
              title={hintTitle}
              onClick={() =>
                act(`q-${agent.agent_id}`, () =>
                  api.quarantineAgent(workspaceId, agent.agent_id, {
                    reason: "manually quarantined from the agents panel",
                  }),
                )
              }
              className="rounded-md border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10.5px] text-amber-300 transition-colors hover:bg-amber-400/20 disabled:opacity-40"
            >
              {busy === `q-${agent.agent_id}` ? "…" : "Quarantine"}
            </button>
          )}
          <button
            type="button"
            disabled={disabled || busy !== null}
            title={hintTitle}
            onClick={() =>
              act(`del-${agent.agent_id}`, () =>
                api.deleteWorkspaceAgent(workspaceId, agent.agent_id),
              )
            }
            className="rounded-md border border-red-400/25 bg-red-400/5 px-2 py-0.5 text-[10.5px] text-red-300/90 transition-colors hover:bg-red-400/15 disabled:opacity-40"
          >
            {busy === `del-${agent.agent_id}` ? "…" : "Delete"}
          </button>
        </div>
      ) : null}

      {isEditing ? (
        <AgentEditor
          agent={agent}
          workspaceId={workspaceId}
          onSaved={onSaved}
        />
      ) : null}
    </div>
  );
}

function AgentEditor({
  agent,
  workspaceId,
  onSaved,
}: {
  agent: WorkspaceAgent;
  workspaceId: string;
  onSaved: () => void;
}) {
  const [name, setName] = useState(agent.name);
  const [role, setRole] = useState(agent.role);
  const [status, setStatus] = useState<WorkspaceAgentStatus>(agent.status);
  const [requiresVerification, setRequiresVerification] = useState(
    agent.requires_verification,
  );
  const [permissions, setPermissions] = useState({ ...agent.permissions });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.patchWorkspaceAgent(workspaceId, agent.agent_id, {
        name: name.trim(),
        role: role.trim(),
        status,
        requires_verification: requiresVerification,
        permissions,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <div className="mt-2.5 space-y-2.5 rounded-md border border-edge bg-surface-0 p-2.5">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Name
          </span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded border border-edge bg-surface-2 px-2 py-1 text-[12px] text-zinc-200"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Role
          </span>
          <input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="rounded border border-edge bg-surface-2 px-2 py-1 text-[12px] text-zinc-200"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Status
          </span>
          <select
            aria-label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value as WorkspaceAgentStatus)}
            className="rounded border border-edge bg-surface-2 px-2 py-1 text-[12px] text-zinc-200"
          >
            {AGENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end pb-1 text-[11.5px] text-zinc-300">
          <input
            type="checkbox"
            checked={requiresVerification}
            onChange={(e) => setRequiresVerification(e.target.checked)}
          />
          Requires verification
        </label>
      </div>

      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Permissions
        </div>
        <div className="grid gap-x-3 gap-y-1 sm:grid-cols-2">
          {AGENT_PERMISSION_KEYS.map((key) => {
            const risky = RISKY_PERMISSION_KEYS.has(key);
            return (
              <label
                key={key}
                className={`flex items-center gap-2 text-[11px] ${
                  risky ? "text-amber-300/90" : "text-zinc-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={permissions[key]}
                  onChange={(e) =>
                    setPermissions((p) => ({ ...p, [key]: e.target.checked }))
                  }
                />
                {risky ? "⚠ " : ""}
                {permissionLabel(key)}
              </label>
            );
          })}
        </div>
      </div>

      {error ? <ErrorNote message={error} /> : null}
      <button
        type="button"
        disabled={saving || !name.trim()}
        onClick={save}
        className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-3 py-1 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
      >
        {saving ? "Saving…" : "Save agent"}
      </button>
    </div>
  );
}
