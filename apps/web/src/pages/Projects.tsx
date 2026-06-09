import { Link } from "react-router-dom";

import { Card, EmptyState, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import { fmtDate, timeAgo } from "../lib/format";

export function ProjectsPage() {
  const { data: projects, loading, error } = useFetch(() => api.projects(), []);

  if (loading) return <Spinner label="Loading projects…" />;
  if (error) return <ErrorNote message={error} />;

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle="Each project is an isolated stream of agent telemetry"
      />
      {!projects || projects.length === 0 ? (
        <EmptyState title="No projects yet">
          Projects are created automatically when the first event arrives with a new{" "}
          <code className="font-mono text-zinc-400">project_id</code>.
        </EmptyState>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link key={project.id} to={`/projects/${project.id}`}>
              <Card className="h-full px-4 py-4 transition-colors hover:border-edge-strong hover:bg-surface-2">
                <div className="text-[15px] font-semibold text-zinc-100">{project.name}</div>
                <div className="mt-0.5 font-mono text-[11px] text-zinc-600">{project.id}</div>
                {project.description ? (
                  <p className="mt-2 line-clamp-2 text-[12.5px] text-zinc-500">
                    {project.description}
                  </p>
                ) : null}
                <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[11px]">
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">{project.run_count}</div>
                    <div className="text-zinc-600">runs</div>
                  </div>
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">{project.agent_count}</div>
                    <div className="text-zinc-600">agents</div>
                  </div>
                  <div className="rounded-md bg-surface-2 px-2 py-1.5">
                    <div className="font-mono text-[13px] text-zinc-200">
                      {timeAgo(project.last_activity_at)}
                    </div>
                    <div className="text-zinc-600">activity</div>
                  </div>
                </div>
                <div className="mt-3 text-[11px] text-zinc-600">
                  created {fmtDate(project.created_at)}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
