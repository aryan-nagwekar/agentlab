import type {
  Agent,
  AgentLabEvent,
  AgentScore,
  AttackInjectRequest,
  AttackInjectResult,
  AttackTemplate,
  FaultInjectRequest,
  FaultInjectResult,
  FaultTemplate,
  HealthInfo,
  Project,
  ProjectDetail,
  ModelCallResult,
  ModelTestCallRequest,
  Provider,
  Run,
  RunCost,
  RunGraph,
  RunMetrics,
  RunReplay,
  RunRiskSummary,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail) detail = ` — ${JSON.stringify(body.detail)}`;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(
      response.status,
      `${response.status} ${response.statusText} — ${path}${detail}`,
    );
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
  runReplay: (runId: string, limit = 5000) =>
    request<RunReplay>(`/api/runs/${runId}/replay${query({ limit })}`),
  replayGraphAt: (runId: string, index: number) =>
    request<RunGraph>(`/api/runs/${runId}/replay/graph${query({ index })}`),
  runMetrics: (runId: string) => request<RunMetrics>(`/api/runs/${runId}/metrics`),
  agent: (agentId: string, projectId?: string) =>
    request<Agent>(`/api/agents/${agentId}${query({ project_id: projectId })}`),
  agentEvents: (agentId: string, projectId?: string, limit = 200) =>
    request<AgentLabEvent[]>(
      `/api/agents/${agentId}/events${query({ project_id: projectId, limit })}`,
    ),
  faultTemplates: () => request<FaultTemplate[]>("/api/lab/fault-templates"),
  runFaults: (runId: string) => request<AgentLabEvent[]>(`/api/runs/${runId}/faults`),
  injectFault: (runId: string, body: FaultInjectRequest) =>
    request<FaultInjectResult>(`/api/runs/${runId}/faults`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  attackTemplates: () => request<AttackTemplate[]>("/api/lab/attack-templates"),
  runAttacks: (runId: string) => request<AgentLabEvent[]>(`/api/runs/${runId}/attacks`),
  injectAttack: (runId: string, body: AttackInjectRequest) =>
    request<AttackInjectResult>(`/api/runs/${runId}/attacks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  runRiskSummary: (runId: string) =>
    request<RunRiskSummary>(`/api/runs/${runId}/risk-summary`),
  runCosts: (runId: string) => request<RunCost>(`/api/runs/${runId}/costs`),
  providers: () => request<{ providers: Provider[] }>("/api/model-gateway/providers"),
  testCall: (body: ModelTestCallRequest) =>
    request<ModelCallResult>("/api/model-gateway/test-call", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  agentScores: (agentId: string, projectId?: string, runId?: string) =>
    request<AgentScore>(
      `/api/agents/${agentId}/scores${query({ project_id: projectId, run_id: runId })}`,
    ),
};

export function wsUrl(path: string): string {
  const base = API_BASE || window.location.origin;
  return base.replace(/^http/, "ws") + path;
}
