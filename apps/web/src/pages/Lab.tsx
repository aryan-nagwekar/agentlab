import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { RawJson } from "../components/JsonView";
import {
  Badge,
  Card,
  EmptyState,
  ErrorNote,
  PageHeader,
  SectionLabel,
  Spinner,
  StatusDot,
} from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { useProjectStream } from "../hooks/useProjectStream";
import { api } from "../lib/api";
import { fmtClock } from "../lib/format";
import { agentStatus } from "../lib/status";
import type { FaultInjectResult, FaultTemplate, GraphNode, RunGraph } from "../lib/types";

export function LabPage() {
  const projectsState = useFetch(() => api.projects(), []);
  const [projectId, setProjectId] = useState<string>("");
  const [runId, setRunId] = useState<string>("");
  const [lastResult, setLastResult] = useState<FaultInjectResult | null>(null);
  const [injectError, setInjectError] = useState<string | null>(null);
  const [busyFault, setBusyFault] = useState<string | null>(null);

  const projects = projectsState.data ?? [];
  useEffect(() => {
    if (!projectId && projects.length > 0) setProjectId(projects[0].id);
  }, [projects, projectId]);

  const runsState = useFetch(
    () => (projectId ? api.projectRuns(projectId, 25) : Promise.resolve([])),
    [projectId],
  );
  const runs = useMemo(() => runsState.data ?? [], [runsState.data]);
  useEffect(() => {
    if (runs.length > 0 && !runs.some((run) => run.id === runId)) setRunId(runs[0].id);
  }, [runs, runId]);

  const templatesState = useFetch(() => api.faultTemplates(), []);
  const graphState = useFetch(
    () => (runId ? api.runGraph(runId) : Promise.resolve(null as unknown as RunGraph)),
    [runId],
  );
  const faultsState = useFetch(
    () => (runId ? api.runFaults(runId) : Promise.resolve([])),
    [runId],
  );

  // Live: refresh agent states + fault log as events arrive on this project.
  const debounce = useRef<number | undefined>(undefined);
  const onStreamEvent = useCallback(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      graphState.refetch(true);
      faultsState.refetch(true);
    }, 400);
  }, [graphState.refetch, faultsState.refetch]);
  useProjectStream(projectId || undefined, onStreamEvent);

  const inject = useCallback(
    async (
      template: FaultTemplate,
      target: string,
      source: string | undefined,
      params: Record<string, unknown>,
    ) => {
      if (!runId) return;
      setBusyFault(template.fault_type);
      setInjectError(null);
      try {
        const result = await api.injectFault(runId, {
          fault_type: template.fault_type,
          target_agent_id: target,
          source_agent_id: source,
          params,
        });
        setLastResult(result);
        graphState.refetch(true);
        faultsState.refetch(true);
      } catch (error) {
        setInjectError(error instanceof Error ? error.message : String(error));
      } finally {
        setBusyFault(null);
      }
    },
    [runId, graphState.refetch, faultsState.refetch],
  );

  if (projectsState.loading) return <Spinner label="Loading lab…" />;
  if (projectsState.error) return <ErrorNote message={projectsState.error} />;

  const nodes = graphState.data?.nodes ?? [];
  const templates = templatesState.data ?? [];
  const agentFaults = templates.filter((t) => t.target_kind === "agent");
  const channelFaults = templates.filter((t) => t.target_kind === "channel");

  return (
    <>
      <PageHeader
        title="Fault Injection Lab"
        subtitle="Chaos-test agent systems with safe, simulated failures — watch the topology react, then replay the incident"
      />

      <Card className="mb-5 border-emerald-400/20 bg-emerald-400/5 px-4 py-3 text-[12.5px] leading-6 text-zinc-400">
        <span className="font-medium text-emerald-300">All faults are simulations.</span>{" "}
        Injection emits telemetry events (<code className="font-mono text-[11.5px]">fault.injected</code>{" "}
        + realistic follow-ups) through the normal pipeline — no real process is killed, no real
        network traffic is disrupted, no secrets are touched. Every lab event carries{" "}
        <code className="font-mono text-[11.5px]">safe_simulation: true</code>.
      </Card>

      {projects.length === 0 ? (
        <EmptyState title="No projects to test against">
          Seed the demo first: <code className="font-mono">make demo</code>
        </EmptyState>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-end gap-3">
            <LabSelect
              label="Project"
              value={projectId}
              onChange={setProjectId}
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
            />
            <LabSelect
              label="Target run"
              value={runId}
              onChange={setRunId}
              options={runs.map((r) => ({
                value: r.id,
                label: `${r.name ?? r.id} · ${r.status}`,
              }))}
            />
            {runId ? (
              <Link
                to={`/runs/${runId}`}
                className="mb-1 text-[12px] font-medium text-indigo-300 hover:text-indigo-200"
              >
                Open run →
              </Link>
            ) : null}
          </div>

          {nodes.length > 0 ? (
            <div className="mb-5 flex flex-wrap gap-2">
              {nodes.map((node) => {
                const style = agentStatus(node.status);
                return (
                  <Badge key={node.id} className="border-edge bg-surface-1 px-2.5 py-1">
                    <StatusDot className={style.dot} pulse={node.status === "running"} />
                    <span className="font-mono text-[11px] text-zinc-300">{node.id}</span>
                    <span className={`text-[10px] ${node.status === "failed" ? "text-red-300" : node.status === "overloaded" ? "text-orange-300" : "text-zinc-500"}`}>
                      {style.label.toLowerCase()}
                    </span>
                  </Badge>
                );
              })}
            </div>
          ) : null}

          {injectError ? (
            <div className="mb-4">
              <ErrorNote message={`Injection rejected: ${injectError}`} />
            </div>
          ) : null}
          {lastResult ? (
            <Card className="mb-5 border-rose-400/20 bg-rose-400/5 px-4 py-3 text-[12.5px] text-zinc-300">
              <span className="font-medium text-rose-300">
                ⚡ {lastResult.fault_type} injected
              </span>{" "}
              — {lastResult.events.length} events recorded (
              {lastResult.events.map((e) => e.event_type).join(" → ")}).{" "}
              <Link to={`/runs/${runId}`} className="font-medium text-indigo-300 hover:underline">
                Watch the run
              </Link>{" "}
              or jump into its <span className="text-zinc-400">Replay</span> tab and hit the{" "}
              <span className="text-rose-300">Fault</span> marker.
            </Card>
          ) : null}

          {runId && nodes.length === 0 && !graphState.loading ? (
            <EmptyState title="This run has no agents yet">
              Pick a run with participants, or seed the demo pipeline.
            </EmptyState>
          ) : null}

          {templatesState.loading || graphState.loading ? <Spinner /> : null}

          {nodes.length > 0 ? (
            <>
              <SectionLabel>Agent faults</SectionLabel>
              <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {agentFaults.map((template) => (
                  <FaultCard
                    key={`${template.fault_type}-${runId}`}
                    template={template}
                    nodes={nodes}
                    graph={graphState.data ?? null}
                    busy={busyFault === template.fault_type}
                    onInject={inject}
                  />
                ))}
              </div>

              <SectionLabel>Channel faults</SectionLabel>
              <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {channelFaults.map((template) => (
                  <FaultCard
                    key={`${template.fault_type}-${runId}`}
                    template={template}
                    nodes={nodes}
                    graph={graphState.data ?? null}
                    busy={busyFault === template.fault_type}
                    onInject={inject}
                  />
                ))}
              </div>
            </>
          ) : null}

          <SectionLabel>Fault log for this run</SectionLabel>
          <FaultLog faults={faultsState.data ?? []} />

          <Card className="mt-6 px-4 py-3 text-[12px] text-zinc-500">
            Coming in v0.4 (pending approval): sandboxed malicious-agent simulation — prompt
            injection messages, fake capability advertising, mock exfiltration attempts — plus the
            trust engine and quarantine flows.
          </Card>
        </>
      )}
    </>
  );
}

function LabSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-[220px] max-w-[340px] truncate rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function FaultCard({
  template,
  nodes,
  graph,
  busy,
  onInject,
}: {
  template: FaultTemplate;
  nodes: GraphNode[];
  graph: RunGraph | null;
  busy: boolean;
  onInject: (
    template: FaultTemplate,
    target: string,
    source: string | undefined,
    params: Record<string, unknown>,
  ) => void;
}) {
  const isChannel = template.target_kind === "channel";
  const firstEdge = graph?.edges[0];
  const [target, setTarget] = useState(
    isChannel ? (firstEdge?.target ?? nodes[0]?.id ?? "") : (nodes[0]?.id ?? ""),
  );
  const [source, setSource] = useState(firstEdge?.source ?? nodes[0]?.id ?? "");
  const [params, setParams] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(template.params.map((p) => [p.name, p.default])),
  );

  const agentOptions = nodes.map((node) => (
    <option key={node.id} value={node.id}>
      {node.id}
    </option>
  ));
  const selectClass =
    "w-full rounded-md border border-edge bg-surface-2 px-2 py-1 font-mono text-[11.5px] text-zinc-200";

  return (
    <Card className="flex flex-col px-3.5 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[13px] font-semibold text-zinc-100">{template.label}</div>
        <Badge>{isChannel ? "channel" : "agent"}</Badge>
      </div>
      <p className="mt-1 text-[11.5px] leading-5 text-zinc-500">{template.description}</p>

      <div className="mt-3 space-y-2">
        {isChannel ? (
          <div className="flex items-center gap-1.5">
            <select className={selectClass} value={source} onChange={(e) => setSource(e.target.value)} aria-label="Channel source">
              {agentOptions}
            </select>
            <span className="text-zinc-600">→</span>
            <select className={selectClass} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Channel target">
              {agentOptions}
            </select>
          </div>
        ) : (
          <select className={selectClass} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Target agent">
            {agentOptions}
          </select>
        )}

        {template.params.map((param) => (
          <label key={param.name} className="flex items-center gap-2 text-[11px] text-zinc-500">
            <span className="w-24 shrink-0 truncate font-mono">{param.name}</span>
            <input
              type={param.type === "number" ? "number" : "text"}
              step="any"
              value={String(params[param.name] ?? "")}
              onChange={(event) =>
                setParams((current) => ({
                  ...current,
                  [param.name]:
                    param.type === "number" ? Number(event.target.value) : event.target.value,
                }))
              }
              className="w-full rounded-md border border-edge bg-surface-0 px-2 py-1 font-mono text-[11.5px] text-zinc-300"
            />
          </label>
        ))}
      </div>

      <button
        type="button"
        disabled={busy || !target || (isChannel && !source)}
        onClick={() => onInject(template, target, isChannel ? source : undefined, params)}
        className="mt-3 rounded-lg border border-rose-400/40 bg-rose-400/10 px-3 py-1.5 text-[12px] font-medium text-rose-300 transition-colors hover:border-rose-400/70 hover:bg-rose-400/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Injecting…" : "⚡ Inject fault"}
      </button>
      <div className="mt-2 truncate font-mono text-[9.5px] text-zinc-600" title={template.emits.join(" → ")}>
        emits: {template.emits.join(" → ")}
      </div>
    </Card>
  );
}

