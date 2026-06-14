# AgentLab — Roadmap

## v0.1 — Local observability ✅

The working vertical slice: **instrument → collect → visualize → inspect**.

- Zero-dependency Python SDK (agents, messages, tools, models, routing, trust)
- FastAPI collector: validated 22-type schema, idempotent batch ingest, optional API keys
- Append-only event log + relational projections (SQLite dev / PostgreSQL in Docker)
- Real-time dashboard: live topology (React Flow), Wireshark-style inspector,
  event timeline with filters, run metrics (tokens/cost/p95/error rate/highlights)
- 5-agent demo pipeline with success / retry / failure scenarios (no LLM keys)
- Docker Compose stack, Makefile DX, CI, 44 tests

## v0.2 — Replay debugger ✅

Open any run like a packet capture.

- `GET /runs/{id}/replay` (tape + jump markers) and
  `GET /runs/{id}/replay/graph?index=k` (server-side reconstruction)
- Client-side event-fold reducer with semantics identical to the server fold
  (pinned by both pytest and vitest suites); topology component reused
- Controls: play / pause / step / scrub (marker-dotted slider) / 0.5–8× speed,
  keyboard transport (space, arrows), clamped real-gap pacing
- Jump to next error / tool call / routing decision
- Inspector follows the playhead; pin any node/edge/event to detach
- Deferred to a later cut: snapshot memoization for very large tapes; live
  tape growth while a run is still streaming

## v0.3 — Fault Injection Lab ✅

Chaos engineering for agent systems — all simulated, telemetry only.

- 6 fault types via `POST /runs/{id}/faults`: kill_agent, overload_agent,
  force_tool_failure, simulate_model_timeout, delay_messages, drop_messages
- Each fault = `fault.injected` + realistic follow-up events through the
  normal pipeline (graph, metrics, WS, replay all react for free)
- Functional Lab UI: project/run pickers, live agent-status strip, template
  cards with targets + params, fault log with raw payloads
- Replay integration: `markers.faults`, rose scrubber dots, Fault jump button
- Seeded scenario: "Fault Injection Demo — Research Agent Timeout"
- Safety: simulation-only (`safe_simulation: true` end to end); no real
  process/network/secret interaction
- Deferred: `corrupt_message` / `increase_latency` variants; an SDK
  control-plane hook so faults can intercept *live* demo traffic

## v0.4 — Malicious-agent simulation ✅

A safe cyber range — all attacks are mock-only telemetry simulations.

- 8 attack types via `POST /runs/{id}/attacks`: malicious_agent_joined,
  fake_capability_advertising, prompt_injection_message,
  mock_data_exfiltration_attempt, high_frequency_spam, trust_poisoning,
  routing_manipulation, unsafe_tool_request
- Each attack = `attack.injected` + mock follow-ups (agent.joined/suspicious,
  flagged messages, risk.updated, quarantine) through the normal pipeline
- Security Lab UI (Lab → Security Lab): attack cards with mock-payload
  previews; suspicious/quarantine node states, flagged edges
- Replay integration: `markers.attacks`, fuchsia scrubber dots, Attack jump
- Metrics: attacks / flagged-messages / suspicious-agents counts
- Seeded scenario: "Malicious Agent Demo — Prompt Injection Attempt"
- Safety: mock secrets only; `safe_simulation: true`,
  `real_secrets_accessed: false`, `real_network_access: false` end to end
- The trust/risk *engine* itself shipped in v0.5 (below)

## v0.5 — Trust/risk engine ✅

Deterministic, event-derived, explainable scoring — no LLM, fully replayable.

- `app/scoring.py`: pure event-fold → per-agent trust/risk + explained history;
  one rule table shared by collector, graph, replay, metrics, and the JS mirror
- Endpoints: `/runs/{id}/scores`, `/runs/{id}/score-history`,
  `/runs/{id}/risk-summary`, `/agents/{id}/scores` (with trust/risk factors)
- Fixed the v0.4 bug: a quarantined malicious agent reads ~0.1 trust / 1.0 risk,
  never 1.0; a faulted agent degrades to `caution` without being labelled malicious
- UI: tier badges on nodes, score panel (reason + factors + history) in the
  inspector and agent page, run risk summary on the Metrics tab, and scores that
  evolve step-by-step in replay
- Scores derived on read = no `score.updated` events emitted (no feedback loops)
- 21 pytest + 11 vitest scoring tests
- Deferred: enforcement (routing impact, quarantine thresholds), score decay —
  the engine scores and explains, it is not a policy engine

## v0.6 — Cost/token profiler ✅

Deterministic per-agent / per-model / per-run cost and token attribution.

- `pricing.py` static table (mock providers, USD per 1M tokens) + `costing.py`
  pure fold over `model.*` events; cost always recomputed from tokens = single
  source of truth shared by endpoints, metrics, graph, and the JS mirror
- Endpoints: `/runs/{id}/costs`, `/runs/{id}/token-summary`,
  `/agents/{id}/costs`, `/projects/{id}/cost-summary`
- UI: Cost & Tokens tab (summary cards, cost/token/latency ranking bars,
  model-by-provider breakdown, agent table), model-call inspector with
  token/cost details, "Cost so far" strip that accumulates in replay
- SDK `log_model_call` gains provider/model_name/input_tokens/output_tokens
- Demo: per-agent mock providers — Coder most expensive, Researcher most
  token-heavy, Security on free local-ollama, a failed model call in the
  failure scenario
