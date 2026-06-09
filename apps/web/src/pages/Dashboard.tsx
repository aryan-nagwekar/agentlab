import { Link } from "react-router-dom";

import { RunsTable } from "../components/RunsTable";
import {
  Card,
  CodeSnippet,
  EmptyState,
  ErrorNote,
  PageHeader,
  SectionLabel,
  Spinner,
  Stat,
} from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { Project, Run } from "../lib/types";

interface Overview {
  projects: Project[];
  recentRuns: Run[];
}

async function loadOverview(): Promise<Overview> {
  const projects = await api.projects();
  const runsByProject = await Promise.all(
    projects.slice(0, 6).map((project) => api.projectRuns(project.id, 10)),
  );
  const recentRuns = runsByProject
    .flat()
    .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""))
    .slice(0, 8);
  return { projects, recentRuns };
}

export function DashboardPage() {
  const { data, loading, error } = useFetch(loadOverview, []);

  if (loading) return <Spinner label="Loading fleet overview…" />;
  if (error) return <ErrorNote message={`Cannot reach the AgentLab API: ${error}`} />;
  if (!data) return null;

  const { projects, recentRuns } = data;
  const totalRuns = projects.reduce((sum, p) => sum + p.run_count, 0);
  const totalAgents = projects.reduce((sum, p) => sum + p.agent_count, 0);
  const lastActivity = projects
    .map((p) => p.last_activity_at)
    .filter(Boolean)
    .sort()
    .at(-1);

  if (projects.length === 0) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Observability for your agent fleet" />
        <EmptyState title="No agent activity yet">
          <p className="mb-4">
            Start the collector, then point an instrumented app at it — or seed the demo
            pipeline:
          </p>
          <div className="space-y-2 text-left">
            <CodeSnippet command="make demo" />
            <CodeSnippet command="python examples/basic_multi_agent/run_demo.py --fast" />
          </div>
        </EmptyState>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Observability for your agent fleet" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Projects" value={projects.length} />
        <Stat label="Runs" value={totalRuns} />
        <Stat label="Agents" value={totalAgents} />
        <Stat label="Last activity" value={timeAgo(lastActivity ?? null)} />
      </div>

      <div className="mt-7">
        <SectionLabel>Recent runs</SectionLabel>
        <RunsTable runs={recentRuns} showProject />
      </div>

      <div className="mt-7">
        <SectionLabel>Projects</SectionLabel>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link key={project.id} to={`/projects/${project.id}`}>
              <Card className="h-full px-4 py-3.5 transition-colors hover:border-edge-strong hover:bg-surface-2">
                <div className="font-medium text-zinc-100">{project.name}</div>
                <div className="mt-0.5 font-mono text-[11px] text-zinc-600">{project.id}</div>
                <div className="mt-3 flex gap-4 text-[12px] text-zinc-500">
                  <span>
                    <span className="font-mono text-zinc-300">{project.run_count}</span> runs
                  </span>
                  <span>
                    <span className="font-mono text-zinc-300">{project.agent_count}</span> agents
                  </span>
                  <span className="ml-auto">{timeAgo(project.last_activity_at)}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
