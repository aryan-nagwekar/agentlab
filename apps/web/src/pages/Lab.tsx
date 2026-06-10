import { clsx } from "clsx";
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
import type {
  AgentLabEvent,
  AttackTemplate,
  FaultTemplate,
  GraphNode,
  RunGraph,
} from "../lib/types";

type LabMode = "faults" | "security";

interface Banner {
  tone: "fault" | "attack";
  text: string;
  chain: string[];
}

const SEVERITY_STYLE: Record<string, string> = {
  low: "border-zinc-500/40 bg-zinc-500/10 text-zinc-300",
  medium: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  high: "border-orange-400/40 bg-orange-400/10 text-orange-300",
  critical: "border-rose-400/40 bg-rose-400/10 text-rose-300",
};

export function LabPage() {
  const projectsState = useFetch(() => api.projects(), []);
  const [projectId, setProjectId] = useState<string>("");
  const [runId, setRunId] = useState<string>("");
  const [mode, setMode] = useState<LabMode>("faults");
  const [banner, setBanner] = useState<Banner | null>(null);
  const [injectError, setInjectError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

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

  const faultTemplates = useFetch(() => api.faultTemplates(), []);
  const attackTemplates = useFetch(() => api.attackTemplates(), []);
  const graphState = useFetch(
    () => (runId ? api.runGraph(runId) : Promise.resolve(null as unknown as RunGraph)),
    [runId],
  );
  const faultsState = useFetch(
    () => (runId ? api.runFaults(runId) : Promise.resolve([])),
    [runId],
  );
  const attacksState = useFetch(
    () => (runId ? api.runAttacks(runId) : Promise.resolve([])),
    [runId],
  );

  const debounce = useRef<number | undefined>(undefined);
  const onStreamEvent = useCallback(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      graphState.refetch(true);
      faultsState.refetch(true);
      attacksState.refetch(true);
    }, 400);
  }, [graphState.refetch, faultsState.refetch, attacksState.refetch]);
  useProjectStream(projectId || undefined, onStreamEvent);

  const refreshAfterInject = useCallback(() => {
    graphState.refetch(true);
    faultsState.refetch(true);
    attacksState.refetch(true);
  }, [graphState.refetch, faultsState.refetch, attacksState.refetch]);

  const injectFault = useCallback(
    async (
      template: FaultTemplate,
      target: string,
      source: string | undefined,
      params: Record<string, unknown>,
    ) => {
      if (!runId) return;
      setBusy(template.fault_type);
      setInjectError(null);
      try {
        const result = await api.injectFault(runId, {
          fault_type: template.fault_type,
          target_agent_id: target,
          source_agent_id: source,
          params,
        });
        setBanner({
          tone: "fault",
          text: `⚡ ${result.fault_type} injected`,
          chain: result.events.map((e) => e.event_type),
        });
        refreshAfterInject();
      } catch (error) {
        setInjectError(error instanceof Error ? error.message : String(error));
      } finally {
        setBusy(null);
      }
    },
    [runId, refreshAfterInject],
  );

  const injectAttack = useCallback(
    async (
      template: AttackTemplate,
      attacker: string,
      victim: string | undefined,
      params: Record<string, unknown>,
    ) => {
      if (!runId) return;
      setBusy(template.attack_type);
      setInjectError(null);
      try {
        const result = await api.injectAttack(runId, {
          attack_type: template.attack_type,
          attacker_agent_id: attacker,
          target_agent_id: victim,
          params,
        });
        setBanner({
          tone: "attack",
          text: `🛑 ${result.attack_type} simulated`,
          chain: result.events.map((e) => e.event_type),
        });
        refreshAfterInject();
      } catch (error) {
        setInjectError(error instanceof Error ? error.message : String(error));
      } finally {
        setBusy(null);
      }
    },
    [runId, refreshAfterInject],
  );

  if (projectsState.loading) return <Spinner label="Loading lab…" />;
  if (projectsState.error) return <ErrorNote message={projectsState.error} />;

  const nodes = graphState.data?.nodes ?? [];

  return (
    <>
      <PageHeader
        title="Lab"
        subtitle="Chaos-test and attack-test agent systems with safe, simulated events — watch the topology react, then replay the incident"
      />

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
              options={runs.map((r) => ({ value: r.id, label: `${r.name ?? r.id} · ${r.status}` }))}
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

          <div className="mb-5 inline-flex rounded-lg border border-edge bg-surface-1 p-1">
            <ModeButton active={mode === "faults"} onClick={() => setMode("faults")}>
              ⚗ Fault Injection
            </ModeButton>
            <ModeButton active={mode === "security"} onClick={() => setMode("security")}>
              🛡 Security Lab
            </ModeButton>
          </div>

          {mode === "faults" ? (
            <Card className="mb-5 border-emerald-400/20 bg-emerald-400/5 px-4 py-3 text-[12.5px] leading-6 text-zinc-400">
              <span className="font-medium text-emerald-300">All faults are simulations.</span>{" "}
              Injection emits telemetry events (<code className="font-mono text-[11.5px]">fault.injected</code>{" "}
              + realistic follow-ups) through the normal pipeline — no real process is killed, no
              real network traffic is disrupted, no secrets are touched.
            </Card>
          ) : (
            <Card className="mb-5 border-emerald-400/20 bg-emerald-400/5 px-4 py-3 text-[12.5px] leading-6 text-zinc-400">
              <span className="font-medium text-emerald-300">Safe cyber range — everything is simulated.</span>{" "}
              Attacks emit <code className="font-mono text-[11.5px]">attack.injected</code> + mock
              follow-up events. <span className="text-zinc-300">No real secrets, files, systems, or
              networks are touched.</span> Every payload uses <code className="font-mono text-[11.5px]">MOCK_*</code>{" "}
              placeholders and is tagged <code className="font-mono text-[11.5px]">safe_simulation: true</code>{" "}
              with <code className="font-mono text-[11.5px]">real_secrets_accessed: false</code>.
            </Card>
          )}

          {nodes.length > 0 ? (
            <div className="mb-5 flex flex-wrap gap-2">
              {nodes.map((node) => {
                const style = agentStatus(node.status);
                const danger =
                  node.status === "failed" || node.status === "quarantined" || node.status === "suspicious";
                return (
                  <Badge key={node.id} className="border-edge bg-surface-1 px-2.5 py-1">
                    <StatusDot className={style.dot} pulse={node.status === "running"} />
                    <span className="font-mono text-[11px] text-zinc-300">{node.id}</span>
                    <span className={clsx("text-[10px]", danger ? "text-amber-300" : "text-zinc-500")}>
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
          {banner ? (
            <Card
              className={clsx(
                "mb-5 px-4 py-3 text-[12.5px]",
                banner.tone === "attack"
                  ? "border-fuchsia-400/20 bg-fuchsia-400/5 text-zinc-300"
                  : "border-rose-400/20 bg-rose-400/5 text-zinc-300",
              )}
            >
              <span className={banner.tone === "attack" ? "font-medium text-fuchsia-300" : "font-medium text-rose-300"}>
                {banner.text}
              </span>{" "}
              — {banner.chain.length} events ({banner.chain.join(" → ")}).{" "}
              <Link to={`/runs/${runId}`} className="font-medium text-indigo-300 hover:underline">
                Watch the run
              </Link>{" "}
              or open its <span className="text-zinc-400">Replay</span> tab and hit the{" "}
              <span className={banner.tone === "attack" ? "text-fuchsia-300" : "text-rose-300"}>
                {banner.tone === "attack" ? "Attack" : "Fault"}
              </span>{" "}
              marker.
            </Card>
          ) : null}

          {runId && nodes.length === 0 && !graphState.loading ? (
            <EmptyState title="This run has no agents yet">
              Pick a run with participants, or seed the demo pipeline.
            </EmptyState>
          ) : null}

          {mode === "faults"
            ? renderFaults(faultTemplates.data ?? [], nodes, graphState.data ?? null, busy, injectFault, faultsState.data ?? [], runId)
            : renderSecurity(attackTemplates.data ?? [], nodes, busy, injectAttack, attacksState.data ?? [], runId)}
        </>
      )}
    </>
  );
}

function renderFaults(
  templates: FaultTemplate[],
  nodes: GraphNode[],
  graph: RunGraph | null,
  busy: string | null,
  onInject: (t: FaultTemplate, target: string, source: string | undefined, p: Record<string, unknown>) => void,
  faults: AgentLabEvent[],
  runId: string,
) {
  if (nodes.length === 0) return null;
  const agentFaults = templates.filter((t) => t.target_kind === "agent");
  const channelFaults = templates.filter((t) => t.target_kind === "channel");
  return (
    <>
      <SectionLabel>Agent faults</SectionLabel>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {agentFaults.map((t) => (
          <FaultCard key={`${t.fault_type}-${runId}`} template={t} nodes={nodes} graph={graph} busy={busy === t.fault_type} onInject={onInject} />
        ))}
      </div>
      <SectionLabel>Channel faults</SectionLabel>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {channelFaults.map((t) => (
          <FaultCard key={`${t.fault_type}-${runId}`} template={t} nodes={nodes} graph={graph} busy={busy === t.fault_type} onInject={onInject} />
        ))}
      </div>
      <SectionLabel>Fault log for this run</SectionLabel>
      <EventLog events={faults} kind="fault" />
    </>
  );
}

function renderSecurity(
  templates: AttackTemplate[],
  nodes: GraphNode[],
  busy: string | null,
  onInject: (t: AttackTemplate, attacker: string, victim: string | undefined, p: Record<string, unknown>) => void,
  attacks: AgentLabEvent[],
  runId: string,
) {
  if (nodes.length === 0) return null;
  return (
    <>
      <SectionLabel>Malicious-agent attacks (simulated)</SectionLabel>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {templates.map((t) => (
          <AttackCard key={`${t.attack_type}-${runId}`} template={t} nodes={nodes} busy={busy === t.attack_type} onInject={onInject} />
        ))}
      </div>
      <SectionLabel>Attack log for this run</SectionLabel>
      <EventLog events={attacks} kind="attack" />
      <Card className="mt-6 px-4 py-3 text-[12px] text-zinc-500">
        Coming in v0.5 (pending approval): an event-driven trust/risk engine with automatic
        quarantine thresholds and explainable routing decisions.
      </Card>
    </>
  );
}

function ModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors",
        active ? "bg-surface-3 text-zinc-100" : "text-zinc-500 hover:text-zinc-300",
      )}
    >
      {children}
    </button>
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

const SELECT_CLASS =
  "w-full rounded-md border border-edge bg-surface-2 px-2 py-1 font-mono text-[11.5px] text-zinc-200";

function ParamInputs({
  params,
  values,
  onChange,
}: {
  params: Array<{ name: string; type: string; default?: unknown }>;
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  return (
    <>
      {params.map((param) => (
        <label key={param.name} className="flex items-center gap-2 text-[11px] text-zinc-500">
          <span className="w-24 shrink-0 truncate font-mono">{param.name}</span>
          {param.type === "boolean" ? (
            <input
              type="checkbox"
              checked={Boolean(values[param.name])}
              onChange={(e) => onChange({ ...values, [param.name]: e.target.checked })}
              className="accent-rose-400"
            />
          ) : (
            <input
              type={param.type === "number" ? "number" : "text"}
              step="any"
              value={String(values[param.name] ?? "")}
              onChange={(e) =>
                onChange({
                  ...values,
                  [param.name]: param.type === "number" ? Number(e.target.value) : e.target.value,
                })
              }
              className="w-full rounded-md border border-edge bg-surface-0 px-2 py-1 font-mono text-[11.5px] text-zinc-300"
            />
          )}
        </label>
      ))}
    </>
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
  onInject: (t: FaultTemplate, target: string, source: string | undefined, p: Record<string, unknown>) => void;
}) {
  const isChannel = template.target_kind === "channel";
  const firstEdge = graph?.edges[0];
  const [target, setTarget] = useState(isChannel ? (firstEdge?.target ?? nodes[0]?.id ?? "") : (nodes[0]?.id ?? ""));
  const [source, setSource] = useState(firstEdge?.source ?? nodes[0]?.id ?? "");
  const [params, setParams] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(template.params.map((p) => [p.name, p.default])),
  );
  // Clamp to current participants (the run can change under us).
  const effTarget = nodes.some((n) => n.id === target) ? target : (nodes[0]?.id ?? "");
  const effSource = nodes.some((n) => n.id === source) ? source : (nodes[0]?.id ?? "");
  const agentOptions = nodes.map((n) => (
    <option key={n.id} value={n.id}>
      {n.id}
    </option>
  ));

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
            <select className={SELECT_CLASS} value={effSource} onChange={(e) => setSource(e.target.value)} aria-label="Channel source">
              {agentOptions}
            </select>
            <span className="text-zinc-600">→</span>
            <select className={SELECT_CLASS} value={effTarget} onChange={(e) => setTarget(e.target.value)} aria-label="Channel target">
              {agentOptions}
            </select>
          </div>
        ) : (
          <select className={SELECT_CLASS} value={effTarget} onChange={(e) => setTarget(e.target.value)} aria-label="Target agent">
            {agentOptions}
          </select>
        )}
        <ParamInputs params={template.params} values={params} onChange={setParams} />
      </div>
      <button
        type="button"
        disabled={busy || !effTarget || (isChannel && !effSource)}
        onClick={() => onInject(template, effTarget, isChannel ? effSource : undefined, params)}
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

