import { clsx } from "clsx";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { CostPanel } from "../components/costs/CostPanel";
import { InspectorPanel, type Selection } from "../components/inspector/InspectorPanel";
import { RunMetricsView } from "../components/metrics/RunMetricsView";
import { ReplayView } from "../components/replay/ReplayView";
import { EventTimeline } from "../components/timeline/EventTimeline";
import { TopologyView } from "../components/topology/TopologyView";
import { Badge, Card, ErrorNote, PageHeader, Spinner, StatusDot } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { useProjectStream } from "../hooks/useProjectStream";
import { api } from "../lib/api";
import { fmtCost, fmtDate, fmtNum, runDuration } from "../lib/format";
import { runStatus } from "../lib/status";
import type { AgentLabEvent } from "../lib/types";
import { useAppStore } from "../store/app";

type Tab = "topology" | "timeline" | "metrics" | "cost" | "replay";

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [tab, setTab] = useState<Tab>("topology");
  const [selection, setSelection] = useState<Selection>(null);
  const [events, setEvents] = useState<AgentLabEvent[]>([]);
  const [eventsLoaded, setEventsLoaded] = useState(false);

  const runState = useFetch(() => api.run(runId!), [runId]);
  const graphState = useFetch(() => api.runGraph(runId!), [runId]);
  const metricsState = useFetch(() => api.runMetrics(runId!), [runId]);
  const wsStatus = useAppStore((s) => s.wsStatus);

  useEffect(() => {
    let cancelled = false;
    setEventsLoaded(false);
    api
      .runEvents(runId!)
      .then((list) => {
        if (!cancelled) {
          setEvents(list);
          setEventsLoaded(true);
        }
      })
      .catch(() => setEventsLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Live updates: append instantly, then reconcile via silent refetch.
  const debounceRef = useRef<number | undefined>(undefined);
  const handleStreamEvent = useCallback(
    (event: AgentLabEvent) => {
      if (event.run_id !== runId) return;
      setEvents((prev) =>
        prev.some((e) => e.event_id === event.event_id) ? prev : [...prev, event],
      );
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        runState.refetch(true);
        graphState.refetch(true);
        metricsState.refetch(true);
        api.runEvents(runId!).then(setEvents).catch(() => undefined);
      }, 450);
    },
    [runId, runState.refetch, graphState.refetch, metricsState.refetch],
  );
  useProjectStream(runState.data?.project_id, handleStreamEvent);

  if (runState.loading) return <Spinner label="Loading run…" />;
  if (runState.error) return <ErrorNote message={runState.error} />;
  const run = runState.data;
  if (!run) return null;

  const status = runStatus(run.status);
  const live = run.status === "running";
  const totals = metricsState.data?.totals;

  const selectNode = (id: string | null) => setSelection(id ? { kind: "node", id } : null);
  const selectEdge = (id: string) => setSelection({ kind: "edge", id });
  const selectEvent = (event: AgentLabEvent) => setSelection({ kind: "event", event });

  const inspector = (
    <InspectorPanel
      selection={selection}
      events={events}
      nodes={graphState.data?.nodes ?? []}
      edges={graphState.data?.edges ?? []}
      projectId={run.project_id}
      runId={runId}
      onSelect={setSelection}
      onClose={() => setSelection(null)}
    />
  );

  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            {run.name ?? run.id}
            <Badge className={status.badge}>
              <StatusDot className={status.dot} pulse={live} />
              {status.label}
            </Badge>
            {live && wsStatus === "live" ? (
              <Badge className="border-emerald-400/40 bg-emerald-400/10 text-emerald-300">
                <StatusDot className="bg-emerald-400" pulse /> LIVE
              </Badge>
            ) : null}
          </span>
        }
        subtitle={
          <span className="font-mono text-[12px]">
            {run.id} ·{" "}
            <Link to={`/projects/${run.project_id}`} className="text-indigo-300 hover:underline">
              {run.project_id}
            </Link>{" "}
            · started {fmtDate(run.started_at)} · duration {runDuration(run)}
          </span>
        }
        actions={
          <div className="flex gap-2 text-center">
            <HeaderStat label="agents" value={String(run.agent_count ?? "—")} />
            <HeaderStat label="msgs" value={String(run.message_count ?? "—")} />
            <HeaderStat label="events" value={fmtNum(run.event_count)} />
            <HeaderStat
              label="errors"
              value={String(run.error_count)}
              danger={run.error_count > 0}
            />
            <HeaderStat label="tokens" value={fmtNum(totals?.tokens ?? run.total_tokens)} />
            <HeaderStat
              label="cost"
              value={fmtCost(totals?.cost_estimate ?? run.total_cost_estimate)}
            />
          </div>
        }
      />

      <div className="mb-4 flex gap-1 border-b border-edge">
        {(["topology", "timeline", "metrics", "cost", "replay"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={clsx(
              "-mb-px rounded-t-lg border-b-2 px-4 py-2 text-[13px] font-medium capitalize transition-colors",
              tab === key
                ? "border-indigo-400 text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-300",
            )}
          >
            {key === "cost" ? "Cost & Tokens" : key}
          </button>
        ))}
      </div>

      {tab === "topology" ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
          <Card className="h-[620px] overflow-hidden">
            {graphState.data ? (
              <TopologyView
                graph={graphState.data}
                live={live}
                selectedNodeId={selection?.kind === "node" ? selection.id : null}
                selectedEdgeId={selection?.kind === "edge" ? selection.id : null}
                onSelectNode={selectNode}
                onSelectEdge={selectEdge}
              />
            ) : graphState.error ? (
              <ErrorNote message={graphState.error} />
            ) : (
              <Spinner label="Building topology…" />
            )}
          </Card>
          <div className="h-[620px]">{inspector}</div>
        </div>
      ) : null}

      {tab === "timeline" ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
          <Card className="flex h-[620px] flex-col overflow-hidden">
            {eventsLoaded ? (
              <EventTimeline
                events={events}
                selectedEventId={selection?.kind === "event" ? selection.event.event_id : null}
                onSelect={selectEvent}
                followLive={live}
                maxHeightClass="max-h-none"
              />
            ) : (
              <Spinner label="Loading events…" />
            )}
          </Card>
          <div className="h-[620px]">{inspector}</div>
        </div>
      ) : null}

      {tab === "cost" ? <CostPanel runId={runId!} /> : null}

      {tab === "replay" ? (
        <ReplayView runId={runId!} projectId={run.project_id} runStatus={run.status} />
      ) : null}

      {tab === "metrics" ? (
        metricsState.data ? (
          <RunMetricsView metrics={metricsState.data} events={events} projectId={run.project_id} runId={runId} />
        ) : metricsState.error ? (
          <ErrorNote message={metricsState.error} />
        ) : (
          <Spinner label="Computing metrics…" />
        )
      ) : null}
    </>
  );
}

function HeaderStat({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="min-w-[64px] rounded-lg border border-edge bg-surface-1 px-2.5 py-1.5">
      <div className={clsx("font-mono text-[13px] font-semibold", danger ? "text-red-300" : "text-zinc-200")}>
        {value}
      </div>
      <div className="text-[9.5px] uppercase tracking-wider text-zinc-600">{label}</div>
    </div>
  );
}
