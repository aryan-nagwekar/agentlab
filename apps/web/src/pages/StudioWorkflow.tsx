import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { AgentEditor } from "../components/studio/AgentEditor";
import { EdgeEditor } from "../components/studio/EdgeEditor";
import { RunPanel } from "../components/studio/RunPanel";
import { StudioCanvas } from "../components/studio/StudioCanvas";
import { Badge, Card, ErrorNote, SectionLabel, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import type {
  StudioAgent,
  StudioEdge,
  StudioValidation,
  StudioWorkflow,
} from "../lib/types";

export function StudioWorkflowPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Workflows created from a template carry ?template=<id> so the run panel
  // can start from the template's default input.
  const templateId = searchParams.get("template");
  const workflowState = useFetch(() => api.studioWorkflow(workflowId!), [workflowId]);
  const providersState = useFetch(() => api.providers(), []);
  const runsState = useFetch(() => api.studioWorkflowRuns(workflowId!), [workflowId]);
  const templateState = useFetch(
    () => (templateId ? api.studioTemplate(templateId) : Promise.resolve(null)),
    [templateId],
  );

  // Local editable copy of the stored definition.
  const [name, setName] = useState("");
  const [agents, setAgents] = useState<StudioAgent[]>([]);
  const [edges, setEdges] = useState<StudioEdge[]>([]);
  const [loadedFrom, setLoadedFrom] = useState<StudioWorkflow | null>(null);
  const [dirty, setDirty] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [validation, setValidation] = useState<StudioValidation | null>(null);

  useEffect(() => {
    const workflow = workflowState.data;
    if (workflow && workflow !== loadedFrom) {
      setName(workflow.name);
      setAgents(workflow.agents);
      setEdges(workflow.edges);
      setLoadedFrom(workflow);
      setDirty(false);
    }
  }, [workflowState.data, loadedFrom]);

  const providers = providersState.data?.providers ?? [];
  const unconfiguredProviders = useMemo(() => {
    const configured = new Set(providers.filter((p) => p.configured).map((p) => p.name));
    return [...new Set(agents.map((a) => a.provider).filter((p) => !configured.has(p)))];
  }, [agents, providers]);

  const touch = () => {
    setDirty(true);
    setValidation(null);
  };

  const updateAgent = (next: StudioAgent) => {
    setAgents((current) => current.map((a) => (a.agent_id === next.agent_id ? next : a)));
    touch();
  };

  const addAgent = () => {
    const base = `agent-${agents.length + 1}`;
    let id = base;
    let n = 2;
    while (agents.some((a) => a.agent_id === id)) id = `${base}-${n++}`;
    const agent: StudioAgent = {
      agent_id: id,
      name: `Agent ${agents.length + 1}`,
      role: "assistant",
      provider: "mock",
      model_name: "mock:claude-sonnet",
      temperature: 0.2,
      max_tokens: 1000,
      position_x: 120 + agents.length * 40,
      position_y: 80 + agents.length * 60,
    };
    setAgents((current) => [...current, agent]);
    setSelectedAgentId(id);
    setSelectedEdgeId(null);
    touch();
  };

  const deleteAgent = (agentId: string) => {
    setAgents((current) => current.filter((a) => a.agent_id !== agentId));
    setEdges((current) =>
      current.filter((e) => e.source_agent_id !== agentId && e.target_agent_id !== agentId),
    );
    setSelectedAgentId(null);
    touch();
  };

  const connectAgents = (source: string, target: string) => {
    if (edges.some((e) => e.source_agent_id === source && e.target_agent_id === target)) return;
    setEdges((current) => [
      ...current,
      { edge_id: `edge-${Math.random().toString(36).slice(2, 10)}`, source_agent_id: source, target_agent_id: target, label: null },
    ]);
    touch();
  };

  const save = async () => {
    setBusy("save");
    setActionError(null);
    try {
      const saved = await api.updateStudioWorkflow(workflowId!, {
        name,
        description: loadedFrom?.description ?? null,
        project_id: loadedFrom?.project_id ?? "demo-project",
        agents,
        edges,
      });
      setLoadedFrom(saved);
      setName(saved.name);
      setAgents(saved.agents);
      setEdges(saved.edges);
      setDirty(false);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const validate = async () => {
    setBusy("validate");
    setActionError(null);
    try {
      if (dirty) await save();
      setValidation(await api.validateStudioWorkflow(workflowId!));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete workflow “${name}”?`)) return;
    setBusy("delete");
    try {
      await api.deleteStudioWorkflow(workflowId!);
      navigate("/studio");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

  if (workflowState.loading || providersState.loading)
    return <Spinner label="Loading workflow…" />;
  if (workflowState.error) return <ErrorNote message={workflowState.error} />;

  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId) ?? null;
  const selectedEdge = edges.find((e) => e.edge_id === selectedEdgeId) ?? null;
  const lastRun = runsState.data?.[0] ?? null;

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/studio" className="text-[12px] text-zinc-500 hover:text-zinc-300">
          ← Studio
        </Link>
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            touch();
          }}
          className="min-w-[220px] rounded-lg border border-edge bg-surface-1 px-3 py-1.5 text-[15px] font-semibold text-zinc-100"
          aria-label="Workflow name"
        />
        {dirty ? <Badge className="border-amber-400/30 bg-amber-400/10 text-amber-300">unsaved</Badge> : null}
        <div className="ml-auto flex items-center gap-2">
          {lastRun ? (
            <Link
              to={`/runs/${lastRun.run_id}`}
              className="text-[11.5px] text-zinc-500 hover:text-zinc-300"
            >
              last run {lastRun.status} · {timeAgo(lastRun.created_at)} ↗
            </Link>
          ) : null}
          <button
            type="button"
            onClick={save}
            disabled={busy !== null || !dirty}
            className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
          >
            {busy === "save" ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            onClick={validate}
            disabled={busy !== null}
            className="rounded-lg border border-edge bg-surface-1 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-2 disabled:opacity-40"
          >
            {busy === "validate" ? "Validating…" : "Validate"}
          </button>
          <button
            type="button"
            onClick={addAgent}
            className="rounded-lg border border-edge bg-surface-1 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-2"
          >
            + Agent
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={busy !== null}
            className="rounded-lg border border-red-400/30 bg-red-400/10 px-3 py-1.5 text-[12px] text-red-300 transition-colors hover:bg-red-400/20 disabled:opacity-40"
          >
            Delete
          </button>
        </div>
      </div>

      {actionError ? <ErrorNote message={actionError} /> : null}
      {validation ? (
        <div
          className={`rounded-lg border px-3 py-2.5 text-[12px] leading-5 ${
            validation.valid
              ? "border-emerald-400/30 bg-emerald-400/5 text-emerald-200"
              : "border-red-400/30 bg-red-400/5 text-red-200"
          }`}
        >
          {validation.valid ? "Workflow is valid." : "Workflow is not valid:"}
          {validation.errors.map((error) => (
            <div key={error} className="mt-1 text-red-300">
              ✕ {error}
            </div>
          ))}
          {validation.warnings.map((warning) => (
            <div key={warning} className="mt-1 text-amber-200/90">
              ⚠ {warning}
            </div>
          ))}
        </div>
      ) : null}

      {/* Canvas + inspector */}
      <div className="flex min-h-0 flex-1 gap-4">
        <Card className="min-h-[420px] flex-1 overflow-hidden p-0">
          <StudioCanvas
            agents={agents}
            edges={edges}
            providers={providers}
            selectedAgentId={selectedAgentId}
            selectedEdgeId={selectedEdgeId}
            onSelectAgent={(id) => {
              setSelectedAgentId(id);
              if (id) setSelectedEdgeId(null);
            }}
            onSelectEdge={(id) => {
              setSelectedEdgeId(id);
              if (id) setSelectedAgentId(null);
            }}
            onMoveAgent={(id, x, y) => {
              setAgents((current) =>
                current.map((a) =>
                  a.agent_id === id ? { ...a, position_x: x, position_y: y } : a,
                ),
              );
              touch();
            }}
            onConnect={connectAgents}
          />
        </Card>
        <div className="w-[340px] shrink-0 space-y-4 overflow-y-auto">
          <Card className="px-4 py-4">
            {selectedAgent ? (
              <AgentEditor
                agent={selectedAgent}
                providers={providers}
                onChange={updateAgent}
                onDelete={() => deleteAgent(selectedAgent.agent_id)}
              />
            ) : selectedEdge ? (
              <EdgeEditor
                edge={selectedEdge}
                onChange={(next) => {
                  setEdges((current) =>
                    current.map((e) => (e.edge_id === next.edge_id ? next : e)),
                  );
                  touch();
                }}
                onDelete={() => {
                  setEdges((current) => current.filter((e) => e.edge_id !== selectedEdgeId));
                  setSelectedEdgeId(null);
                  touch();
                }}
              />
            ) : (
              <>
                <SectionLabel>Inspector</SectionLabel>
                <p className="text-[12px] leading-5 text-zinc-500">
                  Select an agent to edit its role, system prompt, provider and model — or drag
                  from an agent’s right handle to another agent to connect them.
                </p>
              </>
            )}
          </Card>
          <Card className="px-4 py-4">
            <RunPanel
              key={templateState.data?.default_input ?? "default"}
              workflowId={workflowId!}
              defaultInput={templateState.data?.default_input}
              dirty={dirty}
              unconfiguredProviders={unconfiguredProviders}
              onRunComplete={() => runsState.refetch(true)}
            />
          </Card>
          {runsState.data && runsState.data.length > 0 ? (
            <Card className="px-4 py-4">
              <SectionLabel>Run history</SectionLabel>
              <div className="space-y-1.5">
                {runsState.data.slice(0, 6).map((run) => (
                  <Link
                    key={run.run_id}
                    to={`/runs/${run.run_id}`}
                    className="flex items-center gap-2 rounded-md border border-edge bg-surface-2 px-2.5 py-1.5 text-[11.5px] transition-colors hover:border-edge-strong"
                  >
                    <span
                      className={
                        run.status === "completed" ? "text-emerald-300" : "text-red-300"
                      }
                    >
                      {run.status}
                    </span>
                    <span className="truncate font-mono text-zinc-500">{run.run_id}</span>
                    <span className="ml-auto shrink-0 text-zinc-600">{timeAgo(run.created_at)}</span>
                  </Link>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
