"""Action Enforcement Gateway (v1.5).

Every important Runtime action becomes an ActionProposal, is evaluated by a
deterministic, ordered policy registry, and resolves into an explainable
ActionDecision *before* anything executes. Decisions record every matched
rule, a human-readable reason, redacted evidence, and a trust/risk snapshot,
and every step emits events through the normal collector pipeline — so
timeline and replay reconstruct what AgentLab allowed, blocked, or flagged.

Hard boundaries for v1.5:
- `require_human_approval` is recorded and halts execution, but there is no
  approval inbox or approve/deny/resume flow (v1.6).
- `quarantine_agent` / `downgrade_permissions` / `reroute_to_verifier` /
  `retry_with_constraints` are single-action decisions recorded as events —
  no real quarantine lifecycle (v1.7) and no validators (v1.8) exist.
- Nothing here adds autonomous execution: integrated actions remain
  user-triggered, and the generic proposal API never executes anything.

Defense in depth: the v1.2 path-safety and v1.3 command-safety layers keep
running *after* an enforcement allow — the gateway reuses their checkers for
its own rules but never replaces them.
"""
from __future__ import annotations

import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as core_models
from .commands import CommandBlock, _redact
from .commands import evaluate as evaluate_command
from .models import (
    EXECUTABLE_DECISIONS,
    UNASSIGNABLE_AGENT_STATUSES,
    ActionDecision,
    ActionProposal,
    RuntimeTask,
    Workspace,
    WorkspaceAgent,
)
from .sandbox import PathViolation, SandboxBlocked, check_path, sandbox_root
from .service import _emit

# Every action type the gateway understands. Anything else is blocked by the
# default rule — if uncertain, block.
KNOWN_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "file.read",
        "file.write",
        "file.delete",
        "directory.create",
        "command.run",
        "model.call",
        "workflow.start",
        "task.start",
        "task.result_record",
        "artifact.save",
        "message.send",
        "data.save",
        "auth.modify",
        "payment.modify",
        "deployment.modify",
        "package.install",
        "database.migration",
        "final_output.publish",
    }
)

# Action types that always require a human decision (v1.6 resolves them; in
# v1.5 they are recorded and never executed).
PROTECTED_ACTION_TYPES: frozenset[str] = frozenset(
    {"auth.modify", "payment.modify", "deployment.modify", "database.migration",
     "package.install"}
)

MUTATING_ACTION_TYPES: frozenset[str] = frozenset(
    {"file.write", "file.delete", "directory.create", "command.run", "data.save",
     "artifact.save", "task.result_record", "deployment.modify", "auth.modify",
     "payment.modify", "database.migration", "package.install",
     "final_output.publish"}
)