function AttackCard({
  template,
  nodes,
  busy,
  onInject,
}: {
  template: AttackTemplate;
  nodes: GraphNode[];
  busy: boolean;
  onInject: (t: AttackTemplate, attacker: string, victim: string | undefined, p: Record<string, unknown>) => void;
}) {
  const needsVictim = template.target_kind === "agent";
  const [attacker, setAttacker] = useState("malicious-agent");
  const firstVictim = nodes.find((n) => n.id !== "malicious-agent")?.id ?? nodes[0]?.id ?? "";
  const [victim, setVictim] = useState(firstVictim);
  const [params, setParams] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(template.params.map((p) => [p.name, p.default])),
  );
  // Clamp to a valid participant: the run's nodes can change under us (async
  // graph refetch) so never submit a stale victim from a previous run.
  const effectiveVictim = nodes.some((n) => n.id === victim) ? victim : firstVictim;

  return (
    <Card className="flex flex-col px-3.5 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[13px] font-semibold text-zinc-100">{template.label}</div>
        <Badge className={SEVERITY_STYLE[template.severity] ?? SEVERITY_STYLE.medium}>
          {template.severity}
        </Badge>
      </div>
      <p className="mt-1 text-[11.5px] leading-5 text-zinc-500">{template.description}</p>

      <div className="mt-2 rounded-md border border-edge bg-surface-0 px-2 py-1.5">
        <div className="text-[9px] uppercase tracking-wider text-zinc-600">mock payload</div>
        <div className="mt-0.5 truncate font-mono text-[10px] text-amber-300/80" title={template.mock_payload}>
          {template.mock_payload}
        </div>
      </div>

      <div className="mt-2.5 space-y-2">
        <label className="flex items-center gap-2 text-[11px] text-zinc-500">
          <span className="w-16 shrink-0 font-mono">attacker</span>
          <input
            value={attacker}
            onChange={(e) => setAttacker(e.target.value)}
            className="w-full rounded-md border border-edge bg-surface-0 px-2 py-1 font-mono text-[11.5px] text-zinc-300"
          />
        </label>
        {needsVictim ? (
          <label className="flex items-center gap-2 text-[11px] text-zinc-500">
            <span className="w-16 shrink-0 font-mono">victim</span>
            <select className={SELECT_CLASS} value={effectiveVictim} onChange={(e) => setVictim(e.target.value)} aria-label="Victim agent">
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.id}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <ParamInputs params={template.params} values={params} onChange={setParams} />
      </div>

      <button
        type="button"
        disabled={busy || !attacker || (needsVictim && !effectiveVictim)}
        onClick={() => onInject(template, attacker, needsVictim ? effectiveVictim : undefined, params)}
        className="mt-3 rounded-lg border border-fuchsia-400/40 bg-fuchsia-400/10 px-3 py-1.5 text-[12px] font-medium text-fuchsia-300 transition-colors hover:border-fuchsia-400/70 hover:bg-fuchsia-400/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Simulating…" : "🛑 Inject attack"}
      </button>
      <div className="mt-2 truncate font-mono text-[9.5px] text-zinc-600" title={template.emits.join(" → ")}>
        emits: {template.emits.join(" → ")}
      </div>
    </Card>
  );
}

