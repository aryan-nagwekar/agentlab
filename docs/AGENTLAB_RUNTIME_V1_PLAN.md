# AgentLab Runtime v1 — Master Plan

> Provided in full by the project owner on 2026-06-12, replacing the earlier
> partial save of this document. This is the long-term master roadmap for the
> Runtime phase. Implementation proceeds one version at a time, each gated on
> explicit owner approval.
>
> Status cross-check at time of saving:
>
> - v0.1–v0.9.1 (observability, replay, fault/security labs, trust/risk,
>   cost/token profiler, model gateway + BYOK, Studio, templates, Chat/Agent
>   mode) — ✅ shipped
> - v1.0 Runtime Workspaces — ✅ shipped (Milestone 1, metadata-only form)
> - v1.1 Workspace Agent Definitions + Permissions — ✅ shipped (Milestone 2,
>   metadata-only form; no execution)
> - v1.2 Sandboxed File Runtime — ✅ shipped (Milestone 3, file operations
>   only)
> - v1.3 Safe Command Runner + Sandbox Events — ✅ shipped (Milestone 3,
>   command portion: allowlisted, deterministic, pre-execution blocking;
>   NOT the enforcement gateway — no dev servers, long-running processes,
>   package installs, or policy engine)
> - v1.4 Orchestration Engine — ✅ shipped (Milestone 4: deterministic
>   planner, role-based assignment honoring quarantined/disabled gating,
>   dependency-respecting lifecycle, manual text results, replayable
>   runtime.workflow.*/runtime.task.* events; **status metadata only — no
>   autonomous file/command/model execution**)
> - v1.5 Action Enforcement Gateway — ✅ shipped (Milestone 5: ActionProposal
>   → deterministic policy evaluation → explainable ActionDecision before
>   execution; integrated into files/commands/workflows with v1.2/v1.3
>   safety as defense in depth; approval_required/quarantine_triggered/
>   rerouted/retry decisions are RECORDED EVENTS ONLY — no approval inbox,
>   no validators, no real quarantine, no autonomous execution)
> - v1.6 Human Approval System — ✅ shipped (Milestone 7: approval_required
>   decisions create pending ApprovalRequests; approve resumes the EXACT
>   stored action through the v1.2/v1.3 safe executors (their safety
>   re-runs), deny blocks, approve_readonly runs/skips a read-only path,
>   reroute/quarantine RECORD events/metadata only — no real quarantine
>   restriction, no validators, no autonomous execution)
> - **v1.7 Real Runtime Quarantine — next, gated on owner approval (separate
>   spec to be provided)**
> - Milestones 6/8–12 remainder (real quarantine, deterministic validators,
>   visual debugging, bottle-selling demo, gateway/cost integration, full
>   testing) — not started, gated on owner approval
>
> The plan text below is preserved verbatim as provided by the owner.

---

You are working inside the AgentLab repository.
This is a serious product evolution task. Do not treat this as a quick feature request. Read the existing repository carefully before making changes. Preserve everything that already works. Build incrementally, test aggressively, and keep the architecture clean.

============================================================ CURRENT COMPLETED STATE

AgentLab is no longer only a basic observability prototype. The following capabilities are already completed and should be treated as existing foundation:

* Python SDK — zero-dependency instrumentation for agents, messages, tools, models, routing, and trust
* Event collector — FastAPI collector with validated event schema and idempotent ingest
* Storage — append-only event log with relational projections using PostgreSQL / SQLite
* Live dashboard — dark-mode infrastructure UI with per-project WebSocket streaming
* Agent topology — React Flow graph with status rings, trust bars, per-node stats, and labeled message edges
* Wireshark-style inspector — payload/metadata trees, parent-child event links, and raw JSON
* Run metrics — tokens, cost, avg/p95 latency, error rate, per-agent table, and superlatives
* Demo workflow — 5-agent pipeline with success, retry, and failure scenarios, no real LLM keys required
* Replay debugger — play/pause/step/scrub any run; jump to next error, tool call, routing decision, or fault; topology and inspector reconstruct at each cursor position
* Fault injection lab — kill, overload, tool failure, model timeout, message delay, and message drop; injected from UI; graph reacts live; every fault is replayable; currently simulated
* Security Lab — simulated malicious-agent attacks including prompt injection, mock exfiltration, fake capabilities, spam, trust poisoning, routing manipulation, unsafe tool request, and rogue join; all mock data, nothing real touched
* Trust/risk engine — deterministic, event-derived, explainable trust/risk scores with tiers, score history, factor explanations, run risk summary, and replay evolution
* Cost/token profiler — deterministic local pricing, per-agent/per-model/per-run token and USD attribution, expensive/token-heavy/slow/failed-call rankings, model-call inspector, cost accumulation in replay
* Model gateway + BYOK — real model gateway and bring-your-own-key support for OpenAI, Anthropic, Gemini, and Ollama

Do not rebuild these systems from scratch. Build on top of them.