# Path segments that mark a file as auth/payment/deployment-sensitive. A
# write/delete touching them requires human approval (resolution in v1.6).
SENSITIVE_PATH_TOKENS: tuple[str, ...] = (
    "auth", "login", "password", "payment", "billing", "checkout", "stripe",
    "deploy",
)
SENSITIVE_FILENAMES: frozenset[str] = frozenset(
    {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
)

DECISION_EVENTS: dict[str, str] = {
    "allow": "enforcement.allowed",
    "allow_readonly": "enforcement.allowed",
    "allow_sandbox_only": "enforcement.allowed",
    "block": "enforcement.blocked",
    "require_human_approval": "enforcement.approval_required",
    "reroute_to_verifier": "enforcement.rerouted",
    "retry_with_constraints": "enforcement.retry_required",
    "downgrade_permissions": "enforcement.permissions_downgraded",
    "quarantine_agent": "enforcement.quarantine_triggered",
}

_DECISION_STATUS: dict[str, str] = {
    "allow": "allowed",
    "allow_readonly": "allowed",
    "allow_sandbox_only": "allowed",
    "block": "blocked",
    "require_human_approval": "approval_required",
    "reroute_to_verifier": "rerouted",
    "retry_with_constraints": "blocked",
    "downgrade_permissions": "blocked",
    "quarantine_agent": "blocked",
}


def _contains_secret(text: str) -> bool:
    return _redact(text) != text


def _is_sensitive_path(target: str) -> str | None:
    """The matched sensitive token, or None."""
    lowered = target.lower()
    for part in lowered.replace("\\", "/").split("/"):
        if part in SENSITIVE_FILENAMES:
            return part
        for token in SENSITIVE_PATH_TOKENS:
            if token in part:
                return token
    return None


@dataclass
class ActionContext:
    """Everything a policy condition may inspect — computed once, before
    any rule runs and before anything touches disk."""

    workspace: Workspace
    root: Path
    actor_type: str
    action_type: str
    target: str
    input_summary: str
    sensitivity_level: str
    requires_approval_hint: bool
    metadata: dict[str, Any]
    agent: WorkspaceAgent | None
    task: RuntimeTask | None
    path_violation: PathViolation | None = None
    command_block: CommandBlock | None = None

    @property
    def is_file_action(self) -> bool:
        return self.action_type.startswith("file.") or self.action_type == "directory.create"

    @property
    def actor_is_verifier(self) -> bool:
        if self.agent is None:
            return False
        return any(k in f"{self.agent.role} {self.agent.name}".lower() for k in ("verif", "review", "safety"))


def build_context(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    *,
    actor_type: str,
    action_type: str,
    target: str,
    input_summary: str,
    sensitivity_level: str,
    requires_approval_hint: bool,
    metadata: dict[str, Any],
    agent_id: str | None,
    task_id: str | None,
) -> ActionContext:
    agent = (
        session.get(WorkspaceAgent, {"workspace_id": workspace.id, "id": agent_id})
        if agent_id
        else None
    )
    task = session.get(RuntimeTask, task_id) if task_id else None
    ctx = ActionContext(
        workspace=workspace,
        root=sandbox_root(workspaces_root, workspace.id),
        actor_type=actor_type,
        action_type=action_type,
        target=target,
        input_summary=input_summary,
        sensitivity_level=sensitivity_level,
        requires_approval_hint=requires_approval_hint,
        metadata=metadata or {},
        agent=agent,
        task=task,
    )
    if ctx.is_file_action and target:
        try:
            check_path(ctx.root, target)
        except PathViolation as violation:
            ctx.path_violation = violation
    if action_type == "command.run":
        command = str(ctx.metadata.get("command", ""))
        args = [str(a) for a in ctx.metadata.get("args", [])]
        if not command and target:
            try:
                tokens = shlex.split(target)
            except ValueError:
                tokens = target.split()
            command, args = (tokens[0], tokens[1:]) if tokens else ("", [])
        try:
            evaluate_command(command, args, ctx.root)
        except (CommandBlock, PathViolation) as blocked:
            if isinstance(blocked, PathViolation):
                ctx.command_block = CommandBlock(blocked.reason, blocked.rule)
            else:
                ctx.command_block = blocked
    return ctx


# ------------------------------------------------------------ policy registry

Condition = Callable[[ActionContext], dict[str, Any] | None]


@dataclass(frozen=True)
class PolicyRule:
    """One deterministic rule. `condition` returns evidence when it matches.
    Lower priority number = evaluated/decides first."""

    id: str
    name: str
    description: str
    priority: int
    decision: str
    reason: str
    condition: Condition
    action_types: frozenset[str] | None = None  # None = any
    enabled: bool = True
    risk_delta: float = 0.0
    trust_delta: float = 0.0

    def applies_to(self, action_type: str) -> bool:
        return self.action_types is None or action_type in self.action_types


def _rule_unassignable_actor(ctx: ActionContext) -> dict | None:
    if ctx.agent is not None and ctx.agent.status in UNASSIGNABLE_AGENT_STATUSES:
        return {"agent_status": ctx.agent.status, "agent_id": ctx.agent.id}
    return None


def _rule_secret_in_input(ctx: ActionContext) -> dict | None:
    if _contains_secret(ctx.input_summary) or _contains_secret(ctx.target):
        return {"detail": "secret-like token detected in proposal input"}
    return None


def _rule_path_escape(ctx: ActionContext) -> dict | None:
    if ctx.path_violation is not None and ctx.path_violation.rule != "secret_file":
        return {
            "legacy_rule": ctx.path_violation.rule,
            "legacy_reason": ctx.path_violation.reason,
        }
    return None


def _rule_secret_file(ctx: ActionContext) -> dict | None:
    if ctx.path_violation is not None and ctx.path_violation.rule == "secret_file":
        return {
            "legacy_rule": "secret_file",
            "legacy_reason": ctx.path_violation.reason,
        }
    return None


def _rule_unsafe_command(ctx: ActionContext) -> dict | None:
    if ctx.command_block is not None and ctx.command_block.rule != "missing_manifest":
        return {
            "legacy_rule": ctx.command_block.rule,
            "legacy_reason": ctx.command_block.reason,
        }
    return None


def _rule_retry_manifest(ctx: ActionContext) -> dict | None:
    if ctx.command_block is not None and ctx.command_block.rule == "missing_manifest":
        return {
            "legacy_rule": "missing_manifest",
            "legacy_reason": ctx.command_block.reason,
            "constraint": "create the missing project manifest, then retry",
        }
    return None


def _rule_sensitive_file(ctx: ActionContext) -> dict | None:
    if ctx.action_type in ("file.write", "file.delete") and ctx.path_violation is None:
        token = _is_sensitive_path(ctx.target)
        if token:
            return {"sensitive_token": token}
    return None


def _rule_protected_action(ctx: ActionContext) -> dict | None:
    if ctx.action_type in PROTECTED_ACTION_TYPES:
        return {"detail": f"{ctx.action_type} always requires a human decision"}
    return None


def _rule_high_risk_publish(ctx: ActionContext) -> dict | None:
    if ctx.action_type == "final_output.publish" and (
        ctx.sensitivity_level == "high" or ctx.requires_approval_hint
    ):
        return {"sensitivity_level": ctx.sensitivity_level}
    return None


def _rule_extreme_risk_actor(ctx: ActionContext) -> dict | None:
    if ctx.agent is not None and ctx.agent.risk_score >= 0.9:
        return {"risk_score": ctx.agent.risk_score, "agent_id": ctx.agent.id}
    return None


def _rule_high_risk_actor(ctx: ActionContext) -> dict | None:
    if ctx.agent is not None and ctx.agent.risk_score >= 0.7:
        return {"risk_score": ctx.agent.risk_score, "agent_id": ctx.agent.id}
    return None


def _rule_unverified_research(ctx: ActionContext) -> dict | None:
    if ctx.metadata.get("unverified_research"):
        return {"detail": "input marked as unverified research"}
    return None


def _rule_flagged_result_approval(ctx: ActionContext) -> dict | None:
    if (
        ctx.action_type == "task.result_record"
        and ctx.actor_type != "user"
        and ctx.task is not None
        and ctx.task.requires_approval
    ):
        return {"task_id": ctx.task.id, "flag": "requires_approval"}
    return None


def _rule_flagged_result_verification(ctx: ActionContext) -> dict | None:
    if (
        ctx.action_type == "task.result_record"
        and ctx.actor_type != "user"
        and ctx.task is not None
        and (ctx.task.requires_validation or ctx.task.risk_level == "high")
        and not ctx.actor_is_verifier
    ):
        return {"task_id": ctx.task.id, "risk_level": ctx.task.risk_level}
    return None


def _rule_suspicious_actor_downgrade(ctx: ActionContext) -> dict | None:
    if (
        ctx.agent is not None
        and ctx.agent.status == "suspicious"
        and ctx.action_type in MUTATING_ACTION_TYPES
    ):
        return {"agent_status": "suspicious", "agent_id": ctx.agent.id}
    return None


def _rule_allow_sandbox_command(ctx: ActionContext) -> dict | None:
    if ctx.action_type == "command.run" and ctx.command_block is None:
        return {"detail": "command passed v1.3 deterministic safety"}
    return None


def _rule_allow_readonly_caution(ctx: ActionContext) -> dict | None:
    if ctx.agent is not None and ctx.agent.status == "caution" and ctx.action_type == "file.read":
        return {"agent_status": "caution"}
    return None


def _rule_allow_file_read(ctx: ActionContext) -> dict | None:
    if ctx.action_type == "file.read" and ctx.path_violation is None:
        return {}
    return None


def _rule_allow_file_write(ctx: ActionContext) -> dict | None:
    if (
        ctx.action_type in ("file.write", "file.delete", "directory.create")
        and ctx.path_violation is None
    ):
        return {}
    return None


def _rule_allow_metadata_action(ctx: ActionContext) -> dict | None:
    # final_output.publish lands here only when not flagged high-risk (the
    # approval rule outranks this one).
    if ctx.action_type in (
        "workflow.start", "task.start", "task.result_record", "artifact.save",
        "message.send", "model.call", "data.save", "final_output.publish",
    ):
        evidence: dict[str, Any] = {}
        if (
            ctx.action_type == "task.result_record"
            and ctx.task is not None
            and (ctx.task.requires_approval or ctx.task.requires_validation)
        ):
            evidence["note"] = (
                "task is flagged for approval/validation; recorded manually by the "
                "user — approval resolution (v1.6) and validators (v1.8) will gate "
                "this for agent actors"
            )
        return evidence
    return None


def _rule_block_unknown(ctx: ActionContext) -> dict | None:
    if ctx.action_type not in KNOWN_ACTION_TYPES:
        return {"detail": f"unknown action type {ctx.action_type!r}"}
    return None


def _rule_default_block(ctx: ActionContext) -> dict | None:
    # Absolute catch-all so evaluation always has a deciding rule — a known
    # action type with no specific terminal rule is blocked, never assumed.
    return {"detail": "no specific policy matched; blocked by default"}


POLICY_RULES: list[PolicyRule] = sorted(
    [
        PolicyRule(
            "block-unassignable-actor", "Block disabled/quarantined actors",
            "Agents whose definition is disabled or quarantined cannot act.",
            10, "block",
            "the acting agent definition is disabled or quarantined",
            _rule_unassignable_actor,
        ),
        PolicyRule(
            "block-secret-in-input", "Block raw secrets in inputs",
            "Proposals whose input or target contains secret-like tokens are rejected.",
            15, "block",
            "the proposal input appears to contain a raw secret",
            _rule_secret_in_input,
        ),
        PolicyRule(
            "block-path-escape", "Block path escapes",
            "File paths that are absolute, traverse, or resolve outside the sandbox are rejected.",
            20, "block",
            "the target path escapes the workspace sandbox",
            _rule_path_escape,
        ),
        PolicyRule(
            "block-secret-file", "Block secret-like files",
            "Secret-named files (.env, keys, …) are never readable or writable.",
            21, "block",
            "the target is a secret-like file",
            _rule_secret_file,
        ),
        PolicyRule(
            "block-unsafe-command", "Block unsafe commands",
            "Commands failing v1.3 deterministic safety (dangerous/unknown/shell/inline/install) are rejected.",
            30, "block",
            "the command failed deterministic command safety",
            _rule_unsafe_command, frozenset({"command.run"}),
        ),
        PolicyRule(
            "retry-missing-manifest", "Retry after adding manifest",
            "npm test/build and pytest need a project manifest; retry once it exists.",
            31, "retry_with_constraints",
            "the command needs a project manifest that does not exist yet",
            _rule_retry_manifest, frozenset({"command.run"}),
        ),
        PolicyRule(
            "approval-protected-action", "Protected domains need approval",
            "Auth/payment/deployment/database-migration/package-install actions require a human decision.",
            35, "require_human_approval",
            "this action touches a protected domain and needs human approval",
            _rule_protected_action,
        ),
        PolicyRule(
            "approval-sensitive-file", "Sensitive file changes need approval",
            "Writes/deletes touching auth/payment/deployment-related paths require a human decision.",
            40, "require_human_approval",
            "the file touches auth/payment/deployment-sensitive paths and needs human approval",
            _rule_sensitive_file, frozenset({"file.write", "file.delete"}),
        ),
        PolicyRule(
            "approval-high-risk-publish", "High-risk publishing needs approval",
            "Publishing final output marked high-risk requires a human decision.",
            42, "require_human_approval",
            "publishing high-risk output needs human approval",
            _rule_high_risk_publish, frozenset({"final_output.publish"}),
        ),
        PolicyRule(
            "quarantine-extreme-risk-actor", "Quarantine extreme-risk actors",
            "Agents with risk ≥ 0.9 trigger a quarantine decision (real quarantine arrives in v1.7).",
            45, "quarantine_agent",
            "the acting agent's risk score is extreme; quarantine was triggered",
            _rule_extreme_risk_actor, risk_delta=0.1,
        ),
        PolicyRule(
            "reroute-high-risk-actor", "Reroute high-risk actors",
            "Actions from agents with risk ≥ 0.7 are rerouted to a verifier.",
            50, "reroute_to_verifier",
            "the acting agent's risk score is high; the action was rerouted to a verifier",
            _rule_high_risk_actor, risk_delta=0.05,
        ),
        PolicyRule(
            "reroute-unverified-research", "Reroute unverified research",
            "Actions based on unverified research are rerouted to a verifier.",
            51, "reroute_to_verifier",
            "the input is unverified research and must be verified first",
            _rule_unverified_research,
        ),
        PolicyRule(
            "approval-flagged-task-result", "Flagged task results need approval",
            "Agent-recorded results for approval-flagged tasks require a human decision.",
            52, "require_human_approval",
            "this task is flagged requires_approval; an agent cannot finalize it alone",
            _rule_flagged_result_approval, frozenset({"task.result_record"}),
        ),
        PolicyRule(
            "reroute-flagged-task-result", "Verify flagged task results",
            "Agent-recorded results for validation-flagged/high-risk tasks reroute to a verifier.",
            53, "reroute_to_verifier",
            "this task requires verification and the actor is not a verifier",
            _rule_flagged_result_verification, frozenset({"task.result_record"}),
        ),
        PolicyRule(
            "downgrade-suspicious-actor", "Downgrade suspicious actors",
            "Mutating actions from suspicious agents are downgraded (read-only inspection stays available).",
            55, "downgrade_permissions",
            "the acting agent is suspicious; its permissions were downgraded for this action",
            _rule_suspicious_actor_downgrade,
        ),
        PolicyRule(
            "allow-sandbox-command", "Allow sandboxed commands",
            "Commands that pass v1.3 safety run sandbox-only.",
            60, "allow_sandbox_only",
            "the command is allowlisted and runs inside the sandbox only",
            _rule_allow_sandbox_command, frozenset({"command.run"}),
        ),
        PolicyRule(
            "allow-readonly-caution", "Read-only for caution actors",
            "Caution-status agents keep read-only inspection access.",
            70, "allow_readonly",
            "caution agents may inspect read-only",
            _rule_allow_readonly_caution, frozenset({"file.read"}),
        ),
        PolicyRule(
            "allow-file-read", "Allow safe file reads",
            "Workspace file reads are allowed once path safety passes.",
            80, "allow",
            "safe read-only workspace file access",
            _rule_allow_file_read, frozenset({"file.read"}),
        ),
        PolicyRule(
            "allow-file-write", "Allow safe sandbox writes",
            "Non-sensitive workspace file writes inside the sandbox are allowed.",
            81, "allow",
            "a normal workspace file change inside the sandbox",
            _rule_allow_file_write,
            frozenset({"file.write", "file.delete", "directory.create"}),
        ),
        PolicyRule(
            "allow-metadata-action", "Allow metadata actions",
            "Workflow/task/artifact/message/model bookkeeping actions are allowed.",
            82, "allow",
            "a normal metadata/bookkeeping action",
            _rule_allow_metadata_action,
        ),
        PolicyRule(
            "block-unknown-action", "Block unknown action types",
            "Action types the gateway does not know are blocked by default.",
            99, "block",
            "unknown action types are blocked by default",
            _rule_block_unknown,
        ),
        PolicyRule(
            "default-block", "Block when nothing matched",
            "If no specific policy matched an action, it is blocked — never assumed safe.",
            100, "block",
            "no specific policy matched this action; blocked by default",
            _rule_default_block,
        ),
    ],
    key=lambda rule: rule.priority,
)


def policy_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "action_types": sorted(rule.action_types) if rule.action_types else ["*"],
            "decision": rule.decision,
            "reason": rule.reason,
        }
        for rule in POLICY_RULES
    ]


