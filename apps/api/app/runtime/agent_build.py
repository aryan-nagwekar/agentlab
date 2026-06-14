"""Live Agent Execution — single governed step (v3.0).

The loop *body*: take a goal, make ONE real model call through the v0.7 gateway
(the workspace agent's own provider/model — e.g. local ollama/llama3.2), parse
a strict JSON action manifest, and route **every** proposed file write through
the v1.5 enforcement gateway before it touches the sandbox.

Nothing here bypasses a single existing control:
- the model call goes through the gateway and emits `model.*` telemetry;
- each file write goes through `enforcement.guarded_execute` attributed to the
  agent, so v1.2 path safety, v1.5 policy, v1.6 approval, and v1.7 quarantine
  all apply exactly as for a manual write;
- a malformed/empty model response writes **nothing** (clean failure);
- sensitive paths halt for human approval; unsafe paths are blocked.

This is a single pass — no autonomous iteration and no command execution yet
(those are v3.1 / v3.2). The safe files it produces are renderable through the
v2.1 website preview.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from .. import models as core_models
from ..collector import process_events
from ..model_gateway import ModelRequest, ModelResponse, build_model_events
from . import enforcement, sandbox
from .commands import _redact
from .models import Workspace, WorkspaceAgent
from .sandbox import SandboxBlocked
from .service import _emit

MAX_FILES = 16
MAX_FILE_CHARS = 100_000

BUILD_SYSTEM_PROMPT = (
    "You are a build agent operating inside a sandboxed, governed runtime. "
    "Given a goal, produce ONE small, self-contained static web page. "
    "Respond with ONLY a JSON object, no markdown, no commentary, of the form: "
    '{"summary": "<one sentence>", "files": [{"path": "index.html", "content": "..."}]}. '
    "Strong rules: output exactly one file, index.html, a complete valid HTML "
    "document with ALL styling inline in a <style> tag. "
    "Do NOT reference external or separate image files — represent products with "
    "emoji or CSS-colored blocks instead. "
    "Every JSON key must be double-quoted (write {\"path\": ...}, never {path: ...}). "
    "Paths must be relative (never start with / or ..); no external CDNs, no network "
    "calls, no secrets, no API keys. Keep it compact."
)


def build_prompt(goal: str) -> str:
    return (
        f"Goal: {goal.strip()}\n\n"
        "Return the JSON object now with a single index.html file. It must be a "
        "complete, valid, self-contained HTML document with inline CSS and no "
        "external image files. Keep it compact."
    )


# llama-class local models routinely drop the opening quote on a JSON key right
# after `{` or `,` (e.g. `{path": ...}`). Re-add it for known keys — this only
# touches malformed keys; correctly-quoted `"path"` is preceded by `"`, not `{`/`,`.
_KEY_REPAIR = re.compile(r'([{,]\s*)(path|content|type|summary|files)"\s*:')


def _repair_json(text: str) -> str:
    return _KEY_REPAIR.sub(r'\1"\2":', text)


def parse_manifest(text: str) -> tuple[str, list[dict[str, str]]] | None:
    """Extract {summary, files[]} from a model response. Tolerant of markdown
    fences and surrounding prose; returns None if no valid manifest is found."""
    if not text:
        return None
    candidate = text.strip()
    # Strip ```json … ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.+?)```", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
    # Narrow to the outermost {...} block if there is surrounding prose. If
    # there is no JSON object at all, fall straight through to HTML salvage.
    if not candidate.startswith("{"):
        brace = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = brace.group(0) if brace else ""
    # strict=False tolerates literal newlines/tabs inside string values; the
    # repair pass fixes the common missing-opening-quote-on-a-key malformation.
    data = None
    for attempt in (candidate, _repair_json(candidate)) if candidate else ():
        try:
            data = json.loads(attempt, strict=False)
            break
        except (json.JSONDecodeError, ValueError):
            continue
    if isinstance(data, dict) and isinstance(data.get("files"), list):
        files: list[dict[str, str]] = []
        for entry in data["files"][:MAX_FILES]:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path", "")).strip()
            content = entry.get("content", "")
            if not path or not isinstance(content, str):
                continue
            files.append({"path": path, "content": content[:MAX_FILE_CHARS]})
        if files:
            summary = str(data.get("summary", "")).strip()[:300] or "Generated files."
            return summary, files

    # Last-resort salvage: small models often emit good HTML inside a broken
    # JSON wrapper. If we can recover an HTML document, write it as a single
    # index.html so a previewable page still results.
    html = _salvage_html(text)
    if html:
        return "Recovered a single-page site from the model's HTML output", [
            {"path": "index.html", "content": html[:MAX_FILE_CHARS]}
        ]
    return None


# HTML the model emitted even when its JSON wrapper is malformed.
_HTML_OPENERS = ("<!doctype", "<html", "<head", "<body", "<style", "<main",
                 "<section", "<header", "<h1", "<div")


def _salvage_html(text: str) -> str | None:
    lowered = text.lower()
    starts = [i for i in (lowered.find(t) for t in _HTML_OPENERS) if i != -1]
    if not starts:
        return None
    html = text[min(starts):]
    # Trim trailing JSON wrapper junk after the last real close tag.
    low = html.lower()
    for closer in ("</html>", "</body>"):
        idx = low.rfind(closer)
        if idx != -1:
            html = html[: idx + len(closer)]
            break
    else:
        html = re.sub(r'["\']?\s*[}\]]*\s*$', "", html)
    # Undo JSON string escapes the model may have left behind.
    for a, b in (('\\"', '"'), ("\\n", "\n"), ("\\t", "\t"), ("\\/", "/"), ("\\\\", "\\")):
        html = html.replace(a, b)
    if "<html" not in html.lower():
        html = (
            '<!doctype html><html><head><meta charset="utf-8">'
            "<title>Preview</title></head><body>\n" + html + "\n</body></html>"
        )
    return html.strip()


def build_model_request(
    workspace: Workspace, agent: WorkspaceAgent, goal: str
) -> ModelRequest:
    return ModelRequest(
        provider=agent.model_provider,
        model_name=_bare_model(agent.model_name),
        prompt=build_prompt(goal),
        system_prompt=BUILD_SYSTEM_PROMPT,
        agent_id=agent.id,
        run_id=workspace.activity_run_id,
        project_id=workspace.project_id,
        temperature=0.2,
        max_tokens=4000,
        metadata={"source": "agent_build", "workspace_id": workspace.id},
    )


def _bare_model(model_name: str) -> str:
    # Agents may store "ollama:llama3.2"; the gateway wants the bare model id.
    return model_name.split(":", 1)[1] if ":" in model_name else model_name


def apply_build(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    agent: WorkspaceAgent,
    response: ModelResponse,
) -> tuple[dict[str, Any], list[core_models.Event]]:
    """Emit model telemetry, parse the manifest, and route every proposed file
    write through enforcement. Commits via the caller. Never raises on a
    blocked/halted file — it records the outcome and continues."""
    request_run = workspace.activity_run_id
    stored: list[core_models.Event] = []

    # Model telemetry into the activity run (cost/replay/topology pick it up).
    # The model OUTPUT is generated code — redact it before it enters the event
    # preview so a secret the model emitted never lands in the activity stream.
    telemetry = build_model_events(
        ModelRequest(
            provider=response.provider,
            model_name=response.model_name,
            prompt=BUILD_SYSTEM_PROMPT,
            agent_id=agent.id,
            run_id=request_run,
            project_id=workspace.project_id,
        ),
        replace(response, output_text=_redact(response.output_text)),
    )
    model_rows, _ = process_events(session, telemetry)
    stored += model_rows

    stored += _emit(
        session, workspace, "agent.build.started",
        {"agent_id": agent.id, "model": response.model_name, "provider": response.provider},
    )

    if response.status != "completed":
        stored += _emit(
            session, workspace, "agent.build.failed",
            {"agent_id": agent.id, "reason": (response.error_message or "model call failed")[:300]},
        )
        return _result(agent, response, "failed", [], "the model call failed"), stored

    parsed = parse_manifest(response.output_text)
    if parsed is None:
        stored += _emit(
            session, workspace, "agent.build.failed",
            {"agent_id": agent.id, "reason": "model did not return a valid file manifest"},
        )
        return (
            _result(agent, response, "failed", [],
                    "the model did not return a valid JSON file manifest — nothing was written"),
            stored,
        )

    summary, files = parsed
    outcomes: list[dict[str, str]] = []
    for f in files:
        path, content = f["path"], f["content"]
        try:
            _payload, events = enforcement.guarded_execute(
                session,
                workspace,
                workspaces_root,
                action_type="file.write",
                target=path,
                actor_type="agent",
                agent_id=agent.id,
                legacy_audit=enforcement.file_legacy_audit(session, workspace, "write", path),
                approval_payload={"path": path, "content": content},
                execute=lambda p=path, c=content: sandbox.write_file(
                    session, workspace, workspaces_root, p, c
                ),
            )
            stored += events
            outcomes.append({"path": path, "status": "written"})
        except SandboxBlocked as refused:
            stored += list(refused.events)
            halted = getattr(refused, "http_status", 400) == 403
            outcomes.append(
                {
                    "path": path,
                    "status": "halted_for_approval" if halted else "blocked",
                    "reason": refused.reason,
                }
            )

    counts = {
        "written": sum(1 for o in outcomes if o["status"] == "written"),
        "halted_for_approval": sum(1 for o in outcomes if o["status"] == "halted_for_approval"),
        "blocked": sum(1 for o in outcomes if o["status"] == "blocked"),
    }
    stored += _emit(
        session, workspace, "agent.build.completed",
        {"agent_id": agent.id, "summary": summary[:300], "file_count": len(outcomes), **counts},
    )
    return _result(agent, response, "completed", outcomes, summary), stored


def _result(
    agent: WorkspaceAgent,
    response: ModelResponse,
    status: str,
    outcomes: list[dict[str, str]],
    summary: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "agent_id": agent.id,
        "agent_name": agent.name,
        "provider": response.provider,
        "model": response.model_name,
        "summary": summary,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "latency_ms": response.latency_ms,
        "files": outcomes,
        "written": sum(1 for o in outcomes if o["status"] == "written"),
        "halted_for_approval": sum(1 for o in outcomes if o["status"] == "halted_for_approval"),
        "blocked": sum(1 for o in outcomes if o["status"] == "blocked"),
    }