The current system can observe, replay, score, inspect, and profile agent behavior. The next major product leap is to let users build projects inside AgentLab itself and have AgentLab orchestrate, validate, enforce, and visually explain what the agents are doing.

============================================================ TARGET PRODUCT VISION

Evolve AgentLab from:

OBSERVABILITY + REPLAY + SCORING + MODEL GATEWAY

into:

SANDBOXED AGENT PROJECT BUILDER + ORCHESTRATION ENGINE + ENFORCEMENT CONTROL PLANE + VISUAL DEBUGGING RUNTIME

The final product should allow a user to:

1. Create a software project inside AgentLab.
2. Connect existing BYOK/model gateway providers.
3. Create specialized agents such as Planner, UI Agent, Backend Coder, Researcher, Marketing Agent, Verifier, and Safety Reviewer.
4. Give the agents a goal, such as “build an e-commerce website that sells water bottles.”
5. Let AgentLab orchestrate the work across agents.
6. Let agents generate files, run commands, call tools, research, edit project artifacts, and propose changes inside a controlled sandbox.
7. Stream every action into the existing event log.
8. Enforce policy before risky actions execute.
9. Validate claims, code, runtime behavior, and data flow using deterministic validators.
10. Reroute hallucinating or low-trust agents to verifier agents.
11. Require human approval for risky actions.
12. Quarantine agents in a real runtime sense, not just visually.
13. Show nontechnical users what is happening through simple visuals.
14. Let technical users drill into raw logs, events, traces, policies, and replay.
15. Preserve the existing Wireshark-style replay and trust/risk explainability.

The product should feel like:

* Replit/Lovable-style AI project creation
* plus Wireshark-style replay
* plus Sentry/Datadog-style debugging
* plus agent trust/risk scoring
* plus policy enforcement
* plus human approval gates
* plus a sandboxed safety runtime for vibe-coded software

One-line thesis:

AgentLab lets anyone build software with AI agents while visually understanding, debugging, validating, and safely controlling every action those agents take.

============================================================ TARGET USERS

AgentLab is not only for professional AI engineers.

Primary user groups:

1. AI-native builders / vibe coders: People using Claude Code, Codex, ChatGPT, Cursor, Replit, Lovable, or similar tools to generate apps, but who do not deeply understand frontend, backend, databases, auth, payments, APIs, deployment, or code architecture.
2. Nontechnical founders: People who can describe a product idea but cannot debug the generated code when something breaks.
3. Students and solo builders: People learning software by building with AI.
4. Agencies and freelancers: People generating client projects with AI who need visibility, safety, and debugging.
5. Technical teams: Teams deploying multi-agent workflows that need observability, policy, audit logs, and runtime control.

The product should make generated software understandable.

The pain point: AI can generate software quickly, but users often do not know:

* what the AI changed
* why something broke
* which agent caused the issue
* whether frontend/backend/database are connected correctly
* whether a researcher agent hallucinated
* whether a coder agent touched risky code
* whether it is safe to approve a change
* whether deployment/payment/auth/database actions are dangerous

AgentLab should solve this by turning invisible AI work into visual, replayable, enforceable system behavior.

============================================================ NON-NEGOTIABLE ARCHITECTURE PRINCIPLES

1. Raw events remain the source of truth.
2. All runtime, orchestration, validation, approval, and enforcement decisions must emit events.
3. Replay must be able to reconstruct not only what agents did, but what AgentLab allowed, blocked, rerouted, or quarantined.
4. Deterministic validation should be preferred over LLM judgment for safety-critical decisions.
5. LLM verifier agents may explain, summarize, or assist, but they must not be the only authority for blocking or allowing high-risk actions.
6. Enforcement decisions must be explainable with matched policy rules and evidence.
7. Secret values must never appear in raw events, frontend state, logs, traces, replay payloads, screenshots, or test snapshots.
8. Existing BYOK/model gateway must be reused.
9. Existing cost/token profiler must continue working with runtime/orchestrated model calls.
10. Existing trust/risk scoring must continue working and should be extended, not replaced.
11. Quarantine must become real runtime behavior, not just a UI marker.
12. Unsafe actions must be blocked before execution.
13. Human approval must pause execution until approved or denied.
14. Sandbox boundaries must prevent access outside the workspace.
15. UI must use progressive disclosure: simple by default, deep diagnostics on demand.
16. Existing demos, tests, replay, topology, inspector, metrics, cost profiler, security lab, and model gateway must keep working.
17. Avoid demo-only hardcoding in core systems.
18. Build stable vertical slices with tests.

============================================================ IMPORTANT TERMINOLOGY

Use “sandboxed work environment” or “sandbox runtime.” Do not call it “SanDisk.”

Use “enforcement” or “runtime guardrails.” Do not implement reinforcement learning as the core safety mechanism right now.

If “reinforcement” is needed later, interpret it as:

* feedback-driven improvement
* policy tuning
* evaluator feedback
* agent score calibration

But the first production-safe version must use deterministic policy enforcement and validation.

