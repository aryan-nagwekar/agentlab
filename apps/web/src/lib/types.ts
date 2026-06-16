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

// Workspace templates (v3.3) — one-click real workspace + agent team setup.
export interface WorkspaceTemplate {
  template_id: string;
  name: string;
  description: string;
  goal: string;
  agent_roles: string[];
  agent_count: number;
  tags: string[];
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
  // Quarantine bookkeeping (v1.7) — present while quarantined or after a lift.
  quarantine: AgentQuarantineInfo | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentQuarantineInfo {
  reason: string;
  requested_by: string;
  quarantined_at: string;
  source_action_id: string | null;
  source_approval_id: string | null;
  policy_rules: Array<{ id: string; name: string }>;
  previous_status: string;
  lifted_at: string | null;
  lifted_by: string | null;
  lift_reason: string | null;
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

// -------------------------------------------------- orchestration (v1.4)

export interface RuntimeWorkflow {
  workflow_id: string;
  workspace_id: string;
  goal: string;
  status:
    | "planned"
    | "running"
    | "paused"
    | "blocked"
    | "failed"
    | "completed"
    | "cancelled";
  created_by: string;
  task_count: number;
  completed_task_count: number;
  has_plan: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RuntimeWorkflowPlan {
  plan_id: string;
  workflow_id: string;
  summary: string;
  steps: Array<Record<string, unknown>>;
  dependencies: Record<string, number[]>;
  required_agents: string[];
  risk_assessment: string | null;
  validation_requirements: string[];
  approval_requirements: string[];
  created_at: string;
}

export interface RuntimeTaskResult {
  result_id: string;
  task_id: string;
  agent_id: string | null;
  output: string;
  artifacts: string[];
  validation_status: string;
  created_at: string;
}

export interface RuntimeTask {
  task_id: string;
  workflow_id: string;
  workspace_id: string;
  assigned_agent_id: string | null;
  assigned_agent_name: string | null;
  title: string;
  description: string | null;
  status: string;
  dependencies: string[];
  expected_artifacts: string[];
  risk_level: string;
  requires_validation: boolean;
  requires_approval: boolean;
  blocked_reason: string | null;
  latest_result: RuntimeTaskResult | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// --------------------------------------------------- enforcement (v1.5)

export type EnforcementDecision =
  | "allow"
  | "block"
  | "require_human_approval"
  | "reroute_to_verifier"
  | "retry_with_constraints"
  | "quarantine_agent"
  | "downgrade_permissions"
  | "allow_readonly"
  | "allow_sandbox_only";

export interface EnforcementDecisionRecord {
  decision_id: string;
  action_id: string;
  decision: EnforcementDecision;
  matched_rules: Array<{ id: string; name: string }>;
  trust_score_before: number | null;
  risk_score_before: number | null;
  reason: string;
  evidence: Record<string, unknown>;
  created_at: string;
  action_type: string;
  actor_type: string;
  target: string;
  action_status: string;
}

export interface RuntimePolicyRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
  action_types: string[];
  decision: EnforcementDecision;
  reason: string;
}

export interface RuntimeActionProposal {
  action_id: string;
  workspace_id: string;
  workflow_id: string | null;
  task_id: string | null;
  agent_id: string | null;
  actor_type: string;
  action_type: string;
  target: string;
  input_summary: string;
  sensitivity_level: string;
  expected_effect: string | null;
  requires_approval_hint: boolean;
  status: string;
  decision: Omit<
    EnforcementDecisionRecord,
    "action_type" | "actor_type" | "target" | "action_status"
  > | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

// ----------------------------------------------------- approvals (v1.6)

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "denied"
  | "expired"
  | "cancelled"
  | "rerouted"
  | "quarantine_requested";

export interface RuntimeApproval {
  approval_id: string;
  workspace_id: string;
  workflow_id: string | null;
  task_id: string | null;
  action_id: string;
  agent_id: string | null;
  title: string;
  plain_english_summary: string;
  technical_summary: string;
  risk_level: string;
  matched_policy_rules: Array<{ id: string; name: string }>;
  recommended_decision: string;
  options: string[];
  status: ApprovalStatus;
  action_type: string;
  target: string;
  resolution_decision: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_reason: string | null;
  execution_status: "not_executed" | "executed" | "execution_failed" | "skipped";
  execution_detail: string | null;
  created_at: string;
}

// ----------------------------------------------------- validators (v1.8)

export interface RuntimeValidatorInfo {
  type: string;
  description: string;
  target_type: string;
  inputs: string[];
}

export interface RuntimeValidatorResult {
  result_id: string;
  workspace_id: string;
  workflow_id: string | null;
  task_id: string | null;
  agent_id: string | null;
  validator_type: string;
  target_type: string;
  target_ref: string;
  passed: boolean;
  confidence: number;
  evidence: Record<string, unknown>;
  failures: string[];
  suggested_action: string | null;
  risk_delta: number;
  trust_delta: number;
  explanation: string;
  created_at: string;
}

// ----------------------------------------- bottle shop demo (v2.0)

export interface DemoSeedResult {
  workspace_id: string;
  workflow_id: string;
  agent_count: number;
  file_count: number;
  command_count: number;
  validator_result_ids: string[];
  pending_approval_id: string | null;
  goal: string;
}

// --------------------------------------- project debugging (v1.9)

export interface DebugHealth {
  state: string;
  label: string;
  severity: "high" | "medium" | "ok" | "none";
  active_labels: string[];
}

export interface DebugAction {
  action: string;
  label: string;
  link: string;
}

export interface DebugSummary {
  workspace_id: string;
  workspace_status: string;
  health: DebugHealth;
  recommended_actions: DebugAction[];
  counts: Record<string, number>;
  agents_overview: {
    total: number;
    by_status: Record<
      string,
      Array<{
        agent_id: string;
        name: string;
        role: string;
        trust_score: number;
        risk_score: number;
        current_assignment: string | null;
        restricted: boolean;
      }>
    >;
  };
  workflow_progress: {
    workflow_count: number;
    active_workflows: Array<{ workflow_id: string; goal: string; status: string }>;
    task_status_counts: Record<string, number>;
    blocked_tasks: Array<{ task_id: string; title: string; reason: string }>;
  };
  validation_summary: {
    total: number;
    failed: number;
    recent: Array<{
      result_id: string;
      validator_type: string;
      passed: boolean;
      target_ref: string;
      explanation: string;
      suggested_action: string | null;
    }>;
  };
  enforcement_summary: {
    pending_approvals: number;
    recent_decisions: Array<{
      decision_id: string;
      decision: string;
      action_type: string | null;
      reason: string;
      matched_rule: string;
    }>;
  };
  recent_changes: Array<{
    category: string;
    label: string;
    detail: string;
    event_type: string;
    timestamp: string | null;
    event_id: string;
  }>;
}

export interface DebugIssue {
  severity: "high" | "medium" | "low";
  kind: string;
  title: string;
  detail: string;
  suggested_action: string | null;
  link: string;
  ref: string;
}

export interface DebugMapNode {
  id: string;
  type: string;
  label: string;
  status: string | null;
  sublabel: string | null;
}

export interface DebugMap {
  nodes: DebugMapNode[];
  edges: Array<{ from: string; to: string; label: string | null }>;
}

// ----------------------------------------------- live agent build (v3.0)

export interface AgentBuildFile {
  path: string;
  status: "written" | "halted_for_approval" | "blocked";
  reason: string | null;
}

export interface AgentBuildResult {
  status: "completed" | "failed";
  agent_id: string;
  agent_name: string;
  provider: string;
  model: string;
  summary: string;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  files: AgentBuildFile[];
  written: number;
  halted_for_approval: number;
  blocked: number;
}

// ------------------------------------------- bounded agent loop (v3.1)

export type AgentRunActionStatus =
  | "written"
  | "completed"
  | "failed"
  | "timed_out"
  | "halted_for_approval"
  | "blocked"
  | "approved"
  | "denied";

export interface AgentRunCommand {
  command: string;
  status: AgentRunActionStatus;
  exit_code: number | null;
  reason?: string | null;
}

export interface AgentRunValidation {
  validator: string;
  target: string;
  passed: boolean;
}

export interface AgentRunFile {
  path: string;
  // adds "approved"/"denied" over AgentBuildFile once a held write is resolved
  status: AgentRunActionStatus;
  reason?: string | null;
}

export interface AgentRunStep {
  step: number;
  summary: string;
  status: "ok" | "failed";
  done: boolean;
  files: AgentRunFile[];
  commands: AgentRunCommand[];
  validations: AgentRunValidation[];
}

export interface AgentRunResult {
  status: "completed" | "failed" | "awaiting_approval" | "running";
  run_id: string;
  agent_id: string;
  agent_name: string;
  provider: string;
  model: string;
  goal: string;
  steps: AgentRunStep[];
  step_count: number;
  stop_reason: string;
  pending_approval_ids: string[];
  resumable: boolean;
  total_written: number;
  total_held: number;
  total_blocked: number;
  commands_run: number;
}

// Team build (v3.4) — Goal → Team: orchestrator plans, each agent builds its part.
export interface TeamBuildStep {
  agent_id: string;
  agent_name: string;
  role: string;
  task_id: string;
  task_title: string;
  kind: "build" | "contribute";
  status: "ok" | "failed";
  summary?: string | null;
  note?: string | null;
  files: AgentBuildFile[];
  validations: AgentRunValidation[];
}

export interface TeamBuildResult {
  status: "completed" | "failed";
  goal: string;
  workflow_id: string;
  stop_reason: string;
  steps: TeamBuildStep[];
  step_count: number;
  total_written: number;
  total_held: number;
  total_blocked: number;
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
