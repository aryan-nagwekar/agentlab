"""Deterministic Validators (v1.8).

Evidence-based checks that let AgentLab stop blindly trusting agent outputs.
Every validator is a pure, deterministic function — no LLM judgment, no web
browsing, no live external fetch. They inspect workspace files, already
recorded v1.3 command results, and structured claim / data-flow / business
metadata, and produce a ValidatorResult with **bounded, redacted** evidence
plus risk/trust deltas.

Boundaries: validators never run arbitrary project code (Python syntax uses
``ast.parse``, JSON uses ``json.loads``); the command-result validator
*consumes* existing command events rather than re-running anything; evidence
snippets are length-capped and secret-redacted, and no host filesystem path
ever leaves the server. risk/trust deltas are scoring SIGNALS in the result
and events — the deterministic v0.5 trust/risk fold is not modified.
"""
from __future__ import annotations

import ast
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as core_models
from .commands import _redact
from .models import RuntimeTask, ValidatorResult, Workspace
from .sandbox import (
    MAX_READ_BYTES,
    PathViolation,
    check_path,
    sandbox_root,
)
from .service import _emit

EVIDENCE_SNIPPET_CHARS = 200
MAX_EVIDENCE_ITEMS = 10

# Broader than the command-output redactor: also private-key headers and
# .env-style secret assignments. Used only to *detect* exposure; matched text
# is always redacted before it is stored.
_SECRET_DETECTORS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(r"(?<![A-Za-z0-9])(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}|xox[bap]-[A-Za-z0-9-]{10,})")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("env_secret", re.compile(r"(?im)^\s*[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|API)[A-Z0-9_]*\s*=\s*\S{6,}")),
]

# Default evidence fields a supported product/supplier claim must include.
DEFAULT_REQUIRED_FIELDS = ("price", "moq", "shipping", "supplier_name")

# Tokens that mark a change/claim as business-critical.
_BUSINESS_TOKENS: dict[str, str] = {
    "payment": "payment code/flow touched",
    "billing": "billing flow touched",
    "checkout": "checkout flow touched",
    "stripe": "payment provider touched",
    "auth": "authentication touched",
    "login": "authentication touched",
    "password": "credential handling touched",
    "deploy": "deployment touched",
    "migration": "database migration touched",
    "customer": "customer data touched",
    "pii": "personal data touched",
}


def _redact_snippet(text: str) -> str:
    return _redact(text)[:EVIDENCE_SNIPPET_CHARS]


@dataclass
class Outcome:
    """A validator's deterministic verdict (pre-persistence)."""

    passed: bool
    target_type: str
    target_ref: str
    confidence: float = 1.0
    evidence: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    suggested_action: str | None = None
    risk_delta: float = 0.0
    trust_delta: float = 0.0
    explanation: str = ""
    # Extra signal events beyond validation.passed/failed: (event_type, payload).
    signals: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


# ------------------------------------------------------------- file helpers


def _read_workspace_file(root, target_ref: str) -> str:
    """Read a workspace file for validation with path safety + size cap.
    Raises ValueError (→ validator failure) for unsafe/oversize/binary."""
    try:
        real = check_path(root, target_ref)
    except PathViolation as exc:
        raise ValueError(f"unsafe path: {exc.reason}")
    if not real.is_file():
        raise ValueError("file not found in the workspace sandbox")
    if real.lstat().st_size > MAX_READ_BYTES:
        raise ValueError(f"file exceeds the {MAX_READ_BYTES // 1024} KB validation limit")
    try:
        return real.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("binary files cannot be validated as text")


# --------------------------------------------------------------- validators


def validate_secret_exposure(root, target_ref: str, payload: dict[str, Any]) -> Outcome:
    """Scan a workspace file (or inline `content`) for secret-like patterns."""
    if payload.get("content") is not None:
        text, target_type, ref = str(payload["content"]), "inline", target_ref or "inline"
    else:
        text, target_type, ref = _read_workspace_file(root, target_ref), "file", target_ref

    findings: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _SECRET_DETECTORS:
            if pattern.search(line):
                findings.append(
                    {"line": line_no, "kind": kind, "snippet": _redact_snippet(line.strip())}
                )
                break
        if len(findings) >= MAX_EVIDENCE_ITEMS:
            break

    if findings:
        return Outcome(
            passed=False,
            target_type=target_type,
            target_ref=ref,
            evidence={"findings": findings, "match_count": len(findings)},
            failures=[f"line {f['line']}: {f['kind']} secret-like value" for f in findings],
            suggested_action="remove the secret and load it from env/secret storage instead",
            risk_delta=0.3,
            trust_delta=-0.2,
            explanation=f"Found {len(findings)} secret-like value(s); the exposed text is redacted.",
            signals=[
                (
                    "secret.exposure.detected",
                    {"target_ref": ref, "match_count": len(findings)},
                )
            ],
        )
    return Outcome(
        passed=True,
        target_type=target_type,
        target_ref=ref,
        evidence={"match_count": 0},
        explanation="No secret-like patterns detected.",
    )


