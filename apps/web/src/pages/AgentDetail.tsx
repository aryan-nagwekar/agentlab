import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { EventDetail } from "../components/inspector/EventDetail";
import { EventTimeline } from "../components/timeline/EventTimeline";
import { RawJson } from "../components/JsonView";
import {
  Badge,
  Card,
  ErrorNote,
  PageHeader,
  SectionLabel,
  Spinner,
  StatusDot,
  TrustBar,
} from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { fmtDate, timeAgo } from "../lib/format";
import { agentStatus } from "../lib/status";
import type { AgentLabEvent } from "../lib/types";

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("project") ?? undefined;
  const [selected, setSelected] = useState<AgentLabEvent | null>(null);

  const agentState = useFetch(() => api.agent(agentId!, projectId), [agentId, projectId]);
  const eventsState = useFetch(
    () => api.agentEvents(agentId!, projectId, 300),
    [agentId, projectId],
  );

  if (agentState.loading) return <Spinner label="Loading agent…" />;
  if (agentState.error) return <ErrorNote message={agentState.error} />;
  const agent = agentState.data;
  if (!agent) return null;

  const style = agentStatus(agent.status);
  // API returns newest-first; the timeline reads best oldest-first.
  const events = [...(eventsState.data ?? [])].reverse();

  return (
    <>
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
            <StatusDot className={style.dot} pulse={agent.status === "running"} />
            {agent.name}
            <Badge className={style.badge}>{style.label}</Badge>
            {agent.role ? <Badge>{agent.role}</Badge> : null}
          </span>
        }
        subtitle={
          <span className="font-mono text-[12px]">
            {agent.project_id} / {agent.id} · first seen {fmtDate(agent.created_at)} · last seen{" "}
            {timeAgo(agent.last_seen_at)}
          </span>
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <Card className="px-4 py-3">
          <SectionLabel>Trust score</SectionLabel>
          <TrustBar value={agent.trust_score} />
        </Card>
        <Card className="px-4 py-3">
          <SectionLabel>Risk score</SectionLabel>
          <div className="flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
              <div
                className="h-full rounded-full bg-rose-400"
                style={{ width: `${Math.round(agent.risk_score * 100)}%` }}
              />
            </div>
            <span className="font-mono text-[11px] text-zinc-400">
              {agent.risk_score.toFixed(2)}
            </span>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_400px]">
        <div>
          <SectionLabel>Recent events (all runs)</SectionLabel>
          <Card className="overflow-hidden">
            {eventsState.loading ? (
              <Spinner />
            ) : (
              <EventTimeline
                events={events}
                selectedEventId={selected?.event_id ?? null}
                onSelect={setSelected}
                maxHeightClass="max-h-[620px]"
              />
            )}
          </Card>
        </div>
        <div>
          <SectionLabel>{selected ? "Event inspector" : "Agent record"}</SectionLabel>
          <Card className="overflow-hidden">
            {selected ? (
              <div className="h-[660px]">
                <EventDetail event={selected} allEvents={events} onSelectEvent={setSelected} />
              </div>
            ) : (
              <div className="p-3">
                <RawJson value={agent} />
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