# ----------------------------------------------------------------- gateway


class EnforcementRefused(SandboxBlocked):
    """An enforcement decision halted execution. Carries the proposal,
    decision, and any HTTP presentation overrides for the router layer."""

    def __init__(
        self,
        reason: str,
        rule: str,
        target: str,
        *,
        http_status: int = 400,
        detail_override: str | None = None,
    ) -> None:
        super().__init__(reason, rule, target)
        self.http_status = http_status
        self.detail_override = detail_override


def _redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _redact(value) if isinstance(value, str) else value
        for key, value in list(data.items())[:20]
    }


def propose_action(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    *,
    actor_type: str = "user",
    action_type: str,
    target: str = "",
    input_summary: str = "",
    sensitivity_level: str = "normal",
    expected_effect: str | None = None,
    requires_approval_hint: bool = False,
    metadata: dict[str, Any] | None = None,
    agent_id: str | None = None,
    workflow_id: str | None = None,
    task_id: str | None = None,
    evaluate_now: bool = True,
) -> tuple[ActionProposal, ActionDecision | None, list[core_models.Event]]:
    proposal = ActionProposal(
        id=f"act-{uuid.uuid4().hex[:10]}",
        workspace_id=workspace.id,
        run_id=workspace.activity_run_id,
        workflow_id=workflow_id,
        task_id=task_id,
        agent_id=agent_id,
        actor_type=actor_type,
        action_type=action_type,
        target=_redact(target)[:512],
        input_summary=_redact(input_summary)[:2000],
        sensitivity_level=sensitivity_level,
        expected_effect=expected_effect[:500] if expected_effect else None,
        requires_approval_hint=requires_approval_hint,
        meta=_redact_dict(metadata or {}),
    )
    session.add(proposal)
    session.flush()
    stored = _emit(
        session,
        workspace,
        "action.proposed",
        {
            "action_id": proposal.id,
            "action_type": action_type,
            "actor_type": actor_type,
            "target": proposal.target[:200],
            **({"agent_id": agent_id} if agent_id else {}),
            **({"workflow_id": workflow_id} if workflow_id else {}),
            **({"task_id": task_id} if task_id else {}),
        },
    )
    decision = None
    if evaluate_now:
        # Evaluate against the RAW input (so the secret rule can fire) while
        # only the redacted form was persisted above.
        decision, more = evaluate_action(
            session, workspace, workspaces_root, proposal,
            raw_target=target, raw_input_summary=input_summary,
        )
        stored += more
    return proposal, decision, stored