def validate_code_syntax(root, target_ref: str, payload: dict[str, Any]) -> Outcome:
    """ast.parse for .py, json.loads for .json/package.json. No code runs."""
    text = (
        str(payload["content"])
        if payload.get("content") is not None
        else _read_workspace_file(root, target_ref)
    )
    name = target_ref.rsplit("/", 1)[-1].lower()

    if name.endswith(".py"):
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return Outcome(
                passed=False, target_type="file", target_ref=target_ref,
                evidence={"language": "python", "line": exc.lineno, "offset": exc.offset},
                failures=[f"Python syntax error at line {exc.lineno}: {exc.msg}"],
                suggested_action="fix the Python syntax error before using this file",
                risk_delta=0.1, trust_delta=-0.1,
                explanation=f"Python syntax error at line {exc.lineno}: {exc.msg}.",
            )
        return Outcome(True, "file", target_ref, evidence={"language": "python"},
                       explanation="Python syntax is valid.")

    if name.endswith(".json"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return Outcome(
                passed=False, target_type="file", target_ref=target_ref,
                evidence={"language": "json", "line": exc.lineno, "column": exc.colno},
                failures=[f"JSON parse error at line {exc.lineno}: {exc.msg}"],
                suggested_action="fix the malformed JSON",
                risk_delta=0.1, trust_delta=-0.1,
                explanation=f"JSON is invalid at line {exc.lineno}: {exc.msg}.",
            )
        failures: list[str] = []
        if name == "package.json" and isinstance(parsed, dict):
            for key in ("name", "version"):
                if key not in parsed:
                    failures.append(f"package.json is missing '{key}'")
        if failures:
            return Outcome(
                passed=False, target_type="file", target_ref=target_ref,
                evidence={"language": "json"}, failures=failures,
                suggested_action="add the required package.json fields",
                risk_delta=0.05,
                explanation="; ".join(failures) + ".",
            )
        return Outcome(True, "file", target_ref, evidence={"language": "json"},
                       explanation="JSON parses successfully.")

    return Outcome(
        passed=True, target_type="file", target_ref=target_ref, confidence=0.0,
        evidence={"skipped": True},
        explanation="No deterministic syntax validator for this file type; skipped.",
    )


_ERROR_PATTERNS = re.compile(
    r"(?i)\b(error|exception|traceback|failed|cannot find|not found|undefined|syntaxerror)\b"
)


def validate_command_result(
    session: Session, workspace: Workspace, target_ref: str, payload: dict[str, Any]
) -> Outcome:
    """Validate the most recent recorded command result in a run. Consumes
    existing v1.3 command events — never re-runs anything."""
    run_id = target_ref or workspace.activity_run_id
    rows = (
        session.execute(
            select(core_models.Event)
            .where(
                core_models.Event.run_id == run_id,
                core_models.Event.event_type.in_(
                    ("sandbox.command.completed", "sandbox.command.failed", "sandbox.command.timed_out")
                ),
            )
            .order_by(core_models.Event.timestamp.desc(), core_models.Event.id.desc())
            .limit(1)
        )
        .scalars()
        .all()
    )
    if not rows:
        return Outcome(
            passed=False, target_type="command_run", target_ref=run_id, confidence=0.0,
            failures=["no recorded command result found in this run"],
            suggested_action="run a command first, then validate its result",
            explanation="No command result is available to validate.",
        )

    event = rows[0]
    p = event.payload or {}
    command = str(p.get("command", ""))[:200]
    exit_code = p.get("exit_code")
    stderr_summary = _redact_snippet(str(p.get("stderr_summary", "")))
    base_evidence = {"command": command, "exit_code": exit_code, "kind": event.event_type}

    if event.event_type == "sandbox.command.completed" and exit_code == 0:
        if _ERROR_PATTERNS.search(stderr_summary):
            return Outcome(
                passed=False, target_type="command_run", target_ref=run_id, confidence=0.6,
                evidence={**base_evidence, "stderr_summary": stderr_summary},
                failures=["command exited 0 but stderr contains error-like output"],
                suggested_action="inspect the command's stderr before trusting the result",
                risk_delta=0.05,
                explanation="Command succeeded (exit 0) but its stderr looks error-like.",
                signals=[("runtime.error.detected", {"target_ref": run_id, "command": command})],
            )
        return Outcome(
            passed=True, target_type="command_run", target_ref=run_id,
            evidence=base_evidence, explanation=f"Command succeeded: `{command}` (exit 0).",
        )

    return Outcome(
        passed=False, target_type="command_run", target_ref=run_id,
        evidence={**base_evidence, "stderr_summary": stderr_summary},
        failures=[f"command did not succeed ({event.event_type}, exit {exit_code})"],
        suggested_action="fix the failing command and re-run before continuing",
        risk_delta=0.15, trust_delta=-0.1,
        explanation=f"Command `{command}` {event.event_type.rsplit('.', 1)[-1]} (exit {exit_code}).",
        signals=[("runtime.error.detected", {"target_ref": run_id, "command": command, "exit_code": exit_code})],
    )


def validate_research_claim(target_ref: str, payload: dict[str, Any]) -> Outcome:
    """Validate a structured claim against PROVIDED evidence only. No web."""
    claim = str(payload.get("claim", "")).strip()
    source_url = str(payload.get("source_url", "")).strip()
    evidence_text = str(payload.get("evidence_text", ""))
    required = [str(f).lower() for f in payload.get("required_fields", DEFAULT_REQUIRED_FIELDS)]
    ref = target_ref or (claim[:80] or "claim")

    failures: list[str] = []
    if not source_url:
        failures.append("no source_url provided for the claim")
    haystack = f"{evidence_text} {json.dumps(payload.get('fields', {}))}".lower()
    missing = [f for f in required if f.replace("_", " ") not in haystack and f not in haystack]
    if missing:
        failures.append(f"evidence missing required field(s): {', '.join(missing)}")
    # Deterministic support check: the claim's significant tokens must appear
    # in the supplied evidence text.
    claim_tokens = [t for t in re.findall(r"[a-z0-9]+", claim.lower()) if len(t) > 3]
    if claim and evidence_text:
        unsupported = [t for t in claim_tokens if t not in evidence_text.lower()]
        if claim_tokens and len(unsupported) > len(claim_tokens) // 2:
            failures.append("claim text is not supported by the provided evidence")

    if failures:
        return Outcome(
            passed=False, target_type="claim", target_ref=ref,
            evidence={"source_url_present": bool(source_url), "missing_fields": missing},
            failures=failures,
            suggested_action="reject the claim or gather complete cited evidence before saving it",
            risk_delta=0.2, trust_delta=-0.15,
            explanation="The claim is not supported by complete, cited evidence.",
            signals=[("claim.rejected", {"target_ref": ref, "failure_count": len(failures)})],
        )
    return Outcome(
        passed=True, target_type="claim", target_ref=ref,
        evidence={"source_url_present": True, "fields_present": required},
        trust_delta=0.05,
        explanation="The claim is supported by the provided cited evidence.",
        signals=[("claim.verified", {"target_ref": ref})],
    )


def _normalize_fields(side: Any) -> tuple[str, dict[str, Any]]:
    """Accept {label, fields:{...}} or a bare {field: type} map."""
    if isinstance(side, dict) and "fields" in side and isinstance(side["fields"], dict):
        return str(side.get("label", "")), dict(side["fields"])
    if isinstance(side, dict):
        return "", {k: v for k, v in side.items() if k != "label"}
    return "", {}


def validate_data_flow(target_ref: str, payload: dict[str, Any]) -> Outcome:
    """Compare a consumer's expected fields against a producer's actual
    fields (structured metadata only) and explain any mismatch."""
    consumer_label, expected = _normalize_fields(
        payload.get("consumer") or payload.get("expected") or payload.get("frontend") or {}
    )
    producer_label, actual = _normalize_fields(
        payload.get("producer") or payload.get("actual") or payload.get("backend") or {}
    )
    consumer_label = consumer_label or payload.get("consumer_label", "the consumer")
    producer_label = producer_label or payload.get("producer_label", "the producer")
    ref = target_ref or f"{consumer_label}→{producer_label}"

    if not expected:
        return Outcome(
            passed=False, target_type="data_flow", target_ref=ref, confidence=0.0,
            failures=["no expected fields supplied to compare"],
            explanation="Nothing to validate — supply the consumer's expected fields.",
        )

    missing = [f for f in expected if f not in actual]
    type_mismatch = [
        f for f in expected
        if f in actual and str(expected[f]) != str(actual[f])
    ]
    failures: list[str] = []
    explanation_parts: list[str] = []
    for f in missing:
        failures.append(f"{producer_label} does not provide '{f}'")
        explanation_parts.append(
            f"{consumer_label} expects `{f}`, but {producer_label} does not provide it"
        )
    for f in type_mismatch:
        failures.append(f"'{f}' type mismatch: expected {expected[f]}, got {actual[f]}")
        explanation_parts.append(
            f"{consumer_label} expects `{f}` as {expected[f]}, but {producer_label} provides {actual[f]}"
        )

    if failures:
        return Outcome(
            passed=False, target_type="data_flow", target_ref=ref,
            evidence={"missing": missing, "type_mismatch": type_mismatch,
                      "expected_fields": list(expected), "actual_fields": list(actual)},
            failures=failures,
            suggested_action="align the producer and consumer field contracts",
            risk_delta=0.15, trust_delta=-0.1,
            explanation=". ".join(explanation_parts) + ".",
            signals=[("schema.mismatch.detected", {"target_ref": ref, "missing": missing[:10]}),
                     ("app.error.translated", {"target_ref": ref, "explanation": (". ".join(explanation_parts))[:300]})],
        )
    return Outcome(
        passed=True, target_type="data_flow", target_ref=ref,
        evidence={"matched_fields": list(expected)},
        explanation=f"{consumer_label} and {producer_label} field contracts match.",
    )


def validate_business_risk(target_ref: str, payload: dict[str, Any]) -> Outcome:
    """Flag business-critical changes/claims from structured metadata."""
    haystack = " ".join(
        str(v) for v in (
            payload.get("target", ""),
            payload.get("description", ""),
            target_ref,
            " ".join(str(t) for t in payload.get("touches", [])),
        )
    ).lower()
    hits = sorted({label for token, label in _BUSINESS_TOKENS.items() if token in haystack})
    unverified = bool(payload.get("unverified")) or "unverified" in haystack
    if unverified:
        hits.append("uses unverified product/supplier data")

    if hits:
        requires_approval = any(
            k in haystack for k in ("payment", "auth", "deploy", "migration", "customer", "pii")
        )
        return Outcome(
            passed=False, target_type="change", target_ref=target_ref or "change",
            evidence={"flags": hits, "requires_approval": requires_approval,
                      "requires_validation": True},
            failures=hits,
            suggested_action=(
                "require human approval before this change proceeds"
                if requires_approval
                else "require validation/verification before this data is used"
            ),
            risk_delta=0.25 if requires_approval else 0.15,
            trust_delta=-0.1,
            explanation="Business-critical: " + "; ".join(hits) + ".",
            signals=[("risky.file_change.detected",
                      {"target_ref": target_ref or "change", "flags": hits[:10],
                       "requires_approval": requires_approval})],
        )
    return Outcome(
        passed=True, target_type="change", target_ref=target_ref or "change",
        evidence={"flags": []},
        explanation="No business-critical risk flags detected.",
    )


# ------------------------------------------------------------- registry/run


def validator_registry() -> list[dict[str, Any]]:
    return [
        {"type": "secret_exposure", "description": "Scan a workspace file or inline content for secret-like patterns (redacted evidence only).", "target_type": "file", "inputs": ["target_ref or content"]},
        {"type": "code_syntax", "description": "Validate .py (ast.parse) and .json/package.json (json.loads) syntax. No code runs.", "target_type": "file", "inputs": ["target_ref or content"]},
        {"type": "command_result", "description": "Validate the most recent recorded v1.3 command result in a run (exit 0 = pass).", "target_type": "command_run", "inputs": ["target_ref=run_id (optional)"]},
        {"type": "research_claim", "description": "Validate a structured claim against PROVIDED cited evidence only. No web browsing.", "target_type": "claim", "inputs": ["claim", "source_url", "evidence_text", "required_fields"]},
        {"type": "data_flow", "description": "Compare a consumer's expected fields vs a producer's actual fields and explain mismatches.", "target_type": "data_flow", "inputs": ["consumer/expected", "producer/actual"]},
        {"type": "business_risk", "description": "Flag business-critical changes (payment/auth/deploy/customer-data/unverified).", "target_type": "change", "inputs": ["target", "description", "touches", "unverified"]},
    ]


def run_validator(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    *,
    validator_type: str,
    target_ref: str = "",
    payload: dict[str, Any] | None = None,
    workflow_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
) -> tuple[ValidatorResult, list[core_models.Event]]:
    payload = payload or {}
    if validator_type not in {v["type"] for v in validator_registry()}:
        from .sandbox import SandboxError

        raise SandboxError(f"unknown validator {validator_type!r}")

    stored = _emit(
        session, workspace, "validator.started",
        {"validator_type": validator_type, "target_ref": target_ref[:200]},
    )

    root = sandbox_root(workspaces_root, workspace.id)
    try:
        if validator_type == "secret_exposure":
            outcome = validate_secret_exposure(root, target_ref, payload)
        elif validator_type == "code_syntax":
            outcome = validate_code_syntax(root, target_ref, payload)
        elif validator_type == "command_result":
            outcome = validate_command_result(session, workspace, target_ref, payload)
        elif validator_type == "research_claim":
            outcome = validate_research_claim(target_ref, payload)
        elif validator_type == "data_flow":
            outcome = validate_data_flow(target_ref, payload)
        else:  # business_risk
            outcome = validate_business_risk(target_ref, payload)
    except ValueError as exc:
        # The validator could not run (unsafe/missing/binary target).
        stored += _emit(
            session, workspace, "validator.failed",
            {"validator_type": validator_type, "target_ref": target_ref[:200],
             "error": str(exc)[:200]},
        )
        from .sandbox import SandboxError

        exc_out = SandboxError(f"validator could not run: {exc}", status_code=400)
        exc_out.events = stored  # type: ignore[attr-defined]
        raise exc_out

    result = ValidatorResult(
        id=f"val-{uuid.uuid4().hex[:10]}",
        workspace_id=workspace.id,
        run_id=workspace.activity_run_id,
        workflow_id=workflow_id,
        task_id=task_id,
        agent_id=agent_id,
        validator_type=validator_type,
        target_type=outcome.target_type,
        target_ref=outcome.target_ref[:512],
        passed=outcome.passed,
        confidence=outcome.confidence,
        evidence=outcome.evidence,
        failures=outcome.failures[:MAX_EVIDENCE_ITEMS],
        suggested_action=outcome.suggested_action,
        risk_delta=outcome.risk_delta,
        trust_delta=outcome.trust_delta,
        meta={"explanation": outcome.explanation},
    )
    session.add(result)
    session.flush()

    base = {
        "validator_result_id": result.id,
        "validator_type": validator_type,
        "target_type": outcome.target_type,
        "target_ref": outcome.target_ref[:200],
        "passed": outcome.passed,
        "confidence": outcome.confidence,
        "failure_count": len(outcome.failures),
        "suggested_action": outcome.suggested_action,
        "risk_delta": outcome.risk_delta,
        "trust_delta": outcome.trust_delta,
        "explanation": outcome.explanation[:300],
    }
    for event_type, extra in outcome.signals:
        stored += _emit(session, workspace, event_type, {**base, **extra})
    stored += _emit(
        session, workspace,
        "validation.passed" if outcome.passed else "validation.failed", base,
    )
    stored += _emit(session, workspace, "validator.completed", base)

    # Task linkage (metadata only — no scheduler status change here).
    if task_id:
        task = session.get(RuntimeTask, task_id)
        if task is not None and task.workspace_id == workspace.id:
            task.meta = {
                **(task.meta or {}),
                "validation_status": "passed" if outcome.passed else "failed",
                "validation_result_id": result.id,
            }

    return result, stored


# ------------------------------------------------------------------ queries


def list_results(session: Session, workspace_id: str, limit: int = 50) -> list[ValidatorResult]:
    return list(
        session.execute(
            select(ValidatorResult)
            .where(ValidatorResult.workspace_id == workspace_id)
            .order_by(ValidatorResult.created_at.desc(), ValidatorResult.id.desc())
            .limit(max(1, min(limit, 200)))
        ).scalars()
    )


def get_result(session: Session, workspace_id: str, result_id: str) -> ValidatorResult | None:
    result = session.get(ValidatorResult, result_id)
    if result is None or result.workspace_id != workspace_id:
        return None
    return result