============================================================ NEXT PRODUCT PHASE NAME

Call this next phase:

AgentLab Runtime v1

Subtitle:

Sandboxed Project Builder + Orchestration + Enforcement Control Plane

============================================================ HIGH-LEVEL SYSTEM DESIGN

The new runtime architecture should look like this:

User Goal → Workspace → Agent Definitions → Planner creates Workflow Plan → Orchestrator assigns Tasks → Agents call Model Gateway → Agents propose Actions → Enforcement Gateway evaluates Actions → Sandbox executes allowed Actions → Validators inspect outputs/runtime/evidence → Trust/Risk engine updates scores → Human approvals resolve risky decisions → UI visualizes project map, data flow, agents, errors, and decisions → Replay reconstructs entire workflow

Important flow:

Agent proposes action → action.proposed event → policy engine evaluates → policy.evaluated event → decision: allow/block/reroute/approval/quarantine → enforcement event → if allowed, sandbox executes → sandbox/runtime events stream → validators run → validation events stream → trust/risk updates → UI updates live → replay can reconstruct all of it

============================================================ MILESTONE 1 — PROJECT WORKSPACES

Add a first-class Project Workspace concept.

A workspace represents a software project being built inside AgentLab.

Backend data model should include:

Workspace:

* id
* project_id
* name
* description
* goal
* status: created, planning, running, paused, blocked, failed, completed, archived
* root_path
* sandbox_id
* active_run_id
* provider_config_id
* created_at
* updated_at

WorkspaceArtifact:

* id
* workspace_id
* artifact_type: file, directory, generated_code, research_result, product_data, plan, validation_report, approval_record, build_output, runtime_log
* name
* path
* content_hash
* metadata
* status: draft, validated, rejected, blocked, approved
* created_by_agent_id
* created_at
* updated_at

Workspace events:

* workspace.created
* workspace.updated
* workspace.deleted
* workspace.status.changed
* workspace.artifact.created
* workspace.artifact.updated
* workspace.artifact.validated
* workspace.artifact.rejected

Backend APIs:

* POST /api/workspaces
* GET /api/workspaces
* GET /api/workspaces/{workspace_id}
* PATCH /api/workspaces/{workspace_id}
* POST /api/workspaces/{workspace_id}/start
* POST /api/workspaces/{workspace_id}/pause
* POST /api/workspaces/{workspace_id}/resume
* POST /api/workspaces/{workspace_id}/archive
* GET /api/workspaces/{workspace_id}/artifacts
* GET /api/workspaces/{workspace_id}/events
* GET /api/workspaces/{workspace_id}/runtime-status

Frontend:

* Workspaces page
* Create workspace modal/page
* Workspace detail page
* Workspace status banner
* Goal summary
* Agent panel
* Recent activity panel
* Pending approval panel
* Project health panel

Acceptance criteria:

* User can create a workspace.
* Workspace appears in UI.
* Workspace emits events into event log.
* Workspace can be associated with a run.
* Existing project/run model remains backward compatible.
* Tests cover workspace creation and status transitions.

============================================================ MILESTONE 2 — AGENT DEFINITIONS INSIDE WORKSPACES

Add configurable agents that belong to a workspace.

AgentDefinition:

* id
* workspace_id
* name
* role
* description
* system_prompt
* model_provider_id
* model_name
* allowed_tools
* denied_tools
* permissions
* max_tokens_per_call
* max_calls_per_run
* max_tool_calls_per_run
* requires_verification
* trust_score
* risk_score
* status: ready, running, caution, suspicious, quarantined, disabled
* created_at
* updated_at

Permissions examples:

* can_read_files
* can_write_files
* can_delete_files
* can_run_commands
* can_call_web
* can_access_database
* can_modify_auth
* can_modify_payment
* can_modify_deployment
* can_send_to_agents
* can_send_to_user
* can_save_product_data
* can_use_unverified_research

Default agent templates:

1. Planner Agent

* creates workflow plan
* assigns tasks
* cannot write files directly
* cannot run commands

1. UI Agent

* creates/edits frontend components/pages/styles
* cannot modify backend/payment/auth unless approved

1. Backend Coder Agent

* creates APIs, schemas, DB models, cart/checkout logic
* auth/payment/deployment changes require approval

1. Researcher Agent

* researches products/suppliers
* cannot write directly to production database
* all supplier/product claims require validation

1. Marketing Agent

* writes product copy, SEO, ads
* cannot use unverified product data

1. Verifier Agent

* validates research and claims
* can inspect evidence
* cannot override deterministic validators alone

1. Safety Reviewer Agent

* summarizes risks and suggests approvals
* cannot directly execute risky actions

Agent events:

* agent.definition.created
* agent.definition.updated
* agent.permission.changed
* agent.status.changed
* agent.runtime.started
* agent.runtime.completed
* agent.runtime.failed
* agent.quarantined
* agent.unquarantined
* agent.permissions.restricted

Acceptance criteria:

* User can create/select agent templates.
* Agents are connected to existing model gateway.
* Agent cards show model, permissions, trust, risk, status.
* Quarantined/disabled agents cannot be assigned normal tasks.
* Existing topology can display workspace agents.
* Tests cover permission model and state transitions.

============================================================ MILESTONE 3 — SANDBOXED WORK ENVIRONMENT

Build a controlled sandbox runtime for projects.

The sandbox must be able to:

* create workspace directory
* write files
* read files
* list files
* watch file changes
* run safe commands
* capture stdout/stderr
* capture exit codes
* start/stop dev servers
* run tests/builds
* stream logs/events to backend
* prevent path traversal
* prevent access outside workspace
* redact secrets
* block unsafe commands before execution

First implementation can be local-process-based if needed, but structure it so Docker/container isolation can become default later.

Preferred components:

* SandboxManager
* WorkspaceFileService
* SandboxCommandRunner
* SandboxPolicyAdapter
* SandboxProcessManager
* SandboxEventEmitter
* SandboxFileWatcher
* SandboxLogStreamer
* SandboxRuntimeSession

Sandbox event types:

* sandbox.created
* sandbox.initialized
* sandbox.started
* sandbox.paused
* sandbox.resumed
* sandbox.stopped
* sandbox.destroyed
* sandbox.file.read
* sandbox.file.created
* sandbox.file.updated
* sandbox.file.deleted
* sandbox.command.proposed
* sandbox.command.allowed
* sandbox.command.blocked
* sandbox.command.started
* sandbox.command.completed
* sandbox.command.failed
* sandbox.server.started
* sandbox.server.stopped
* sandbox.server.failed
* sandbox.build.started
* sandbox.build.completed
* sandbox.build.failed
* sandbox.test.started
* sandbox.test.completed
* sandbox.test.failed
* sandbox.log.emitted

Default blocked command classes:

* destructive host operations
* rm -rf outside workspace
* path traversal
* reading .env/secrets without approval
* writing outside workspace
* network exfiltration commands
* credential dumping commands
* deployment commands without approval
* git push without approval
* database destructive commands without approval
* chmod/chown/system modifications
* package install from suspicious/unpinned source unless approved

Safe command examples:

* npm install only after policy evaluation
* npm run build
* npm test
* python -m pytest
* ls inside workspace
* cat safe project files
* node scripts inside workspace
* dev server start inside workspace

Acceptance criteria:

* Sandbox can create/read/write/list files inside workspace.
* Sandbox blocks path traversal.
* Sandbox blocks unsafe commands before execution.
* Sandbox emits all actions into event log.
* Sandbox logs appear in UI.
* Sandbox actions appear in replay.
* Tests verify blocked commands never execute.
* Tests verify workspace boundary cannot be escaped.

============================================================ MILESTONE 4 — ORCHESTRATION ENGINE

Build the orchestration layer that turns user goals into multi-agent workflows.

Core objects:

Workflow:

* id
* workspace_id
* run_id
* goal
* status: planned, running, paused, blocked, failed, completed
* created_by
* created_at
* updated_at

WorkflowPlan:

* id
* workflow_id
* summary
* steps
* dependencies
* required_agents
* risk_assessment
* validation_requirements
* approval_requirements

Task:

* id
* workflow_id
* workspace_id
* assigned_agent_id
* title
* description
* status: pending, running, blocked, waiting_for_approval, waiting_for_validation, rerouted, failed, completed
* dependencies
* expected_artifacts
* risk_level
* requires_validation
* requires_approval
* created_at
* updated_at

TaskResult:

* id
* task_id
* agent_id
* output
* artifacts
* validation_status
* risk_delta
* trust_delta
* created_at

Orchestrator responsibilities:

* create initial plan
* assign tasks to agents
* respect dependencies
* prevent quarantined agents from receiving normal tasks
* route low-confidence outputs to verifier
* pause when approval is required
* resume after approval
* retry failed tasks with constraints
* record all routing and decision events
* use existing model gateway for model calls
* use existing cost/token profiler
* use existing event pipeline

Workflow events:

* workflow.created
* workflow.plan.requested
* workflow.plan.created
* workflow.started
* workflow.paused
* workflow.resumed
* workflow.blocked
* workflow.completed
* workflow.failed
* task.created
* task.assigned
* task.started
* task.completed
* task.failed
* task.blocked
* task.rerouted
* task.retry_requested
* task.waiting_for_validation
* task.waiting_for_approval

Acceptance criteria:

* User can start a workflow from workspace goal.
* Planner produces plan.
* Orchestrator creates tasks.
* Tasks are assigned to agents.
* Dependencies are respected.
* Quarantined agents cannot receive normal tasks.
* Workflow events stream to UI.
* Replay shows workflow execution.
* Tests cover basic orchestration and rerouting.

============================================================ MILESTONE 5 — ACTION ENFORCEMENT GATEWAY

Build central enforcement gateway.

Every important action must be proposed before execution.

Action types requiring enforcement:

* model call
* tool call
* web/browser request
* file read
* file write
* file delete
* command execution
* package install
* database read/write/migration
* API request
* message to another agent
* save artifact
* save product/supplier data
* auth/payment/deployment code modification
* deployment/publishing
* final output to user when high-risk

Action lifecycle:

1. action.proposed
2. policy.evaluated
3. enforcement.allowed OR enforcement.blocked OR enforcement.approval_required OR enforcement.rerouted OR enforcement.quarantine_triggered
4. action.started if allowed
5. action.completed OR action.failed
6. validation may run
7. score.updated if needed

ActionProposal:

* id
* workspace_id
* run_id
* workflow_id
* task_id
* agent_id
* action_type
* target
* input_summary
* raw_input_redacted
* sensitivity_level
* expected_effect
* requires_approval_hint
* created_at

ActionDecision:

* id
* action_id
* decision: allow, block, require_human_approval, reroute_to_verifier, retry_with_constraints, quarantine_agent, downgrade_permissions, allow_readonly, allow_sandbox_only
* matched_rules
* trust_score_before
* risk_score_before
* reason
* evidence
* created_at

PolicyRule:

* id
* name
* description
* enabled
* priority
* condition
* decision
* risk_delta
* trust_delta
* human_readable_reason

Default policies:

1. Block destructive shell commands unless explicitly approved.
2. Block path traversal and file access outside workspace.
3. Block reading secrets unless approved and redacted.
4. Require approval for payment, auth, deployment, or production database changes.
5. Require validation for supplier/product claims.
6. Block unverified supplier data from reaching database, UI, or marketing.
7. Block marketing claims based on unverified product data.
8. Reroute low-confidence research output to Verifier Agent.
9. Reroute tasks away from agents with risk > 0.7.
10. Quarantine agents with repeated high-risk violations.
11. Quarantined agents cannot call tools, write files, run commands, or message normal agents.
12. Require tests/build after backend/schema/auth/payment changes.
13. Block deploy until build/tests pass.
14. Block model/tool calls if token/cost budget exceeded.
15. Require approval when installing new packages.
16. Allow read-only inspection for caution agents.
17. Allow sandbox-only execution for medium-risk actions.
18. Require verifier/human approval before saving business-critical data.

Enforcement events:

* action.proposed
* policy.evaluated
* policy.rule.matched
* enforcement.allowed
* enforcement.blocked
* enforcement.approval_required
* enforcement.rerouted
* enforcement.retry_required
* enforcement.permissions_downgraded
* enforcement.quarantine_triggered
* action.started
* action.completed
* action.failed

Acceptance criteria:

* Every risky action goes through enforcement.
* Unsafe command is blocked before execution.
* Unverified research cannot flow downstream.
* High-risk agents are rerouted.
* Policy decisions are explainable.
* Policy decisions appear in replay.
* Existing trust/risk engine receives scoring signals.
* Tests verify action lifecycle.

============================================================ MILESTONE 6 — REAL QUARANTINE

Upgrade quarantine from visualization to runtime restriction.

When an agent is quarantined:

* it cannot run tools
* it cannot execute commands
* it cannot write files
* it cannot delete files
* it cannot save artifacts except quarantine explanation/debug notes
* it cannot send messages to normal agents
* it cannot affect workflow outputs
* it can only communicate with Verifier Agent, Safety Reviewer, or Human
* it can be inspected in replay
* it can be manually unquarantined through approval flow

Quarantine triggers:

* repeated unsupported claims
* attempted policy bypass
* attempted secret access
* attempted destructive command
* repeated validation failure
* high risk score above threshold
* malicious/suspicious event
* human quarantine action

Events:

* agent.quarantine.requested
* agent.quarantined
* agent.quarantine.enforced
* agent.quarantine.blocked_action
* agent.unquarantine.requested
* agent.unquarantined
* agent.permissions.restored

Acceptance criteria:

* Quarantined agent cannot write files.
* Quarantined agent cannot message UI/Backend/Marketing agents.
* Quarantined agent can send explanation to Verifier/Human only.
* UI clearly shows real restricted state.
* Replay shows why quarantine happened.
* Tests prove restrictions are enforced.

============================================================ MILESTONE 7 — HUMAN APPROVAL SYSTEM

Add approval gates for risky actions.

ApprovalRequest:

* id
* workspace_id
* run_id
* workflow_id
* task_id
* action_id
* agent_id
* title
* plain_english_summary
* technical_summary
* risk_level
* matched_policy_rules
* recommended_decision
* options: approve, deny, approve_once, approve_readonly, reroute, quarantine
* status: pending, approved, denied, expired, cancelled
* created_at
* resolved_at
* resolved_by

Approval triggers:

* risky command
* package install
* payment/auth/deployment code change
* database migration
* deploy/publish
* reading secret/sensitive files
* accepting supplier recommendation
* overriding validator failure
* unquarantining agent
* allowing high-risk agent to continue

Approval events:

* approval.requested
* approval.approved
* approval.denied
* approval.expired
* approval.cancelled
* approval.override_used

UI:

* Approval inbox
* Pending approval badge
* Plain-English risk summary
* Technical details expandable
* Approve/Deny/Reroute/Quarantine buttons
* Replay link to action context

Acceptance criteria:

* Risky action pauses workflow.
* User can approve or deny.
* Approved action resumes.
* Denied action blocks or reroutes.
* Approval appears in event log and replay.
* Tests cover approval flow.

============================================================ MILESTONE 8 — DETERMINISTIC VALIDATORS

Build validators that produce evidence for enforcement and trust/risk scoring.

Do not rely only on LLM verifier opinions.

ValidatorResult:

* id
* workspace_id
* run_id
* validator_type
* target_type
* target_id
* passed
* confidence
* evidence
* failures
* suggested_action
* risk_delta
* trust_delta
* created_at

Validator categories:

1. Code validators:

* syntax check
* typecheck where available
* build
* tests
* lint if configured
* dependency install failure
* import resolution
* changed risky files
* secret exposure scan
* suspicious package install

1. Runtime validators:

* frontend route loads
* backend route responds
* API status codes
* browser console errors
* server errors
* request failures
* HTTP 404/500
* dev server crash

1. Data-flow validators:

* frontend expects field X
* backend returns field Y
* database stores field Z
* mismatch between frontend/backend/database
* missing required field
* type mismatch
* cart expects price_cents but API sends price
* checkout expects stripe_price_id but DB lacks it

1. Research validators:

* URL exists
* URL returns 200
* source page contains claimed supplier/product
* price appears on page
* MOQ appears on page
* shipping info appears on page
* supplier contact exists
* cited source supports claim
* multiple source cross-check when required
* timestamp and evidence snapshot stored
* fake/unsupported claim rejected

1. Business-risk validators:

* supplier data affects money/inventory
* price affects checkout
* marketing claim unsupported
* product data unverified
* payment/auth/deployment code touched
* customer data touched

Validation events:

* validator.started
* validator.completed
* validator.failed
* validation.passed
* validation.failed
* claim.verified
* claim.rejected
* schema.mismatch.detected
* runtime.error.detected
* app.error.translated
* risky.file_change.detected
* secret.exposure.detected

Acceptance criteria:

* Fake supplier URL is caught.
* Missing price/MOQ evidence is caught.
* Frontend/backend field mismatch is caught.
* Failed build/test is caught.
* Validator results influence enforcement.
* Validator results influence trust/risk.
* Validator results appear in UI/replay.

============================================================ MILESTONE 9 — VISUAL PROJECT DEBUGGING FOR NONTECHNICAL USERS

Build visual debugging UI using progressive disclosure.

Default view must be simple.

Default Workspace Home should show:

* Project health
* What agents are working on
* What changed recently
* What is broken
* What is risky
* What needs approval
* Recommended next action

Use beginner-friendly labels:

* Working
* Needs attention
* Blocked
* Needs approval
* Verification failed
* Agent restricted
* Safe to continue
* Risky change
* Data mismatch
* Build failed

Advanced views hidden behind clicks:

* Agent graph
* File-change timeline
* Project map
* Data-flow map
* Runtime logs
* API traces
* DB traces
* Policy decisions
* Validator evidence
* Replay debugger
* Raw JSON

Project map for e-commerce demo: Frontend:

* Home page
* Product page
* Cart page
* Checkout page

Backend:

* Product API
* Cart API
* Checkout API
* Supplier/Product service

Database:

* products
* suppliers
* cart_items
* orders

External/tools:

* model provider
* browser/web research
* payment stub
* verifier
* sandbox commands

Data-flow map: Supplier research → verified product data → products database → product API → product page → cart → checkout

File-change timeline:

* UI Agent edited ProductCard.tsx
* Backend Agent edited /api/products
* Backend Agent changed product schema
* Researcher Agent added supplier candidate
* Verifier rejected supplier candidate
* Policy blocked propagation
* Coder fixed mismatch
* Build passed

Error translator examples:

1. “The product page is blank because the frontend expects bottle.price, but the backend is sending bottle.cost.”
2. “Checkout is broken because the backend route exists, but the payment function is not connected.”
3. “The supplier recommendation was blocked because the source URL returned 404 and the price was not found.”
4. “The coder changed payment-related code, so AgentLab requires approval before continuing.”
5. “The marketing agent tried to use unverified supplier data, so the message was blocked.”

Trust/risk panel examples:

* Researcher Agent: caution because 2 unsupported claims
* Backend Agent: trusted but must run tests after schema changes
* Marketing Agent: blocked from using unverified product data
* Verifier Agent: trusted
* UI Agent: healthy

Acceptance criteria:

* Nontechnical user can understand what broke without reading raw stack traces.
* Technical user can drill down to raw logs/events.
* UI does not overwhelm by default.
* Project map and data-flow map are connected to real events/validators.
* Replay links to visual explanations.
* Frontend tests cover key UI states.