def evaluate_action(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    proposal: ActionProposal,
    *,
    raw_target: str | None = None,
    raw_input_summary: str | None = None,
) -> tuple[ActionDecision, list[core_models.Event]]:
    ctx = build_context(
        session,
        workspace,
        workspaces_root,
        actor_type=proposal.actor_type,
        action_type=proposal.action_type,
        target=raw_target if raw_target is not None else proposal.target,
        input_summary=(
            raw_input_summary if raw_input_summary is not None else proposal.input_summary
        ),
        sensitivity_level=proposal.sensitivity_level,
        requires_approval_hint=proposal.requires_approval_hint,
        metadata=proposal.meta or {},
        agent_id=proposal.agent_id,
        task_id=proposal.task_id,
    )
    matched: list[tuple[PolicyRule, dict[str, Any]]] = []
    for rule in POLICY_RULES:
        if rule.id == "default-block" or not rule.enabled or not rule.applies_to(ctx.action_type):
            continue
        evidence = rule.condition(ctx)
        if evidence is not None:
            matched.append((rule, evidence))
    if not matched:
        # The catch-all only steps in when no specific rule matched at all.
        default = next(rule for rule in POLICY_RULES if rule.id == "default-block")
        matched = [(default, default.condition(ctx) or {})]

    # POLICY_RULES is priority-sorted, so the first match decides.
    deciding, deciding_evidence = matched[0]

    stored: list[core_models.Event] = []
    for rule, _evidence in matched[:10]:
        stored += _emit(
            session,
            workspace,
            "policy.rule.matched",
            {
                "action_id": proposal.id,
                "rule_id": rule.id,
                "rule_name": rule.name,
                "rule_decision": rule.decision,
            },
        )

    decision = ActionDecision(
        id=f"dec-{uuid.uuid4().hex[:10]}",
        action_id=proposal.id,
        workspace_id=workspace.id,
        decision=deciding.decision,
        matched_rules=[{"id": r.id, "name": r.name} for r, _ in matched],
        trust_score_before=ctx.agent.trust_score if ctx.agent else None,
        risk_score_before=ctx.agent.risk_score if ctx.agent else None,
        reason=deciding.reason,
        evidence=_redact_dict(deciding_evidence),
    )
    session.add(decision)
    proposal.status = _DECISION_STATUS[deciding.decision]
    session.flush()

    stored += _emit(
        session,
        workspace,
        "policy.evaluated",
        {
            "action_id": proposal.id,
            "decision": deciding.decision,
            "deciding_rule": deciding.id,
            "matched_rule_count": len(matched),
        },
    )
    stored += _emit(
        session,
        workspace,
        DECISION_EVENTS[deciding.decision],
        {
            "action_id": proposal.id,
            "action_type": proposal.action_type,
            "actor_type": proposal.actor_type,
            "target": proposal.target[:200],
            "decision": deciding.decision,
            "rule": deciding.id,
            "reason": deciding.reason,
            "execution_allowed": deciding.decision in EXECUTABLE_DECISIONS,
            **(
                {"trust_before": ctx.agent.trust_score, "risk_before": ctx.agent.risk_score}
                if ctx.agent
                else {}
            ),
        },
    )
    return decision, stored