function EventLog({ events, kind }: { events: AgentLabEvent[]; kind: "fault" | "attack" }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const typeKey = kind === "fault" ? "fault_type" : "attack_type";
  const accent = kind === "attack" ? "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-300" : "border-rose-400/40 bg-rose-400/10 text-rose-300";
  if (events.length === 0) {
    return (
      <Card className="px-4 py-6 text-center text-[12.5px] text-zinc-600">
        No {kind === "fault" ? "faults" : "attacks"} injected into this run yet.
      </Card>
    );
  }
  return (
    <Card className="divide-y divide-edge/60">
      {events.map((event) => {
        const payload = event.payload as Record<string, unknown>;
        const open = expanded === event.event_id;
        return (
          <div key={event.event_id} className="px-4 py-2.5">
            <button
              type="button"
              onClick={() => setExpanded(open ? null : event.event_id)}
              className="flex w-full items-center gap-3 text-left"
            >
              <span className="font-mono text-[10.5px] text-zinc-500">{fmtClock(event.timestamp)}</span>
              <Badge className={accent}>{String(payload[typeKey] ?? event.event_type)}</Badge>
              <span className="truncate font-mono text-[11px] text-zinc-400">
                {event.source_agent_id} → {event.target_agent_id ?? "—"}
              </span>
              <span className="truncate text-[11.5px] text-zinc-500">
                {String(payload.description ?? payload.reason ?? "")}
              </span>
              <span className="ml-auto text-[11px] text-zinc-600">{open ? "▲" : "▼"}</span>
            </button>
            {open ? (
              <div className="mt-2">
                <RawJson value={event} />
              </div>
            ) : null}
          </div>
        );
      })}
    </Card>
  );
}