- 21 pytest + 10 vitest cost tests
- Deferred: real provider calls / BYOK (v0.7); pricing is a static local table

## v0.7 — Model gateway / BYOK ✅

Local-first model gateway: call providers through one interface, safely.

- `app/model_gateway/`: provider abstraction + mock (keyless default),
  OpenAI-compatible, Anthropic, and Ollama providers; registry from Settings;
  telemetry bridge to model.called/completed/failed
- Endpoints: `/model-gateway/providers`, `/providers/{p}/health`,
  `/model-gateway/test-call`, `/runs/{id}/model-call`
- SDK `client.model_call(...)` (clean model.failed if the gateway is unreachable)
- UI: Settings → Model Gateway — provider cards (status, models, redacted key)
  + safe test-call panel; gateway calls flow into telemetry, replay & Cost & Tokens
- Safe BYOK: keys env-only, never stored/returned/logged, redacted in UI; a test
  greps responses to prove no leak; `.env.example` placeholders only
- Demo `--use-gateway` routes model calls through the gateway (mock)
- 13 pytest + 2 SDK + 4 vitest gateway tests
- Deferred: hosted/cloud secret storage, per-user keys, real Gemini provider
  (→ v0.7.1)

## v0.7.1 — Model gateway patch: Gemini + Ollama troubleshooting ✅

- `GeminiProvider` (generateContent API): `GEMINI_API_KEY` / `GOOGLE_API_KEY`
  (GEMINI preferred), key server-side only and redacted in the UI like every
  other provider; `GEMINI_BASE_URL` overridable for tests
- Provider list now carries a `message` troubleshooting hint (mirrors health
  detail); rendered amber on unavailable/not-configured cards
- Ollama health check explains how to fix "unavailable": the configured
  `OLLAMA_BASE_URL`, `ollama serve` / `ollama pull llama3.2`, and the Docker
  `host.docker.internal:11434` hint
- 17 pytest + 6 vitest gateway tests (planted-key leak grep extended to Gemini)
- Still deferred: hosted/cloud secret storage, per-user keys

## v0.8 — Agent Builder Studio ✅

Build and run multi-agent workflows inside AgentLab.

- `app/studio/`: workflow/agent/edge definitions (own tables; the append-only
  `events` log stays the runtime source of truth), validation (DAG-only —
  cycles rejected with a clear error; provider/model checked against the
  gateway registry), and a deterministic topological executor
- Every model call goes through the v0.7 Model Gateway; a Studio run emits the
  standard run/agent/message/model events through the collector, so the graph,
  replay, inspector, metrics, trust/risk, and Cost & Tokens all work unchanged
- Endpoints: `/studio/workflows` CRUD, agent/edge CRUD, `/validate`, `/run`
  (+ `/runs` history); failed providers fail cleanly with `model.failed`,
  downstream agents are skipped, and the run ends in `run.failed`
- UI: Studio section — workflow list, React Flow canvas (drag, connect,
  select), agent editor (role/system prompt/provider/model/temperature/max
  tokens with unconfigured-provider warnings), edge editor, validate banner,
  run panel with Open Run / Replay / Cost & Tokens links, run history
- Seeded "Code Review Agent Team" (Planner → Coder → Security Reviewer →
  Report, all on keyless mock models) created at startup when no workflows exist
- 16 pytest + 11 vitest studio tests
- Deferred: templates (v0.9), loops/recursion, tools, hosted collaboration,
  cloud key storage, workflow governance

## v0.9 — Project Templates ✅

Start from real agent-team blueprints instead of a blank canvas.

- `app/studio/templates.py`: template registry — six 5-agent teams (Code
  Review, Research, Resume Tailoring, SOC Investigation, Customer Support,
  Data Analysis), each with category/tags/difficulty/use case, per-agent
  role + system prompt + mock model defaults, labeled edges, default input,
  expected outputs, and demo notes
- Templates are data, not a new run format: `create-workflow` materializes a
  normal v0.8 workflow (editable, validatable, runnable; agents carry
  `template_id` provenance in metadata)
- Endpoints: `GET /studio/templates`, `GET /studio/templates/{id}`,
  `POST /studio/templates/{id}/create-workflow`
- UI: template gallery ("Start from template"), preview page (canvas preview,
  agent team, default input, expected outputs, demo notes; system prompts
  behind an advanced toggle), create-with-optional-rename → opens the v0.8
  editor with the template's default input pre-filled in the run panel
- 11 pytest + 4 vitest template tests
- Deferred: Runtime v1 (workspaces, sandbox runtime, enforcement gateway,
  approvals, validators, real quarantine) — starts after v0.9 approval

## v0.9.1 — Chat Mode / Agent Mode + secure provider setup ✅

The Studio usability/safety patch before the Runtime v1 roadmap.

- Mode switcher on Studio pages: **Chat Mode** (conversational, read-only —
  action buttons disable, the assistant answers questions about the workflow,
  runs, failures, cost/tokens, trust/risk) and **Agent Mode** (runs workflows,
  edits, `/connect <provider>`, `/run`). Action requests in Chat Mode get
  exactly "Switch to Agent Mode to perform this action."
- `/connect gemini|openai|anthropic|ollama` opens a **secure setup modal**
  (password field, optional base URL, Save locally / Test call / Remove saved
  key) — raw keys never travel through chat; key-like text pasted into chat is
  blocked with a warning and never sent or stored