# ------------------------------------------------------------------ queries


def list_proposals(session: Session, workspace_id: str, limit: int = 50) -> list[ActionProposal]:
    return list(
        session.execute(
            select(ActionProposal)
            .where(ActionProposal.workspace_id == workspace_id)
            .order_by(ActionProposal.created_at.desc(), ActionProposal.id.desc())
            .limit(max(1, min(limit, 200)))
        ).scalars()
    )


def get_proposal(session: Session, workspace_id: str, action_id: str) -> ActionProposal | None:
    proposal = session.get(ActionProposal, action_id)
    if proposal is None or proposal.workspace_id != workspace_id:
        return None
    return proposal


def get_decision(session: Session, action_id: str) -> ActionDecision | None:
    return session.execute(
        select(ActionDecision).where(ActionDecision.action_id == action_id)
    ).scalar_one_or_none()


def list_decisions(session: Session, workspace_id: str, limit: int = 50) -> list[ActionDecision]:
    return list(
        session.execute(
            select(ActionDecision)
            .where(ActionDecision.workspace_id == workspace_id)
            .order_by(ActionDecision.created_at.desc(), ActionDecision.id.desc())
            .limit(max(1, min(limit, 200)))
        ).scalars()
    )


# ------------------------------------------------- integrated guard helpers


