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
  avg_trust: number | null;
  avg_risk: number | null;
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
  risk_score: number;
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

export interface ScoreChange {
  agent_id: string;
  event_index: number;
  caused_by_event_id: string | null;
  caused_by_event_type: string;
  previous_trust: number;
  new_trust: number;
  previous_risk: number;
  new_risk: number;
  trust_delta: number;
  risk_delta: number;
  reason: string;
}

export interface ScoreFactor {
  event_type: string;
  count: number;
  trust_delta: number;
  risk_delta: number;
}

export interface AgentScore {
  agent_id: string;
  name: string | null;
  status: string;
  trust_score: number;
  risk_score: number;
  tier: string;
  latest_reason: string | null;
  trust_factors: ScoreFactor[];
  risk_factors: ScoreFactor[];
  history: ScoreChange[];
}

export interface RunScores {
  run_id: string;
  scoring_version: string;
  agents: AgentScore[];
}

export interface RiskSummaryAgent {
  agent_id: string;
  name: string | null;
  trust_score: number;
  risk_score: number;
  tier: string;
}

export interface RunRiskSummary {
  run_id: string;
  highest_risk_agent: RiskSummaryAgent | null;
  lowest_trust_agent: RiskSummaryAgent | null;
  avg_trust: number | null;
  avg_risk: number | null;
  suspicious_agents: number;
  quarantined_agents: number;
  flagged_messages: number;
  attack_events: number;
  fault_events: number;
}

export interface AgentCost {
  agent_id: string;
  agent_name: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  average_latency_ms: number | null;
  p95_latency_ms: number | null;
  model_call_count: number;
  failed_model_calls: number;
  retry_count: number;
  most_used_model: string | null;
}

export interface ModelCost {
  model_name: string;
  provider: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  call_count: number;
  failure_count: number;
  average_latency_ms: number | null;
}

export interface RunCost {
  run_id: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  average_latency_ms: number | null;
  p95_latency_ms: number | null;
  most_expensive_agent: string | null;
  most_token_heavy_agent: string | null;
  slowest_agent: string | null;
  highest_failure_agent: string | null;
  model_breakdown: ModelCost[];
  agent_breakdown: AgentCost[];
}

export interface Provider {
  name: string;
  configured: boolean;
  status: string; // available | not_configured | unavailable | error
  requires_key: boolean;
  models: string[];
  key_redacted: string | null;
  // Health/troubleshooting hint from the server (never contains a key).
  message?: string | null;
}

export interface ModelTestCallRequest {
  provider: string;
  model_name: string;
  prompt: string;
  agent_id?: string;
  project_id?: string;
  run_id?: string;
  simulate_failure?: boolean;
}

export interface ModelCallResult {
  provider: string;
  model_name: string;
  output_text: string;
  status: string;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: number | null;
  latency_ms: number;
  error_message: string | null;
  event_id: string | null;
}

export interface ProviderHealth {
  name: string;
  status: string;
  configured: boolean;
  detail: string | null;
  key_redacted: string | null;
}

// ------------------------------------------------------------ studio (v0.8)

export interface StudioAgent {
  agent_id: string;
  workflow_id?: string;
  name: string;
  role: string;
  description?: string | null;
  system_prompt?: string | null;
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  position_x: number;
  position_y: number;
  metadata?: Record<string, unknown>;
}

export interface StudioEdge {
  edge_id: string;
  workflow_id?: string;
  source_agent_id: string;
  target_agent_id: string;
  label?: string | null;
  metadata?: Record<string, unknown>;
}

export interface StudioWorkflow {
  workflow_id: string;
  project_id: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  agents: StudioAgent[];
  edges: StudioEdge[];
}

export interface StudioWorkflowSummary {
  workflow_id: string;
  project_id: string;
  name: string;
  description?: string | null;
  agent_count: number;
  edge_count: number;
  updated_at: string;
  last_run_id: string | null;
  last_run_status: string | null;
}

export interface StudioWorkflowSave {
  name: string;
  description?: string | null;
  project_id: string;
  agents: Omit<StudioAgent, "workflow_id">[];
  edges: Omit<StudioEdge, "workflow_id">[];
}

export interface StudioValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface StudioRunResult {
  workflow_id: string;
  run_id: string;
  status: string;
  open_run_url: string;
}

export interface StudioTemplateSummary {
  template_id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  difficulty: string;
  use_case: string;
  agent_count: number;
}

export interface StudioTemplateAgent {
  agent_id: string;
  name: string;
  role: string;
  description: string;
  system_prompt: string;
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  position_x: number;
  position_y: number;
}

export interface StudioTemplateEdge {
  source_agent_name: string;
  target_agent_name: string;
  source_agent_id: string;
  target_agent_id: string;
  label: string;
}