- Backend: `POST /model-gateway/providers/{p}/configure` + `/clear` store
  secrets in a local **gitignored** `.agentlab-secrets.json` (chmod 0600,
  overlays env, registry rebuilt immediately) — never the DB, never logged,
  never in responses/events/replay; only the redacted hint is returned
- Settings → Model Gateway cards gain a Configure button using the same modal
- 8 pytest + 9 vitest; the assistant is deterministic/local (rule-based over
  existing APIs — no LLM behind the chat)

## Runtime v1.0 — Runtime Workspaces ✅

The foundation of the Runtime phase (master plan:
docs/AGENTLAB_RUNTIME_V1_PLAN.md). **Metadata and UI only** — v1.0 does not
run commands, write files, sandbox code, enforce policy, or approve actions.

- `app/runtime/`: Workspace + WorkspaceArtifact models (own tables; the
  append-only `events` log stays the source of truth), status lifecycle
  (draft / active / paused / completed / archived / failed; DELETE archives —
  history is never destroyed)
- Every lifecycle action emits a workspace.* event (created / updated /
  status_changed / archived / artifact_registered — added to the shared
  event registry, API + SDK) into the workspace's **activity run**
  (`{workspace_id}-activity`), so the activity feed, timeline, and replay
  work through the normal pipeline with zero special-casing
- Endpoints: `/runtime/workspaces` CRUD (PATCH metadata/status, DELETE =
  archive), `/activity`, `/artifacts` list + register
- UI: Runtime nav section — workspace list + create flow, detail page with
  status banner (lifecycle actions), editable goal panel, recent activity
  (links to timeline/replay), artifact registry, project-health placeholder;
  Chat Mode renders it all read-only
- 11 pytest + 9 vitest

## Runtime v1.1 — Workspace Agent Definitions + Permissions ✅

First-class **agent definitions inside a workspace**. **Metadata only** — an
agent here describes what a future Runtime version will be allowed to run; it
does not execute, write files, call tools, or enforce anything.

- `app/runtime/`: WorkspaceAgent model (own table; events log stays the source
  of truth) with role / description / system prompt, Model Gateway
  provider+model metadata, a 13-flag permission profile, budget ceilings
  (max tokens/calls/tool-calls), `requires_verification`, trust/risk fields,
  and a status lifecycle (ready / running / caution / suspicious /
  quarantined / disabled — quarantined & disabled gate *assignment* only, no
  real runtime quarantine)
- `app/runtime/agent_templates.py`: seven blueprints (Planner, UI, Backend
  Coder, Researcher, Marketing, Verifier, Safety Reviewer) — data, not a
  runtime; instantiating one materializes a normal WorkspaceAgent. Keyless
  mock defaults; risk notes + future-approval flags carried as metadata
- Every action emits a `workspace_agent.*` event (created / updated /
  permission_changed / status_changed / deleted / template_instantiated —
  added to the shared registry, API + SDK) into the workspace's activity run,
  so activity / timeline / replay work through the normal pipeline
- Endpoints: `/runtime/workspaces/{id}/agents` CRUD, `/agent-templates`,
  `/agents/from-template/{template_id}`
- UI: Agents panel on the workspace detail page — template picker, agent
  cards (role, model/provider, status badge, trust/risk, permission badges
  with risky ones flagged), inline editor (metadata + permission toggles +
  status), delete; quarantined/disabled dimmed; Chat Mode disables mutations
- 18 pytest + 6 vitest

## Runtime v1.2 — Sandboxed File Runtime ✅

The first real runtime layer, kept deliberately narrow: **file operations
only**, confined beneath `{AGENTLAB_WORKSPACES_ROOT}/{workspace_id}`
(default `.agentlab-workspaces/`, gitignored). No shell, no command runner,
no build/test execution, no dev server, no orchestration, no enforcement.

- `app/runtime/sandbox.py`: deterministic path safety checked before any
  disk access — absolute paths, `..` traversal, null bytes, secret-named
  files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, …), and anything *resolving*
  outside the workspace root (which also catches symlink escapes) are
  rejected; a rejected operation never touches disk and emits a
  `sandbox.file.blocked` audit event carrying only the attempted logical
  path + matched rule — never host paths or content
- Operations: init sandbox (idempotent), status (file/dir counts + bytes),
  list, recursive tree, read (UTF-8, 256 KB cap), write/create (1 MB cap,
  parents auto-created), mkdir, delete (files + empty directories)
- Events: `sandbox.initialized` / `file.created` / `file.updated` /
  `file.read` / `file.deleted` / `directory.created` / `file.blocked`
  (shared registry, API + SDK) into the workspace activity run — list/tree/
  status reads emit nothing; payloads carry logical paths, sizes, and
  sha256 prefixes, never content or host paths
- Endpoints: `/runtime/workspaces/{id}/sandbox/init|status`,
  `/files`, `/files/tree`, `/files/read`, `/files/write`, `/files/mkdir`,
  `DELETE /files` — writes behind the existing API-key gate
- UI: Files panel on workspace detail — status card + initialize flow,
  recursive file tree, new file/folder flows, read/edit/save editor with
  size + hash, delete, safe blocked-path errors; Chat Mode disables all
  mutations; archived workspaces render read-only
- 21 pytest + 11 vitest (incl. proofs that blocked writes leave disk
  untouched and symlink escapes are refused)

## Runtime v1.3 — Safe Command Runner + Sandbox Events ✅

A narrow, deterministic command runner for workspace sandboxes — explicitly
NOT the future enforcement gateway. No interactive shell, no persistent
sessions, no long-running processes, no dev servers, no package installs.