def file_legacy_audit(
    session: Session, workspace: Workspace, operation: str, path: str
) -> Callable[[ActionDecision], list[core_models.Event]]:
    """v1.2 stream parity: an enforcement block on a file op also emits the
    sandbox.file.blocked audit event the file runtime would have emitted."""

    def audit(decision: ActionDecision) -> list[core_models.Event]:
        if decision.decision not in ("block", "retry_with_constraints"):
            return []
        evidence = decision.evidence or {}
        rule = evidence.get("legacy_rule") or (
            decision.matched_rules[0]["id"] if decision.matched_rules else "policy"
        )
        return _emit(
            session,
            workspace,
            "sandbox.file.blocked",
            {
                "operation": operation,
                "attempted_path": _redact(path)[:200],
                "reason": evidence.get("legacy_reason", decision.reason),
                "rule": rule,
            },
        )

    return audit


def command_legacy_audit(
    session: Session, workspace: Workspace, command: str, args: list[str]
) -> Callable[[ActionDecision], list[core_models.Event]]:
    """v1.3 stream parity: an enforcement block on a command also emits the
    sandbox.command.proposed/blocked pair the command runner would have."""
    display = _redact(shlex.join([command, *args]))

    def audit(decision: ActionDecision) -> list[core_models.Event]:
        if decision.decision not in ("block", "retry_with_constraints"):
            return []
        evidence = decision.evidence or {}
        rule = evidence.get("legacy_rule") or (
            decision.matched_rules[0]["id"] if decision.matched_rules else "policy"
        )
        events = _emit(
            session,
            workspace,
            "sandbox.command.proposed",
            {"command": display[:200], "argv": [_redact(a) for a in [command, *args]][:20]},
        )
        events += _emit(
            session,
            workspace,
            "sandbox.command.blocked",
            {
                "command": display[:200],
                "reason": evidence.get("legacy_reason", decision.reason),
                "rule": rule,
            },
        )
        return events

    return audit