============================================================ MILESTONE 10 — BOTTLE-SELLING WEBSITE END-TO-END DEMO

Create a polished demo that proves the full product vision.

Demo goal: Build a simple water bottle e-commerce website inside AgentLab using multiple agents.

Must include:

* workspace creation
* model provider selection using MockProvider by default
* optional BYOK provider path
* agent creation from templates
* workflow planning
* sandbox file generation
* frontend/backend skeleton
* product database/schema or mock DB
* cart and checkout stub
* supplier research
* deterministic validation
* enforcement gateway
* approval gates
* real quarantine
* visual project map
* data-flow map
* file timeline
* replay

Agents:

* Planner Agent
* UI Agent
* Backend Coder Agent
* Researcher Agent
* Verifier Agent
* Marketing Agent
* Safety Reviewer Agent if useful

Scenario 1 — Normal build:

* Planner creates plan.
* UI creates storefront.
* Backend creates API/cart/checkout stub.
* Researcher finds supplier candidate.
* Verifier validates one valid supplier.
* Marketing writes copy from verified product data.
* Build passes.
* UI shows healthy project map.

Scenario 2 — Research hallucination: Researcher proposes fake supplier:

* fake supplier URL returns 404 or mock invalid page
* price unsupported
* MOQ missing
* shipping missing

Expected behavior:

* validator fails
* claim.rejected emitted
* enforcement blocks propagation
* supplier not saved to product database
* marketing agent cannot use it
* researcher trust decreases
* risk increases
* task rerouted to Verifier or retry
* UI explains the reason plainly
* replay shows the blocked path

Scenario 3 — Frontend/backend mismatch: Intentional mismatch:

* frontend expects product.price
* backend sends product.cost or price_cents

Expected behavior:

* data-flow validator detects mismatch
* UI shows explanation: “The product page is blank because the frontend expects product.price, but the backend sends product.cost.”
* Backend/UI fix task created
* Coder fixes mismatch
* build/test rerun
* replay shows introduction and fix

Scenario 4 — Risky command: Coder proposes unsafe command or sensitive file read.

Expected behavior:

* action.proposed emitted
* policy blocks it before execution
* command never runs
* approval may be requested depending on policy
* UI explains matched rule
* replay shows blocked action

Scenario 5 — Real quarantine: Researcher repeatedly submits unsupported claims or tries to bypass verifier.

Expected behavior:

* risk crosses threshold
* quarantine triggered
* researcher is runtime-restricted
* cannot message Marketing/UI/Backend
* cannot write artifacts
* can only communicate with Verifier/Human
* UI shows quarantine reason
* replay shows all escalation events

Demo commands:

* make bottle-demo
* make runtime-demo
* make policy-test
* make sandbox-test

Acceptance criteria:

* Demo runs without real API keys using MockProvider.
* BYOK path works separately.
* All events stream live.
* Replay reconstructs workflow.
* Nontechnical summary is understandable.
* Unsafe actions are blocked.
* Quarantine is real.
* Tests cover core paths.

============================================================ MILESTONE 11 — INTEGRATION WITH EXISTING MODEL GATEWAY + COST PROFILER

Because model gateway and BYOK already exist, do not rebuild them.

Instead:

* Connect AgentDefinitions to existing model provider configs.
* Ensure orchestrated agent calls use existing gateway.
* Ensure all runtime model calls emit model.call events.
* Ensure token/cost profiler attributes usage to workspace, workflow, task, agent, model, and provider.
* Ensure replay shows accumulated cost over orchestrated workflow.
* Ensure cost limits can be used as enforcement policies.

Add policy examples:

* block model calls if workspace budget exceeded
* require approval if single call estimated cost exceeds threshold
* downgrade model for low-risk tasks if budget constrained
* stop runaway agents after call/tool budget reached

Acceptance criteria:

* Runtime agents use existing gateway.
* Cost profiler works with runtime workflows.
* Per-agent and per-task cost attribution appears.
* Budget policy can block runaway model usage.
* Existing model gateway tests still pass.

============================================================ MILESTONE 12 — TESTING AND QUALITY

Add tests for all new systems.

Backend tests:

* workspace CRUD
* workspace status transitions
* agent definitions
* permission checks
* sandbox path boundaries
* blocked commands
* safe commands
* action lifecycle
* policy evaluation
* approval flow
* quarantine enforcement
* workflow creation
* task assignment
* rerouting
* validators
* research claim rejection
* frontend/backend mismatch detection
* cost budget enforcement
* replay event reconstruction

Frontend tests:

* workspace list
* workspace detail
* agent cards
* approval inbox
* project health summary
* file timeline
* project map
* data-flow map
* validator explanation panel
* policy decision panel
* quarantine state
* replay markers

End-to-end/browser tests:

* create workspace
* start bottle demo
* watch events stream
* inspect blocked supplier
* inspect data mismatch
* approve/deny risky action
* verify quarantine UI
* replay workflow
* ensure no console errors

Security tests:

* secrets redacted
* path traversal blocked
* unsafe commands blocked
* quarantined agent cannot act
* denied approval does not execute action
* unverified supplier data cannot reach marketing/database

CI requirements:

* backend tests pass
* frontend tests pass
* build passes
* no console errors in Playwright demo
* no real API keys required
* no external paid calls required for tests

============================================================ DOCUMENTATION UPDATES

Update documentation after implementation.

Required docs:

* README.md
* ARCHITECTURE.md
* ROADMAP.md
* Runtime design doc
* Sandbox safety doc
* Enforcement policy doc
* Validator design doc
* Human approval doc
* Bottle demo walkthrough
* Nontechnical user guide
* Developer integration guide

README should clearly explain the new positioning:

AgentLab is a sandboxed AI project-building runtime that lets users create multi-agent software workflows, see what every agent is doing, validate outputs, block unsafe actions, reroute hallucinating agents, require approvals, quarantine risky agents, and replay the entire build/debug process.

Add limitations:

* AgentLab reduces risk but cannot guarantee perfect correctness.
* Validators are evidence-based but not omniscient.
* LLM verifiers can be wrong.
* Sandbox isolation depends on deployment mode.
* BYOK keys must be handled carefully.
* External research validation may be incomplete.
* Production deployment requires stronger isolation than local dev.
* Human approval is required for high-risk actions.

============================================================ IMPLEMENTATION BEHAVIOR

Before coding:

1. Inspect repository structure.
2. Identify current event schema.
3. Identify current trust/risk scoring code.
4. Identify current replay reducer.
5. Identify current model gateway implementation.
6. Identify current cost profiler implementation.
7. Identify current dashboard state management.
8. Identify current API/project/run schema.
9. Create a concise implementation plan with files to touch.
10. Do not code until the plan is clear.

While coding:

1. Implement in small vertical slices.
2. Preserve backward compatibility.
3. Add tests with each feature.
4. Use existing event pipeline.
5. Use existing scoring system.
6. Use existing gateway/cost systems.
7. Prefer deterministic behavior.
8. Keep unsafe actions blocked by default.
9. Redact secrets everywhere.
10. Use MockProvider for demos/tests.
11. Do not require paid model calls.
12. Do not hardcode bottle demo behavior into core systems.
13. Do not bypass enforcement gateway for risky actions.

After coding:

1. Run backend tests.
2. Run frontend tests.
3. Run build.
4. Run existing demos.
5. Run new runtime/bottle demo.
6. Verify no console errors.
7. Verify unsafe commands are blocked.
8. Verify quarantine restricts runtime behavior.
9. Verify replay includes enforcement decisions.
10. Verify cost profiling still works.
11. Verify trust/risk explanation still works.
12. Verify BYOK gateway still works.
13. Verify UI is understandable for nontechnical users.

============================================================ FINAL ACCEPTANCE CRITERIA

The upgrade is successful only when all of these are true:

1. User can create a project workspace inside AgentLab.
2. User can create/select agents inside the workspace.
3. Agents use the existing model gateway/BYOK system.
4. AgentLab can orchestrate a multi-agent workflow.
5. Agents can generate files/artifacts inside a sandbox.
6. Sandbox streams file, command, build, test, and runtime events.
7. Every risky action goes through enforcement before execution.
8. Unsafe commands are blocked before execution.
9. Human approval can pause and resume workflows.
10. Unverified supplier/product research cannot reach database, UI, or marketing.
11. Low-trust/hallucinating agents can be rerouted to Verifier.
12. Quarantine actually restricts runtime permissions.
13. Deterministic validators catch fake supplier claims.
14. Deterministic validators catch frontend/backend/data mismatches.
15. UI shows project health simply by default.
16. UI provides deeper diagnostics on demand.
17. Replay reconstructs workflow, validation, approval, enforcement, and quarantine decisions.
18. Trust/risk scoring still works and evolves during replay.
19. Cost/token profiling works across workspace/workflow/task/agent/model.
20. Existing AgentLab observability features still work.
21. Bottle-selling website demo runs end-to-end with MockProvider.
22. All tests pass.
23. No real API keys are required for demos/tests.
24. No unsafe or destructive actions occur outside the sandbox.

============================================================ FINAL PRODUCT POSITIONING TO PRESERVE

Do not let AgentLab become just another AI coding assistant.

The product is not simply: “AI builds an app.”

The product is: “AI builds an app inside a controlled runtime where the user can see, understand, debug, validate, and govern what the AI is doing.”

The important difference: Claude/Codex/Cursor can generate code. AgentLab lets users understand and control the generated system.

AgentLab should answer:

* What did the AI change?
* Which agent caused the issue?
* Why did the app break?
* Which data flow is broken?
* Which action is risky?
* Which agent is hallucinating?
* What was blocked and why?
* What needs approval?
* Can this be replayed?
* Is this safe to continue?

Build toward this final vision:

AgentLab is the visual runtime, debugger, and safety control plane for AI-built software.