function FaultLog({ faults }: { faults: import("../lib/types").AgentLabEvent[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (faults.length === 0) {
    return (
      <Card className="px-4 py-6 text-center text-[12.5px] text-zinc-600">
        No faults injected into this run yet.
      </Card>
    );
  }
  return (
    <Card className="divide-y divide-edge/60">
      {faults.map((fault) => {
        const payload = fault.payload as Record<string, unknown>;
        const open = expanded === fault.event_id;
        return (
          <div key={fault.event_id} className="px-4 py-2.5">
            <button
              type="button"
              onClick={() => setExpanded(open ? null : fault.event_id)}
              className="flex w-full items-center gap-3 text-left"
            >
              <span className="font-mono text-[10.5px] text-zinc-500">
                {fmtClock(fault.timestamp)}
              </span>
              <Badge className="border-rose-400/40 bg-rose-400/10 text-rose-300">
                {String(payload.fault_type ?? fault.event_type)}
              </Badge>
              <span className="truncate font-mono text-[11px] text-zinc-400">
                {fault.source_agent_id} → {fault.target_agent_id ?? "—"}
              </span>
              <span className="truncate text-[11.5px] text-zinc-500">
                {String(payload.reason ?? "")}
              </span>
              <span className="ml-auto text-[11px] text-zinc-600">{open ? "▲" : "▼"}</span>
            </button>
            {open ? (
              <div className="mt-2">
                <RawJson value={fault} />
              </div>
            ) : null}
          </div>
        );
      })}
    </Card>
  );
}