- `app/runtime/commands.py`: structured requests (program + argv, never a
  shell string; `shell=False` end to end), evaluated by an allowlist-first
  safety policy **before any process spawns** — shell metacharacters
  (`;&|<>$\``), program paths, known-dangerous programs (rm/sudo/curl/bash/
  git/docker/pip/…), package installs, inline code (`-c`/`-e`), unknown
  programs, disallowed argument shapes, and path args failing the v1.2
  path-safety checker are all rejected with a `sandbox.command.blocked`
  audit event (reason + matched rule)
- Allowlist: `pwd`, `ls` (safe flags + one checked path), `cat` (one
  path-safety-checked file), `node/npm/python/python3 --version`,
  `npm test` / `npm run build` (require package.json), `python -m pytest`
  (requires pytest config or tests/)
- Execution: cwd locked inside the sandbox (working_subdir path-checked),
  scrubbed environment (PATH/HOME/LANG only — host env and secrets never
  reach commands), hard timeout (1–120 s), stdout/stderr capped (10 KB
  response / 2 KB event summary) and secret-redacted; the command display
  string itself is redacted too
- Events: `sandbox.command.proposed/allowed/blocked/started/completed/
  failed/timed_out` (shared registry, API + SDK) into the workspace
  activity run — history is an event query; timeline/replay reconstruct
  every decision
- Endpoints: `POST /runtime/workspaces/{id}/commands/run` (API-key gated),
  `GET …/commands/history`, `GET …/commands/allowed`
- UI: Commands panel on workspace detail — allowed-commands help, command
  input + optional subdir, outcome card (status/exit/duration/output,
  truncation notes), clear blocked-reason display, history; Chat Mode and
  archived workspaces disable execution
- 40 pytest (incl. marker-file proofs that blocked commands never execute,
  env-scrub and redaction proofs) + 9 vitest

## Runtime v1.4 — Orchestration Engine ✅

Turns a workspace goal into a structured, replayable workflow — and nothing
more. Status metadata only: orchestrated agents never write files, run
commands, or call models in v1.4 (the manual Files/Commands panels remain
user-triggered and the orchestrator never invokes them).

- `app/runtime/orchestration.py`: deterministic planner (fixed 5-step
  pipeline — plan → research → backend → UI → verify — with role keywords,
  per-step risk levels, and recorded-but-inert validation/approval flags),
  role-based assignment (ready > running > caution > suspicious;
  disabled/quarantined agents are never assigned — unassignable steps become
  blocked tasks with explicit reasons + `runtime.task.assignment_failed`),
  dependency-respecting scheduler tick (`_advance`: start eligible tasks,
  settle workflow to completed/failed/blocked), manual task results
  (bounded text) that complete tasks and advance the DAG
- Models: `RuntimeWorkflow` (planned/running/paused/blocked/failed/
  completed/cancelled), `RuntimeWorkflowPlan` (one per workflow),
  `RuntimeTask` (8 statuses; waiting_for_validation/approval reserved for
  later versions), `RuntimeTaskResult`
- 19 events `runtime.workflow.*` / `runtime.task.*` (shared registry,
  API + SDK) into the workspace activity run — timeline/replay reconstruct
  plan → assign → start → block → reroute → resume → complete
- Endpoints: workflows CRUD-lite, `POST …/plan`, `start|pause|resume|
  cancel`, `GET …/tasks`, `PATCH …/tasks/{id}` (status/reassign with
  unassignable-agent rejection), `POST …/tasks/{id}/result` — writes behind
  the existing API-key gate
- UI: Workflows panel on workspace detail — create from goal, generate
  plan, status banner + lifecycle controls, task cards (agent, status,
  risk, dependencies, artifacts, results, blocked reasons), record-result
  flow; Chat Mode and archived workspaces disable mutations
- 17 pytest (incl. a boundary test proving a full workflow cycle emits no
  sandbox.file/sandbox.command/model.* events and never creates a sandbox
  directory) + 10 vitest

## Runtime v1.5 — Action Enforcement Gateway ✅

Every important Runtime action becomes an ActionProposal, is evaluated by a
deterministic ordered policy registry, and resolves into an explainable
ActionDecision **before anything executes** — with matched rules, a
human-readable reason, redacted evidence, and a trust/risk snapshot.

- `app/runtime/enforcement.py`: 22 deterministic policies (priority-ordered,
  first match decides, every match recorded) covering: disabled/quarantined
  actors blocked; raw secrets in inputs blocked (evaluated against raw,
  stored redacted); path escapes + secret files blocked (reusing v1.2
  `check_path`); unsafe commands blocked (reusing v1.3 `evaluate`);
  missing-manifest commands → retry_with_constraints; protected domains
  (auth/payment/deployment/db-migration/package-install) + sensitive file
  paths + high-risk publishing → require_human_approval; unverified research
  + high-risk actors + flagged agent task results → reroute_to_verifier;
  extreme-risk actors → quarantine_agent; suspicious actors →
  downgrade_permissions; caution actors → allow_readonly reads; safe
  reads/writes/commands/metadata actions → allow; unknown/unmatched → block
- Integration: file write/delete/mkdir, command run, workflow start, and
  task-result recording all propose→evaluate→execute through the gateway;
  v1.2/v1.3 safety still runs after an allow (defense in depth), and
  refusals emit the legacy `sandbox.*.blocked` audit events for stream
  parity; approval-required actions halt with a clear 403 (resolution is
  v1.6 — no inbox exists)