def _refuse(
    proposal: ActionProposal,
    decision: ActionDecision,
    stored: list[core_models.Event],
) -> EnforcementRefused:
    evidence = decision.evidence or {}
    legacy_rule = evidence.get("legacy_rule")
    legacy_reason = evidence.get("legacy_reason", decision.reason)
    if decision.decision == "block" and legacy_rule:
        exc = EnforcementRefused(legacy_reason, legacy_rule, proposal.target)
    elif decision.decision == "block":
        exc = EnforcementRefused(decision.reason, decision.matched_rules[0]["id"], proposal.target)
    elif decision.decision == "retry_with_constraints" and legacy_rule:
        # Presented like the v1.3 block (the command still must not run now);
        # the enforcement stream carries the retry nuance.
        exc = EnforcementRefused(legacy_reason, legacy_rule, proposal.target)
    else:
        rule_id = decision.matched_rules[0]["id"] if decision.matched_rules else "policy"
        label = {
            "require_human_approval": "approval required",
            "reroute_to_verifier": "rerouted to verifier",
            "downgrade_permissions": "permissions downgraded",
            "quarantine_agent": "quarantine triggered",
        }.get(decision.decision, "refused")
        exc = EnforcementRefused(
            decision.reason,
            rule_id,
            proposal.target,
            http_status=403,
            detail_override=(
                f"{label} ({rule_id}): {decision.reason} — "
                "approval resolution arrives in v1.6"
                if decision.decision == "require_human_approval"
                else f"{label} ({rule_id}): {decision.reason}"
            ),
        )
    exc.events = stored
    return exc


