import { useCallback, useRef } from "react";
import { Link, useParams } from "react-router-dom";

import { RunsTable } from "../components/RunsTable";
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
import { useProjectStream } from "../hooks/useProjectStream";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import { agentStatus } from "../lib/status";

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { data, loading, error, refetch } = useFetch(
    () => api.project(projectId!),
    [projectId],
  );

  // Live: any event in this project silently refreshes the page data.
  const debounce = useRef<number | undefined>(undefined);
  const onEvent = useCallback(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => refetch(true), 500);
  }, [refetch]);
  useProjectStream(projectId, onEvent);

  if (loading) return <Spinner label="Loading project…" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const { project, runs, agents } = data;

  return (
    <>
      <PageHeader
        title={project.name}
        subtitle={
          <span className="font-mono text-[12px]">
            {project.id} · {project.run_count} runs · {project.agent_count} agents · active{" "}
            {timeAgo(project.last_activity_at)}
          </span>
        }
      />

      <SectionLabel>Agents</SectionLabel>
      <div className="mb-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {agents.map((agent) => {
          const style = agentStatus(agent.status);
          return (
            <Link key={agent.id} to={`/agents/${agent.id}?project=${project.id}`}>
              <Card className="h-full px-3.5 py-3 transition-colors hover:border-edge-strong hover:bg-surface-2">
                <div className="flex items-center gap-2">
                  <StatusDot className={style.dot} pulse={agent.status === "running"} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-semibold text-zinc-100">
                      {agent.name}
                    </div>
                    <div className="font-mono text-[10px] text-zinc-600">{agent.id}</div>
                  </div>
                  {agent.role ? <Badge>{agent.role}</Badge> : null}
                </div>
                <div className="mt-3">
                  <TrustBar value={agent.trust_score} />
                </div>
                <div className="mt-2 flex justify-between text-[10.5px] text-zinc-600">
                  <span>{style.label}</span>
                  <span>seen {timeAgo(agent.last_seen_at)}</span>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>

      <SectionLabel>Runs</SectionLabel>
      <RunsTable runs={runs} />
    </>
  );
}