- Generic API (`/actions/propose|/actions|/actions/{id}|/actions/{id}/
  evaluate`, `/runtime/policies`, `/enforcement/decisions`) records
  decisions but **never executes**
- 13 events (`action.proposed/started/completed/failed`,
  `policy.evaluated`, `policy.rule.matched`, `enforcement.allowed/blocked/
  approval_required/rerouted/retry_required/permissions_downgraded/
  quarantine_triggered`) — shared registry, API + SDK; timeline/replay
  reconstruct every decision
- UI: Enforcement panel (policy count, decision cards with badges +
  matched-rule chips + plain-English reasons, never-executes test form);
  Files/Commands panels surface blocked/approval reasons
- 22 pytest + 9 vitest; fixed a real redaction false-positive (`sk-`
  matching inside `task-…` ids)

## Runtime v1.6 — Human Approval System ✅

Resolves the v1.5 gateway's `require_human_approval` decisions. A halted
action now creates a pending **ApprovalRequest** (deduplicated per
unresolved action) carrying a plain-English summary, matched rules, risk
level, recommended decision, and — for file/command surfaces — the exact
stored payload to resume the action verbatim (payload never mutable, never
in events).

- `app/runtime/approvals.py`: approval lifecycle + safe-executor resume.
  Resolutions: **approve/approve_once** re-run the stored action through the
  existing v1.2 file service / v1.3 command runner (whose own safety
  re-runs — a command that no longer passes is refused even after approval);
  **deny** blocks it and marks the proposal blocked; **approve_readonly**
  runs only a safe read-only path or records a skip; **reroute** and
  **quarantine** are recorded as events/metadata only (a quarantine
  resolution emits `enforcement.quarantine_triggered` but does **not**
  restrict the agent — real quarantine is v1.7)
- Enforcement integration: `require_human_approval` decisions auto-create
  the approval and thread the approval ID into the 403 detail + proposal
  metadata; a new `approval-sensitive-command` rule (priority 34) halts
  allowlisted commands whose args touch auth/payment/deploy paths
- 10 events `approval.requested/approved/denied/cancelled/override_used/
  execution_resumed/execution_failed/execution_skipped/reroute_requested/
  quarantine_requested` (shared registry, API + SDK) into the workspace
  activity run; timeline/replay reconstruct request → resolution → resume
- Routes: `GET …/approvals[/pending-count|/{id}]`, `POST …/approvals/{id}/
  {approve|deny|approve-readonly|reroute|quarantine|cancel}` (writes gated)
- UI: Approvals panel (pending badge, cards with plain-English summary,
  matched-rule chips, expandable technical details, resolution buttons,
  resolved-status + execution outcome); Files/Commands surface the waiting
  approval ID in halted-action errors
- 17 pytest + 10 vitest

## Runtime v1.7 — Real Runtime Quarantine ✅

Upgrades quarantine from a status marker into an enforced restriction. A
quarantined agent's mutating runtime actions are refused before execution,
it is never assigned tasks, and its existing tasks are blocked.

- `app/runtime/quarantine.py`: lifecycle service (apply/lift) storing
  bookkeeping in `agent.meta["quarantine"]` (no column migration — works on
  existing DBs; preserved across metadata PATCHes, surfaced as a dedicated
  `quarantine` field). Quarantine blocks existing pending/running tasks and
  emits `runtime.task.blocked`; unquarantine restores the pre-quarantine
  status.
- Enforcement: the v1.5 `block-unassignable-actor` rule already refuses any
  quarantined actor's action before execution; v1.7 emits the
  quarantine-specific `agent.quarantine.blocked_action` alongside it, and the
  extreme-risk `quarantine_agent` decision now applies **real** quarantine.
  Files/Commands routes accept an `agent_id` so an agent-attributed mutating
  action is refused (disk untouched) — v1.2/v1.3 safety is unchanged.
- Approval: the v1.6 `quarantine` resolution now **really** quarantines the
  linked agent; approval cannot bypass quarantine (the quarantine rule
  outranks the approval rules — no approval is even created).
- Workflows: quarantined agents are never assigned tasks (v1.4 rule), and
  recording a result for a task assigned to a quarantined agent is blocked.
- 7 events `agent.quarantine.requested/enforced/blocked_action`,
  `agent.quarantined`, `agent.unquarantine.requested`, `agent.unquarantined`,
  `agent.permissions.restored` (shared registry, API + SDK) into the activity
  run; timeline/replay reconstruct the full quarantine → block → lift arc.
- Routes: `POST agents/{id}/quarantine|unquarantine`, `GET agents/{id}/
  quarantine`, `GET quarantine/events` (writes gated).
- UI: agent cards show the real quarantined state, reason, and a
  Quarantine/Unquarantine button; the block reason surfaces on halts.
- 17 pytest + 4 vitest.

## Runtime v1.8 — Deterministic Validators ✅

Evidence-based checks so AgentLab stops blindly trusting agent outputs. Every
validator is deterministic — no LLM judgment, no web browsing, no live
external fetch — and produces a `ValidatorResult` with bounded, redacted
evidence plus risk/trust scoring signals.