def guarded_execute(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    *,
    action_type: str,
    target: str,
    metadata: dict[str, Any] | None = None,
    workflow_id: str | None = None,
    task_id: str | None = None,
    legacy_audit: Callable[[ActionDecision], list[core_models.Event]] | None = None,
    execute: Callable[[], tuple[Any, list[core_models.Event]]],
) -> tuple[Any, list[core_models.Event]]:
    """Propose → evaluate → (if executable) run `execute` between
    action.started / action.completed. On refusal, optionally emit the
    legacy v1.2/v1.3 audit events for stream parity, then raise."""
    proposal, decision, stored = propose_action(
        session,
        workspace,
        workspaces_root,
        actor_type="user",
        action_type=action_type,
        target=target,
        metadata=metadata,
        workflow_id=workflow_id,
        task_id=task_id,
    )
    assert decision is not None
    if decision.decision not in EXECUTABLE_DECISIONS:
        if legacy_audit is not None:
            stored += legacy_audit(decision)
        raise _refuse(proposal, decision, stored)

    stored += _emit(
        session,
        workspace,
        "action.started",
        {"action_id": proposal.id, "action_type": action_type, "target": proposal.target[:200]},
    )
    try:
        payload, more = execute()
    except SandboxBlocked as inner:
        # Defense in depth tripped after an enforcement allow — record it.
        proposal.status = "failed"
        inner.events = (
            stored
            + inner.events
            + _emit(
                session,
                workspace,
                "action.failed",
                {"action_id": proposal.id, "action_type": action_type, "reason": inner.reason},
            )
        )
        raise
    stored += more
    proposal.status = "completed"
    stored += _emit(
        session,
        workspace,
        "action.completed",
        {"action_id": proposal.id, "action_type": action_type, "target": proposal.target[:200]},
    )
    return payload, stored