export interface StudioTemplate extends StudioTemplateSummary {
  default_input: string;
  agents: StudioTemplateAgent[];
  edges: StudioTemplateEdge[];
  expected_outputs: string[];
  demo_notes: string;
}

export interface StudioTemplateCreateResult {
  workflow_id: string;
  template_id: string;
  open_url: string;
}

export interface StudioRunRecord {
  run_id: string;
  workflow_id: string;
  project_id: string;
  status: string;
  input: string | null;
  created_at: string;
}

// ----------------------------------------------------------- runtime (v1.0)

export type WorkspaceStatus =
  | "draft"
  | "active"
  | "paused"
  | "completed"
  | "archived"
  | "failed";

export interface RuntimeWorkspace {
  workspace_id: string;
  name: string;
  goal: string | null;
  status: WorkspaceStatus;
  project_id: string;
  activity_run_id: string;
  metadata: Record<string, unknown>;
  artifact_count: number;
  agent_count: number;
  created_at: string;
  updated_at: string;
}

// ------------------------------------------------- workspace agents (v1.1)

export type WorkspaceAgentStatus =
  | "ready"
  | "running"
  | "caution"
  | "suspicious"
  | "quarantined"
  | "disabled";

/** Canonical permission flags — mirrors AGENT_PERMISSION_KEYS in the API. */
export const AGENT_PERMISSION_KEYS = [
  "can_read_files",
  "can_write_files",
  "can_delete_files",
  "can_run_commands",
  "can_call_web",
  "can_access_database",
  "can_modify_auth",
  "can_modify_payment",
  "can_modify_deployment",
  "can_send_to_agents",
  "can_send_to_user",
  "can_save_product_data",
  "can_use_unverified_research",
] as const;

export type AgentPermissionKey = (typeof AGENT_PERMISSION_KEYS)[number];

/** Permissions a future enforcement gateway will gate — surfaced with a warning. */
export const RISKY_PERMISSION_KEYS: ReadonlySet<AgentPermissionKey> = new Set([
  "can_write_files",
  "can_delete_files",
  "can_run_commands",
  "can_access_database",
  "can_modify_auth",
  "can_modify_payment",
  "can_modify_deployment",
]);

export type AgentPermissions = Record<AgentPermissionKey, boolean>;

export interface WorkspaceAgent {
  agent_id: string;
  workspace_id: string;
  name: string;
  role: string;
  description: string | null;
  system_prompt: string | null;
  model_provider: string;
  model_name: string;
  allowed_tools: string[];
  denied_tools: string[];
  permissions: AgentPermissions;
  max_tokens_per_call: number;
  max_calls_per_run: number;
  max_tool_calls_per_run: number;
  requires_verification: boolean;
  trust_score: number;
  risk_score: number;
  status: WorkspaceAgentStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ------------------------------------------------- sandbox files (v1.2)

export interface SandboxStatus {
  workspace_id: string;
  initialized: boolean;
  file_count: number;
  directory_count: number;
  total_bytes: number;
}

/** Logical workspace-relative entries — host paths never reach the client. */
export interface SandboxFileEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  size_bytes: number;
  modified_at: number | null;
  children?: SandboxFileEntry[] | null;
}

export interface SandboxFileRead {
  path: string;
  content: string;
  size_bytes: number;
  sha256: string;
}

export interface SandboxFileWriteResult {
  path: string;
  size_bytes: number;
  sha256: string;
  created: boolean;
}

// ----------------------------------------------- sandbox commands (v1.3)

export interface SandboxCommandResult {
  command: string;
  argv: string[];
  /** Logical workspace path ("." = sandbox root) — never a host path. */
  cwd: string;
  status: "completed" | "failed" | "timed_out";
  exit_code: number | null;
  duration_ms: number;
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
}

export interface AllowedCommand {
  command: string;
  description: string;
  examples: string[];
}

export interface WorkspaceAgentTemplate {
  template_id: string;
  name: string;
  role: string;
  description: string;
  system_prompt: string;
  model_provider: string;
  model_name: string;
  permissions: AgentPermissions;
  allowed_tools: string[];
  denied_tools: string[];
  max_tokens_per_call: number;
  max_calls_per_run: number;
  max_tool_calls_per_run: number;
  requires_verification: boolean;
  trust_score: number;
  risk_score: number;
  status: WorkspaceAgentStatus;
  risk_notes: string[];
  future_approval_required: string[];
}

export interface RuntimeArtifact {
  artifact_id: string;
  workspace_id: string;
  name: string;
  type: string;
  path: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface HealthInfo {
  status: string;
  service: string;
  version: string;
}
