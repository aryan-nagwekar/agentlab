"""Workspace templates (v3.3) — one-click *real* workspace setup.

Instantiating a workspace template materializes a real workspace: a project
area + a goal + an initialized sandbox + a team of agents (from the v1.1 agent
templates, on the local default model). Nothing is canned or pre-written —
unlike `demo_bottle_shop.seed`, this writes **no files**. The user then runs a
real governed build (agent-build / agent-run) and every action goes through the
enforcement gateway as usual.

Templates are *data*, not an engine: `instantiate` only orchestrates existing
services (`create_workspace`, `init_sandbox`, `create_agent_from_template`).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .. import models as core_models
from . import agent_templates, sandbox, service
from .models import Workspace, WorkspaceAgent


@dataclass(frozen=True)
class WorkspaceTemplate:
    template_id: str
    name: str
    description: str
    goal: str
    # Which v1.1 agent templates to materialize into the workspace.
    agent_template_ids: tuple[str, ...]
    tags: tuple[str, ...] = ()


WORKSPACE_TEMPLATES: tuple[WorkspaceTemplate, ...] = (
    WorkspaceTemplate(
        template_id="storefront-team",
        name="Storefront Team",
        description=(
            "An e-commerce storefront — product grid, prices, and an add-to-cart "
            "flow — built by a planner, UI, backend, researcher, verifier, and "
            "safety reviewer."
        ),
        goal=(
            "Build a polished, modern single-page e-commerce storefront as ONE "
            "self-contained index.html: a sticky header with the brand and a live "
            "cart count; a hero with a bold headline, subtext, and a call-to-action; "
            "a responsive grid of at least 6 product cards (each with an emoji or "
            "CSS-gradient thumbnail, a name, a short description, a price, and an "
            "'Add to cart' button that increments the cart count); and a footer. "
            "Dark theme, one warm accent color, all CSS and JS inline, no external "
            "image files."
        ),
        agent_template_ids=(
            "planner", "ui-agent", "backend-coder", "researcher", "verifier",
            "safety-reviewer",
        ),
        tags=("ecommerce", "web"),
    ),
    WorkspaceTemplate(
        template_id="landing-page-team",
        name="Landing Page Team",
        description=(
            "A marketing landing page — hero, feature sections, testimonial, and a "
            "CTA — built by a planner, UI, marketing, and safety reviewer."
        ),
        goal=(
            "Build a polished single-page marketing landing page as ONE "
            "self-contained index.html: a sticky header; a hero with a bold "
            "headline, subtext, and a call-to-action button; a responsive features "
            "section of at least 3 cards; a short testimonial; and a footer. Dark "
            "theme, one accent color, all CSS and JS inline, no external files."
        ),
        agent_template_ids=("planner", "ui-agent", "marketing", "safety-reviewer"),
        tags=("marketing", "web"),
    ),
    WorkspaceTemplate(
        template_id="web-app-team",
        name="Web App Team",
        description=(
            "A small interactive web app (e.g. a task tracker or dashboard) built "
            "by a planner, UI, backend, verifier, and safety reviewer."
        ),
        goal=(
            "Build a small interactive single-page web app as ONE self-contained "
            "index.html with inline CSS and JS: a header, a main interactive area "
            "(e.g. a task list you can add to and check off, or a small metrics "
            "dashboard) that updates live in the browser, and a footer. Dark theme, "
            "one accent color, no external files."
        ),
        agent_template_ids=(
            "planner", "ui-agent", "backend-coder", "verifier", "safety-reviewer",
        ),
        tags=("app", "web"),
    ),
)


def get_workspace_template(template_id: str) -> WorkspaceTemplate | None:
    return next((t for t in WORKSPACE_TEMPLATES if t.template_id == template_id), None)


def agent_roles(template: WorkspaceTemplate) -> list[str]:
    """The human-readable names of the agents this template materializes."""
    names = []
    for at_id in template.agent_template_ids:
        at = agent_templates.get_template(at_id)
        if at is not None:
            names.append(at.name)
    return names


def instantiate(
    session: Session,
    template: WorkspaceTemplate,
    workspaces_root: str,
    *,
    project_id: str,
    name: str | None = None,
    goal: str | None = None,
) -> tuple[Workspace, list[WorkspaceAgent], list[core_models.Event]]:
    """Create a real workspace from the template: workspace + sandbox + agent
    team. Writes no files — the agents build for real when the user runs a
    build. Reuses existing services; emits their normal events."""
    workspace, events = service.create_workspace(
        session,
        name=name or template.name,
        goal=goal or template.goal,
        project_id=project_id,
        metadata={"workspace_template": template.template_id},
    )
    _status, sandbox_events = sandbox.init_sandbox(session, workspace, workspaces_root)
    events += sandbox_events

    agents: list[WorkspaceAgent] = []
    for at_id in template.agent_template_ids:
        agent_template = agent_templates.get_template(at_id)
        if agent_template is None:
            continue
        agent, agent_events = service.create_agent_from_template(
            session, workspace, agent_template, name=None
        )
        agents.append(agent)
        events += agent_events
    return workspace, agents, events