- `app/runtime/validators.py`: six validators —
  **secret_exposure** (api-key/private-key/.env patterns; fails with
  `[redacted]` snippets, never the raw secret), **code_syntax**
  (`ast.parse` for .py, `json.loads` for .json/package.json — no code runs),
  **command_result** (consumes the latest recorded v1.3 command event;
  exit 0 = pass — never re-runs anything), **research_claim** (validates a
  claim against *provided* cited evidence only; fails on missing url/fields/
  support), **data_flow** (consumer-vs-producer field comparison with a
  plain-English mismatch explanation), **business_risk** (flags
  payment/auth/deploy/customer-data/unverified changes → requires approval/
  validation + risk/trust deltas)
- 12 events (`validator.started/completed/failed`, `validation.passed/
  failed`, `claim.verified/rejected`, `schema.mismatch.detected`,
  `runtime.error.detected`, `app.error.translated`,
  `risky.file_change.detected`, `secret.exposure.detected`) — shared
  registry, API + SDK; timeline/replay reconstruct every result
- Narrow enforcement hook: a new `block-failed-validation` policy rule
  (priority 16) blocks actions tagged `metadata.validation_failed`
- Trust/Risk: results carry risk_delta/trust_delta as **scoring signals**;
  the deterministic v0.5 fold is not modified (documented limitation)
- Task linkage: running a validator with a `task_id` sets the task's
  `validation_status` metadata (no scheduler status change)
- Routes: `GET /runtime/validators`, `POST …/validators/run` (gated),
  `GET …/validators/results[/{id}]`
- UI: Validators panel (registry-aware run form, result cards with
  pass/fail badges, redacted secret evidence, failures, suggested actions,
  risk deltas, plain-English explanations)
- 25 pytest + 10 vitest

## Runtime v1.9 — Visual Project Debugging UI ✅

A beginner-friendly comprehension layer over every existing Runtime system —
a **read-only, deterministic** aggregation, not a new engine. Makes a
workspace understandable at a glance while keeping deep diagnostics one click
away.

- `app/runtime/debug.py`: pure aggregation over workspaces, agents,
  workflows/tasks, enforcement decisions, approvals, validators, quarantine
  state, sandbox status, and activity events. Mutates nothing, emits no
  events, creates no new behavior.
- **Health** (deterministic, severity-ordered, highest wins, all active
  surfaced): agent_restricted > approval_needed > validation_failed >
  blocked > build_test_failed > action_blocked > risky_change >
  safe_to_continue > no_signals (a freshly created workspace with only
  lifecycle events reads "No signals yet").
- **Recommended next actions** (deterministic): review approval, fix
  validation, inspect/unquarantine agent, reroute blocked task, fix command,
  initialize sandbox, create workflow, or "No action needed".
- **Issues** list (plain-English, severity-sorted, panel + ref links) from
  failed validators, quarantined agents, pending approvals, blocked/failed
  tasks & workflows, blocked enforcement decisions, and failed/timed-out
  commands.
- **Project map lite**: goal → workflows → tasks → agents → artifacts (+
  data-flow/claim validation nodes) derived from real rows, deduplicated —
  generic nodes, no demo hardcoding.
- Routes: `GET …/debug/summary`, `…/debug/issues`, `…/debug/project-map`
  (read-only, open in local mode).
- UI: **Project debugging** panel at the top of the workspace page — health
  banner, recommended actions, needs-attention issues, recent changes,
  activity/replay links, and a progressive-disclosure "Advanced diagnostics"
  toggle (agent/workflow/validation/enforcement summaries + project map).
- 15 pytest (incl. a read-only proof: activity count stable across repeated
  calls, and a no-secret/no-host-path proof) + 10 vitest.

## Runtime v2.0 — Bottle-Selling Website End-to-End Demo ✅

A one-click, deterministic end-to-end demo proving the existing runtime can
guide, govern, debug, validate, and replay the construction of a small real
project — a dependency-free **Tidewater Bottle Co.** storefront built inside
a workspace sandbox. **Not a new engine**: an isolated seed that orchestrates
existing services and emits their normal events. (Full walkthrough:
[docs/BOTTLE_SHOP_DEMO.md](BOTTLE_SHOP_DEMO.md).)

- `app/runtime/demo_bottle_shop.py`: deterministic seed —
  1) workspace + sandbox, 2) six agents (Planner/Researcher/Backend Coder/UI
  Agent/Verifier/Safety Reviewer), 3) a five-task workflow auto-assigned and
  walked to completion, 4) seven website files written **through the v1.5
  enforcement gateway** (README/index.html/styles.css/app.js/products.json/
  tests/docs), 5) `ls` + `python3 --version` through the v1.3 command runner,
  6) the five v1.8 validators (code-syntax/secret-exposure/command-result/
  data-flow pass; business-risk flags the payment feature), 7) a **governance
  halt**: the Backend Coder's payment-path write is held for human approval
  (the file is not written) — the user approves to resume the exact write or
  denies to keep it blocked.
- Route `POST /api/runtime/demo/bottle-shop` (gated) seeds and broadcasts
  the normal events; returns the workspace id + pending approval id.
- UI: a "Create Bottle Shop Demo" card on the Runtime list page and a demo
  banner on the workspace; the v1.9 Project Debugging panel is the headline
  view (Needs approval / Verification failed / Risky change).
- Safety: no secrets, no network/CDN, no package installs, no server, no
  real payments, no customer data; tests assert no host path or secret-shape
  ever leaks.
- 14 pytest + 4 vitest; reuses every existing service — no core system
  replaced, no demo-only logic leaked into generic runtime.

## Runtime v2.1.1 — Documentation & Acceptance Audit ✅ — Runtime v1 frozen

