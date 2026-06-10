/** Mirrors apps/api/app/schemas.py — the dashboard's wire contract. */

export interface AgentLabEvent {
  id: number;
  event_id: string;
  event_type: string;
  timestamp: string;
  project_id: string;
  run_id: string;
  source_agent_id: string | null;
  target_agent_id: string | null;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface Run {
  id: string;
  project_id: string;
  name: string | null;
  status: "running" | "completed" | "failed" | string;
  started_at: string | null;
  completed_at: string | null;
  total_latency_ms: number | null;
  total_cost_estimate: number | null;
  total_tokens: number | null;
  error_count: number;
  agent_count: number | null;
  message_count: number | null;
  event_count: number | null;
}

export interface Agent {
  project_id: string;
  id: string;
  name: string;
  role: string | null;
  description: string | null;
  status: string;
  trust_score: number;
  risk_score: number;
  created_at: string | null;
  last_seen_at: string | null;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string | null;
  run_count: number;
  agent_count: number;
  last_activity_at: string | null;
}

export interface ProjectDetail {
  project: Project;
  runs: Run[];
  agents: Agent[];
}

export interface GraphNode {
  id: string;
  name: string;
  role: string | null;
  status: string;
  trust_score: number;
  risk_score: number;
  messages_in: number;
  messages_out: number;
  tool_calls: number;
  errors: number;
  avg_latency_ms: number | null;
  tokens: number;
  cost_estimate: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  message_count: number;
  avg_latency_ms: number | null;
  last_status: string | null;
  last_message_at: string | null;
}

export interface RunGraph {
  run_id: string;
  project_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface MetricsTotals {
  agents: number;
  messages: number;
  tool_calls: number;
  model_calls: number;
  events: number;
  tokens: number;
  cost_estimate: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  error_count: number;
  error_rate: number;
  duration_ms: number | null;
}

export interface AgentMetrics {
  agent_id: string;
  name: string;
  role: string | null;
  messages: number;
  tool_calls: number;
  model_calls: number;
  tokens: number;
  cost_estimate: number;
  avg_latency_ms: number | null;
  errors: number;
  trust_score: number;
}

export interface Highlight {
  agent_id: string;
  name: string;
  value: number;
  unit: string;
}

export interface RunMetrics {
  run_id: string;
  totals: MetricsTotals;
  per_agent: AgentMetrics[];
  highlights: Record<string, Highlight | null>;
}

export interface ReplayMarkers {
  errors: number[];
  tool_calls: number[];
  routing: number[];
  messages: number[];
}

export interface RunReplay {
  run_id: string;
  project_id: string;
  status: string;
  name: string | null;
  event_count: number;
  duration_ms: number | null;
  markers: ReplayMarkers;
  events: AgentLabEvent[];
}

export interface HealthInfo {
  status: string;
  service: string;
  version: string;
}
