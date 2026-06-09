import type {
  Agent,
  AgentLabEvent,
  HealthInfo,
  Project,
  ProjectDetail,
  Run,
  RunGraph,
  RunMetrics,
} from "./types";

/** Same-origin by default (vite proxy in dev, nginx in Docker). */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText} — ${path}`);
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  health: () => request<HealthInfo>("/api/health"),
  projects: () => request<Project[]>("/api/projects"),
  project: (projectId: string) => request<ProjectDetail>(`/api/projects/${projectId}`),
  projectRuns: (projectId: string, limit = 100) =>
    request<Run[]>(`/api/projects/${projectId}/runs${query({ limit })}`),
  run: (runId: string) => request<Run>(`/api/runs/${runId}`),
  runEvents: (
    runId: string,
    params: { event_type?: string; agent_id?: string; limit?: number; offset?: number } = {},
  ) => request<AgentLabEvent[]>(`/api/runs/${runId}/events${query(params)}`),
  runGraph: (runId: string) => request<RunGraph>(`/api/runs/${runId}/graph`),
  runMetrics: (runId: string) => request<RunMetrics>(`/api/runs/${runId}/metrics`),
  agent: (agentId: string, projectId?: string) =>
    request<Agent>(`/api/agents/${agentId}${query({ project_id: projectId })}`),
  agentEvents: (agentId: string, projectId?: string, limit = 200) =>
    request<AgentLabEvent[]>(
      `/api/agents/${agentId}/events${query({ project_id: projectId, limit })}`,
    ),
};

export function wsUrl(path: string): string {
  const base = API_BASE || window.location.origin;
  return base.replace(/^http/, "ws") + path;
}