A docs-only audit patch (no runtime behavior, no engine). Added the full
Runtime v1 documentation set — [RUNTIME_DESIGN](docs/RUNTIME_DESIGN.md),
[SANDBOX_SAFETY](docs/SANDBOX_SAFETY.md), [ENFORCEMENT_POLICY](docs/ENFORCEMENT_POLICY.md),
[VALIDATOR_DESIGN](docs/VALIDATOR_DESIGN.md), [HUMAN_APPROVAL](docs/HUMAN_APPROVAL.md),
[NONTECHNICAL_USER_GUIDE](docs/NONTECHNICAL_USER_GUIDE.md),
[DEVELOPER_INTEGRATION_GUIDE](docs/DEVELOPER_INTEGRATION_GUIDE.md) — plus an
honest [RUNTIME_V1_ACCEPTANCE_MATRIX](docs/RUNTIME_V1_ACCEPTANCE_MATRIX.md)
(18 Complete / 6 Partial), a README positioning + docs index + a 10-point
limitations section. Version 2.1.1. **Runtime v1 is frozen as complete.**

## Runtime v2.1 — Final Hardening + Website Preview + Landing Page ✅ — Runtime v1 complete

The final Runtime v1 polish release. Closes the two biggest first-run UX gaps
without adding any new engine, and ships the milestone documentation.

- **Website Preview** (`app/runtime/preview.py`): a safe, read-only static
  serve of files already inside a workspace sandbox, so the generated Bottle
  Shop site renders inside AgentLab. Every path goes through the v1.2
  `check_path` (traversal/absolute/outside-root/secret rejected before any
  disk access); only an allowlist of static web extensions is served; a 2 MB
  cap bounds responses; file *content* is returned, never host paths.
  GET-only — never writes/runs/installs/deploys. Routes:
  `GET …/preview-status`, `GET …/preview[/{path}]`. The frontend renders it
  in a `sandbox="allow-scripts"` iframe (scripts isolated in an opaque
  origin) behind an opt-in "Open Website Preview" button, with a clean
  "no index.html" empty state.
- **Landing page** (`HomePage` at `/`): a clean product homepage — hero
  ("Build with AI. Stay in control."), what-AgentLab-does cards,
  how-it-works steps, positioning vs. code generators, and CTAs that one-click
  the Bottle Shop demo or open Runtime. `/` is now the landing page;
  `/dashboard` is unchanged; a Home nav entry was added.
- **Docs**: [BOTTLE_SHOP_DEMO.md](docs/BOTTLE_SHOP_DEMO.md) updated and a new
  [DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) — what AgentLab is, how to
  run locally, how to create the demo, how to open the preview, which panels
  to inspect, and the governance behaviors shown.
- 12 backend pytest (preview path-safety/extension/host-path proofs) + 6
  vitest (landing page CTAs, preview panel states). Version 2.1.0.

**Runtime v1 is complete** — observe → replay → score → profile → gateway →
studio → workspaces → agents → sandbox files → safe commands → orchestration
→ enforcement → approvals → real quarantine → validators → visual debugging
→ end-to-end demo → preview + landing.

# Runtime v2 — Live Agent Execution

## v3.0 — Live Agent Execution (single governed step) ✅

The first version where an agent's **own model actually builds** — connecting
the model side (v0.7 gateway / BYOK) to the governed runtime. One bounded pass,
not an autonomous loop:

- **`app/runtime/agent_build.py`**: take the workspace goal → one real model
  call through the gateway using the agent's own provider/model (e.g. local
  `ollama/llama3.2`) → parse a strict JSON file manifest (tolerant of markdown
  fences; a malformed/empty response writes **nothing**) → route **every**
  proposed file write through `enforcement.guarded_execute` attributed to the
  agent. So v1.2 path safety, v1.5 policy, v1.6 approval, and v1.7 quarantine
  all apply unchanged: safe files land in the sandbox, sensitive paths
  (auth/payment/deploy) **halt for human approval**, unsafe paths are blocked
  (disk untouched). Model output is redacted before it enters telemetry.
- Route `POST /runtime/workspaces/{id}/agent-build` (API-key gated); a
  quarantined agent is refused (409).
- Events `agent.build.started/completed/failed` plus the existing `model.*` /
  `action.*` / `enforcement.*` / `sandbox.file.*` — Replay reconstructs the
  full chain (model call → enforcement decision → written/held/blocked).
- UI: **Agent build** panel on the workspace — pick an agent, optional prompt,
  "Build with agent" → per-file governance outcomes; written files render in
  the **Website preview**, held files appear in **Approvals**.
- 9 backend pytest (governed-pipeline proofs incl. a real telemetry-leak fix)
  + 8 vitest. **Live-verified with real ollama/llama3.2**: generated a
  previewable two-file site through the full governed pipeline (210/175
  tokens). Version 3.0.0.

> v3.0 is a **single pass**, not an autonomous loop: no iteration, no
> agent-driven command execution, no multi-step planning. Those are v3.1
> (bounded loop + governed commands + validator feedback) and v3.2 (pause/
> resume the loop on approval). Output quality is the model's; the governance
> is identical regardless of model.

## v3.1 — Bounded Agent Loop ✅

Wraps the v3.0 single-pass body in a **bounded iteration** — the first version
where an agent builds over several steps, reacting to what actually happened.
No new engine: the gateway, enforcement, approvals, sandbox, command runner,
and validators are all reused unchanged.

