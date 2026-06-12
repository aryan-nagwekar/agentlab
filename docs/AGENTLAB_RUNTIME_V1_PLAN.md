# AgentLab Runtime v1 — Master Plan

> Provided by the project owner on 2026-06-12, after approval of v0.9.1.
> This document is the master roadmap for the Runtime phase. The owner
> provided the v1.0 portion below; later-version specs (v1.1+) will be
> appended to this document when provided. Implementation proceeds one
> version at a time, each gated on explicit owner approval.
>
> Known future milestone referenced by the owner: **v1.1 Workspace Agent
> Definitions + Permissions**. Later Runtime versions own (per the strict
> out-of-scope list below): sandbox execution, command runner, file writes,
> orchestration engine, enforcement gateway, policy blocking, human
> approvals, validators, real runtime quarantine, and the bottle-selling
> website demo.

---

Now begin the Runtime v1 phase, but do not overbuild.

## First required step

Save the full plan exactly into `docs/AGENTLAB_RUNTIME_V1_PLAN.md`, read it
carefully, and treat it as the master roadmap for the Runtime phase.

Do not implement the entire Runtime v1 plan.

After saving the plan, implement ONLY:

# AgentLab v1.0 — Runtime Workspaces

## Goal

Add the foundation for Runtime Workspaces.

A workspace represents a future AI-built software project area inside
AgentLab, but in v1.0 it is metadata and UI only. It should not execute
commands, write project files, run sandbox actions, enforce policies, or
perform approvals yet.

## Scope for v1.0

Implement:

- Workspace backend model
- Workspace artifact model
- Workspace status lifecycle
- Workspace CRUD APIs
- Workspace events emitted into the existing AgentLab event log
- Workspace list UI
- Workspace detail UI
- Workspace status banner
- Goal summary panel
- Recent activity panel
- Basic project health placeholder
- Association between workspace and AgentLab project/run where appropriate
- Tests
- Docs

## Workspace concepts

A workspace should include fields like:

- workspace_id
- name
- goal / description
- status
- created_at
- updated_at
- optional linked project/run metadata
- metadata fields useful for future Runtime versions

Suggested workspace statuses:

- draft
- active
- paused
- completed
- archived
- failed

Use sensible naming based on existing AgentLab style.

## Workspace artifact model

Add a basic artifact model for future project outputs, but keep it
metadata-only in v1.0.

Artifacts may include:

- artifact_id
- workspace_id
- name
- type
- path or logical reference
- created_at
- updated_at
- metadata

Important: do not build file editing, sandbox writes, command execution, or
validators yet.

## Events

Workspace actions should emit normal AgentLab events into the existing event
system.

Examples:

- workspace.created
- workspace.updated
- workspace.status_changed
- workspace.archived
- workspace.artifact_registered

Events must appear in the normal event/timeline/replay systems where
appropriate.

Follow existing AgentLab architecture:

- raw events remain source of truth
- important actions emit events
- replay should be able to reconstruct workspace-related activity
- do not create a separate incompatible event path

## Backend APIs

Add workspace APIs.

Suggested routes:

- GET /api/runtime/workspaces
- POST /api/runtime/workspaces
- GET /api/runtime/workspaces/{workspace_id}
- PATCH /api/runtime/workspaces/{workspace_id}
- DELETE or archive /api/runtime/workspaces/{workspace_id}
- GET /api/runtime/workspaces/{workspace_id}/activity
- GET /api/runtime/workspaces/{workspace_id}/artifacts
- POST /api/runtime/workspaces/{workspace_id}/artifacts

Exact route names may follow the repo's conventions.

## Frontend

Add Runtime / Workspaces UI.

Required UI:

- Workspace list page
- Create workspace flow
- Workspace detail page
- Status banner
- Goal summary
- Recent activity panel
- Basic project health placeholder
- Empty states
- Links back to relevant runs/replay/details where applicable

Keep UI simple and clear. This is the foundation, not the full Runtime UI.

## Strictly out of scope

Do NOT implement:

- sandbox execution
- command runner
- shell commands
- file writes
- project file editing
- orchestration engine
- enforcement gateway
- policy blocking
- human approvals
- validators
- real runtime quarantine
- bottle-selling website demo
- deployment
- cloud sync
- multi-user permissions

Those belong to later Runtime versions.

## Testing requirements

Add tests for:

- creating a workspace
- listing workspaces
- reading workspace detail
- updating workspace metadata
- changing workspace status
- archiving/deleting workspace according to chosen design
- registering workspace artifact metadata
- workspace events emitted correctly
- workspace events do not break replay/timeline/event APIs
- existing v0.1-v0.9.1 tests still pass

Run the full backend and frontend test suites.

## Documentation

Update docs with:

- Runtime v1 roadmap reference
- what v1.0 Workspaces adds
- workspace data model
- workspace lifecycle
- workspace events
- clear statement that v1.0 does not run commands, edit files, sandbox code,
  enforce policy, or approve actions yet

## Acceptance criteria

v1.0 is complete only if:

- The Runtime v1 master plan is saved at docs/AGENTLAB_RUNTIME_V1_PLAN.md
- User can create a workspace
- User can list workspaces
- User can open workspace detail page
- User can update workspace metadata/status
- Workspace artifact metadata can be registered
- Workspace actions emit normal AgentLab events
- Workspace events appear in activity/timeline/replay where appropriate
- Existing v0.1-v0.9.1 features do not regress
- No sandbox/enforcement/approval/validator/command-runner systems are built
- Tests pass
- Docs are updated

## v1.1 — Workspace Agent Definitions + Permissions ✅ (shipped)

First-class agent definitions inside a workspace. **Metadata and permissions
only** — agents do not execute, run commands, write files, call tools, enforce
policy, request approvals, run validators, or quarantine at runtime.

- **Model** `WorkspaceAgent` (`runtime_workspace_agents`, composite PK
  `(workspace_id, id)`): name, role, description, system_prompt,
  model_provider/model_name (Model Gateway vocabulary; keyless mock default),
  allowed_tools/denied_tools, a 13-flag permission profile, budget ceilings
  (max_tokens_per_call / max_calls_per_run / max_tool_calls_per_run),
  requires_verification, trust_score/risk_score, status, metadata.
- **Statuses** ready / running / caution / suspicious / quarantined /
  disabled. quarantined & disabled gate *assignment* in the UI only.
- **Permissions** can_read_files, can_write_files, can_delete_files,
  can_run_commands, can_call_web, can_access_database, can_modify_auth,
  can_modify_payment, can_modify_deployment, can_send_to_agents,
  can_send_to_user, can_save_product_data, can_use_unverified_research.
  Risky flags (write/delete files, run commands, database, auth, payment,
  deployment) are warned in the UI; all are future-enforcement inputs.
- **Templates** (data, not a runtime): Planner, UI, Backend Coder, Researcher,
  Marketing, Verifier, Safety Reviewer.
- **Events** workspace_agent.created / updated / permission_changed /
  status_changed / deleted / template_instantiated — shared registry (API +
  SDK), emitted into the workspace activity run so timeline/replay work.
- **APIs** `/runtime/workspaces/{id}/agents` CRUD, `/runtime/agent-templates`,
  `/runtime/workspaces/{id}/agents/from-template/{template_id}`.
- **UI** Agents panel on workspace detail: template picker, agent cards
  (role/model/status/trust/risk/permissions with risky flags warned), inline
  editor, delete; quarantined/disabled dimmed; Chat Mode disables mutations.

## v1.2 — Sandboxed File Runtime ✅ (shipped)

The first real runtime layer, **file operations only**, confined to
`{AGENTLAB_WORKSPACES_ROOT}/{workspace_id}` (default `.agentlab-workspaces/`,
gitignored). No shell, no command runner, no build/test execution, no dev
server, no orchestration, no enforcement, no approvals, no validators, no
real quarantine.

- **Module** `app/runtime/sandbox.py`: deterministic path safety before any
  disk access — absolute paths, `..` traversal, null bytes, secret-named
  files (`.env*`, `*.pem`, `*.key`, `id_rsa*`, …), and paths *resolving*
  outside the workspace root (also the symlink-escape guard) are rejected.
  A rejected operation never touches disk and emits `sandbox.file.blocked`
  (operation, attempted logical path, reason, matched rule — never host
  paths or content).
- **Operations** init (idempotent) / status / list / tree / read (UTF-8,
  256 KB cap) / write (1 MB cap, parents auto-created) / mkdir / delete
  (files + empty directories).
- **Events** sandbox.initialized / file.created / file.updated / file.read /
  file.deleted / directory.created / file.blocked — shared registry (API +
  SDK), emitted into the workspace activity run so activity/timeline/replay
  work; payloads carry logical paths, sizes, sha256 prefixes only.
- **APIs** `/runtime/workspaces/{id}/sandbox/init|status`, `/files`,
  `/files/tree`, `/files/read`, `/files/write`, `/files/mkdir`,
  `DELETE /files` — writes behind the existing API-key gate.
- **UI** Files panel on workspace detail: status card + initialize flow,
  recursive tree, new file/folder, read/edit/save editor, delete, safe
  blocked-path errors; Chat Mode disables mutations; archived = read-only.

## Next milestone (gated on explicit approval)

**v1.3 — Safe Command Runner + Sandbox Events** (spec to be provided by the
owner; do not start without approval).
