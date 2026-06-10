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
  attacks: number;
  flagged_messages: number;
  suspicious_agents: number;
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
  faults: number[];
  attacks: number[];
}

export interface FaultTemplate {
  fault_type: string;
  label: string;
  description: string;
  target_kind: "agent" | "channel" | string;
  params: Array<{ name: string; type: string; default?: unknown }>;
  emits: string[];
}

export interface FaultInjectRequest {
  fault_type: string;
  target_agent_id?: string;
  source_agent_id?: string;
  params?: Record<string, unknown>;
  reason?: string;
}

export interface FaultInjectResult {
  fault_event_id: string;
  fault_type: string;
  events: AgentLabEvent[];
}

export interface AttackTemplate {
  attack_type: string;
  label: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  target_kind: "agent" | "network" | string;
  params: Array<{ name: string; type: string; default?: unknown }>;
  emits: string[];
  mock_payload: string;
}

export interface AttackInjectRequest {
  attack_type: string;
  attacker_agent_id?: string;
  target_agent_id?: string;
  params?: Record<string, unknown>;
  description?: string;
}

export interface AttackInjectResult {
  attack_event_id: string;
  attack_type: string;
  events: AgentLabEvent[];
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