- **`app/runtime/agent_run.py`**: loop of up to `max_steps` passes (default 6,
  hard-capped at 8). Each step builds a prompt from the goal + the **current
  sandbox file tree** + the **previous step's validator/command feedback** →
  one real gateway call → parses a step manifest (`{summary, done, files[],
  commands[]}`, reusing v3.0's tolerant JSON/HTML salvage) → applies actions.
- **Governed commands.** A step can propose `command.run` actions alongside
  file writes; both are attributed to the agent and routed through the **same**
  `enforcement.guarded_execute` choke point (v1.3 allowlist + v1.5 policy +
  v1.6 approval + v1.7 quarantine all apply). Safe commands run via the v1.3
  runner; unsafe ones are blocked before execution.
- **Validator feedback.** After each step, deterministic validators run over
  its outputs — `secret_exposure` (every written file), `code_syntax`
  (.py/.json), `command_result` (if a command ran) — and their pass/fail is
  fed verbatim into the next prompt.
- **Stop conditions.** The loop stops on a model `done` signal, an empty step,
  max steps, an unrecoverable error (failed/malformed model response), or the
  first approval-required action — which is **recorded and the loop stops
  cleanly** (pause/resume across an approval is v3.2, deliberately not built).
- Route `POST /runtime/workspaces/{id}/agent-run` (API-key gated; 409 if the
  agent is quarantined). Events `runtime.agent_run.started/step/completed/
  failed` plus the per-step `model.*`/`action.*`/`enforcement.*`/`sandbox.*`/
  `validator.*` — Replay reconstructs the whole multi-step build.
- UI: **Agent run** panel on the workspace — pick an agent, a max-step count,
  optional prompt; renders a per-step timeline (files, commands, validator
  badges) and a plain-English stop reason.
- 17 backend pytest + 8 vitest. **Live-verified with real ollama/llama3.2**: a
  3-step loop that wrote `notes.txt`/`data.json`/`index.html`, ran governed
  `ls` commands (exit 0), and passed `code_syntax`/`secret_exposure`/
  `command_result` validators that fed each next step. Version 3.1.0.

> v3.1 still does **not** pause/resume across an approval — the first
> approval-required action stops the loop cleanly with a pending approval. That
> resume-on-approval flow is v3.2.

## v3.2 — Pause / Resume the Loop on Approval ✅

Closes the v3.1 gap: a bounded run that hits an approval-required action now
**pauses** as a persisted, resumable run instead of ending — and once the human
resolves the approval, the loop **resumes** from the next step. Still no new
engine: it reuses the v1.6 approval flow and the v3.1 loop verbatim.

- **`AgentRun` state row** (`runtime_agent_runs`): the loop is persisted (goal,
  step cursor, accumulated per-step outcomes, the next-prompt context, and the
  approvals blocking a resume), so it survives across requests. Statuses:
  `running` / `awaiting_approval` / `completed` / `failed`.
- **Pause.** When a step holds an action for approval, the run is saved as
  `awaiting_approval` with `pending_approval_ids` and a
  `runtime.agent_run.paused` event. The `POST …/agent-run` response now returns
  `run_id`, `status`, and `pending_approval_ids` instead of forcing completion.
- **Resume.** `POST …/agent-run/{run_id}/resume` (gated): refuses while any
  linked approval is still pending (409); otherwise refreshes the prompt context
  from the current sandbox (an approved file now exists on disk) plus a note for
  each resolution, reconciles the held step outcome to `approved`/`denied`, emits
  `runtime.agent_run.resumed`, and drives the loop from the next step. It can
  pause again on a later approval — fully re-resumable. `GET …/agent-run/{run_id}`
  exposes the current state.
- The approval itself is resolved through the **existing v1.6 flow**
  (approve writes the held action, deny keeps it blocked) — `approvals.resolve`
  is untouched and stays decoupled from the loop.
- UI: the **Agent run** panel shows an amber "paused — N actions waiting for
  approval" banner with a **Resume agent loop** button once the run is
  `awaiting_approval`.
- 8 backend pytest (pause persists, resume blocked while pending, resume after
  approve/deny, re-pause, 404/409 guards, gating) + 1 vitest. **Live-verified
  with real ollama/llama3.2**: a run paused on a payment-path write, the write
  was approved, and the loop resumed to completion. Version 3.2.0.

> This completes the Live Agent Execution arc (v3.0 → v3.1 → v3.2). Everything
> beyond is the unscheduled backlog below.

## Later (unscheduled)

- Framework integrations: LangGraph / CrewAI / OpenAI Agents SDK / MCP
  adapters, auto-instrumentation, OpenTelemetry span export, Alembic
  migrations (lands with the first relational schema change)
- Teams & projects: per-project key management, scoped tokens, multi-user
  roles, retention/archival, saved views, run comparison
- Hosted platform: managed multi-tenant deployment, ingest quotas, alerting,
  audit logging

---

### Engineering debt ledger (tracked honestly)

- Alembic migrations deferred until the first relational schema change
  (v0.3 added no tables — faults are events)
- Read API is unauthenticated in local mode (auth lands v0.10)
- Trust/risk engine scores and explains but does not enforce (no routing
  impact, no score decay, quarantine is a marker) — enforcement is future work
- Replay folds from scratch per cursor move (snapshot memoization when tapes
  get large); replay tape doesn't grow live for still-running runs
- Dashboard bundle could code-split React Flow / Recharts routes
- `examples/langgraph_integration/` arrives with v0.4 adapters
