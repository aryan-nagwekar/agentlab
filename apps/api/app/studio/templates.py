"""Workflow templates (v0.9) — prebuilt agent-team blueprints.

A template is *data*, not a new run format: creating from one builds a plain
``WorkflowIn`` and hands it to the v0.8 Studio service, so the resulting
workflow is editable, validatable, and runnable exactly like a hand-built one.
Every default uses the keyless mock provider; users can switch any agent to a
real provider afterwards in the Studio editor.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import AgentDefIn, EdgeDefIn, WorkflowIn, slugify

# Linear chains read nicely as a staircase on the canvas.
STEP_X = 250
STEP_Y = 110


@dataclass(frozen=True)
class TemplateAgent:
    name: str
    role: str
    description: str
    system_prompt: str
    model_name: str
    provider: str = "mock"
    temperature: float = 0.2
    max_tokens: int = 1000


@dataclass(frozen=True)
class TemplateEdge:
    source_agent_name: str
    target_agent_name: str
    label: str


@dataclass(frozen=True)
class WorkflowTemplate:
    template_id: str
    name: str
    description: str
    category: str
    tags: tuple[str, ...]
    difficulty: str  # beginner | intermediate
    use_case: str
    default_input: str
    agents: tuple[TemplateAgent, ...]
    edges: tuple[TemplateEdge, ...]
    expected_outputs: tuple[str, ...]
    demo_notes: str


def _chain(agents: tuple[TemplateAgent, ...], labels: tuple[str, ...]) -> tuple[TemplateEdge, ...]:
    """Connect agents in order; one label per hop."""
    assert len(labels) == len(agents) - 1
    return tuple(
        TemplateEdge(agents[i].name, agents[i + 1].name, labels[i])
        for i in range(len(agents) - 1)
    )


def _t(  # noqa: PLR0913 - a template is intrinsically wide
    template_id: str,
    name: str,
    description: str,
    category: str,
    tags: tuple[str, ...],
    difficulty: str,
    use_case: str,
    default_input: str,
    agents: tuple[TemplateAgent, ...],
    labels: tuple[str, ...],
    expected_outputs: tuple[str, ...],
    demo_notes: str,
) -> WorkflowTemplate:
    return WorkflowTemplate(
        template_id=template_id,
        name=name,
        description=description,
        category=category,
        tags=tags,
        difficulty=difficulty,
        use_case=use_case,
        default_input=default_input,
        agents=agents,
        edges=_chain(agents, labels),
        expected_outputs=expected_outputs,
        demo_notes=demo_notes,
    )


CODE_REVIEW = _t(
    "code-review-team",
    "Code Review Agent Team",
    "Generate or review code, write tests, and produce a final review.",
    "engineering",
    ("code", "review", "testing", "security"),
    "beginner",
    "Good for: reviewing a feature end-to-end — plan, implementation, tests, security pass, and a final report.",
    "Build a simple FastAPI endpoint that accepts a username and returns a "
    "greeting. Then review it for basic security and testing issues.",
    (
        TemplateAgent(
            "Planner Agent", "planner",
            "Breaks the request into an ordered implementation plan.",
            "Break the request into a short, ordered plan for the team.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Coder Agent", "coder",
            "Implements the plan as clean, minimal code.",
            "Implement the plan as clean, minimal code.",
            "mock:gpt-4.1",
        ),
        TemplateAgent(
            "Test Writer Agent", "tester",
            "Writes focused tests for the implementation.",
            "Write focused tests covering the happy path and obvious edge cases.",
            "mock:gemini-pro",
        ),
        TemplateAgent(
            "Security Reviewer Agent", "security",
            "Reviews the code and tests for basic security issues.",
            "Review the code for basic security issues (injection, validation, secrets).",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Final Report Agent", "reporter",
            "Summarizes the work, tests, and findings as a review report.",
            "Summarize the implementation, test coverage, and security findings as a concise review.",
            "mock:gemini-pro",
        ),
    ),
    ("plan", "code", "tests", "findings"),
    (
        "An ordered implementation plan",
        "Code for the requested feature",
        "A small test suite",
        "Security findings",
        "A final review report",
    ),
    "Run it, then open Cost & Tokens to compare the coder vs. the reviewers, "
    "and step through the hand-offs in Replay.",
)

RESEARCH = _t(
    "research-team",
    "Research Agent Team",
    "Research a topic, verify claims, summarize findings, and produce a cited report.",
    "research",
    ("research", "fact-checking", "citations", "summarization"),
    "beginner",
    "Good for: turning a research question into a verified, cited summary.",
    "Research the main security risks in multi-agent AI systems and summarize "
    "the findings for a technical audience.",
    (
        TemplateAgent(
            "Research Planner", "planner",
            "Frames the research question and plans the investigation.",
            "Break the research question into specific sub-questions worth investigating.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Researcher Agent", "researcher",
            "Gathers findings for each sub-question.",
            "Answer each sub-question with concrete findings and note where each came from.",
            "mock:gpt-4.1",
        ),
        TemplateAgent(
            "Fact Checker Agent", "fact-checker",
            "Verifies claims and flags weak or unsupported statements.",
            "Check each claim for plausibility and flag anything unsupported or overstated.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Citation Reviewer Agent", "citations",
            "Reviews sourcing and citation quality.",
            "Review the sourcing: every important claim should trace to a source worth citing.",
            "mock:gemini-pro",
        ),
        TemplateAgent(
            "Summary Agent", "reporter",
            "Produces the final cited summary.",
            "Write the final summary for a technical audience, keeping the verified citations.",
            "mock:gemini-pro",
        ),
    ),
    ("sub-questions", "findings", "verified claims", "cited findings"),
    (
        "A research plan with sub-questions",
        "Findings per sub-question",
        "Fact-check notes",
        "Citation review",
        "A cited summary report",
    ),
    "A clean example of sequential refinement — each agent narrows and "
    "hardens the previous agent's output.",
)

RESUME = _t(
    "resume-tailoring-team",
    "Resume Tailoring Agent Team",
    "Analyze a job description, tailor resume bullets, identify missing keywords, "
    "and draft a cover-letter outline.",
    "careers",
    ("resume", "job-search", "ats", "cover-letter"),
    "beginner",
    "Good for: tailoring application materials to a specific job posting.",
    "Tailor a resume for an AI automation internship focused on agents, "
    "backend systems, security, and workflow automation.",
    (
        TemplateAgent(
            "Job Description Analyzer", "analyst",
            "Extracts the role's core requirements and signals.",
            "Extract the role's must-have skills, nice-to-haves, and the language the posting uses.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Resume Optimizer", "optimizer",
            "Rewrites resume bullets to match the role.",
            "Rewrite resume bullets to target the extracted requirements with concrete impact.",
            "mock:gpt-4.1",
        ),
        TemplateAgent(
            "ATS Keyword Agent", "ats",
            "Finds missing keywords an ATS would scan for.",
            "List keywords from the job description that are still missing from the resume.",
            "mock:gemini-pro",
        ),
        TemplateAgent(
            "Cover Letter Agent", "writer",
            "Drafts a cover-letter outline from the tailored material.",
            "Draft a short cover-letter outline connecting the candidate's strengths to the role.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Final Reviewer", "reviewer",
            "Reviews everything for consistency and tone.",
            "Review the bullets, keywords, and outline for consistency, honesty, and tone.",
            "mock:gemini-pro",
        ),
    ),
    ("requirements", "tailored bullets", "keyword gaps", "outline"),
    (
        "A requirements breakdown of the posting",
        "Tailored resume bullets",
        "A missing-keyword list",
        "A cover-letter outline",
        "A consistency review",
    ),
    "Swap the default input for a real job posting to make the demo personal.",
)

SOC = _t(
    "soc-investigation-team",
    "SOC Investigation Agent Team",
    "Analyze a mock security incident, classify severity, build a timeline, "
    "and write an incident report.",
    "security",
    ("soc", "incident-response", "triage", "forensics"),
    "intermediate",
    "Good for: walking a mock alert through triage, timeline, remediation, and reporting.",
    "Investigate a mock alert where a service account made unusual API calls "
    "and several failed login attempts occurred.",
    (
        TemplateAgent(
            "Log Parser Agent", "parser",
            "Extracts the relevant events from the mock logs.",
            "Extract the relevant events, actors, and timestamps from the described alert.",
            "mock:gemini-pro",
        ),
        TemplateAgent(
            "Threat Classifier Agent", "classifier",
            "Classifies the threat type and severity.",
            "Classify the likely threat type and assign a severity with reasoning.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Timeline Builder Agent", "timeline",
            "Reconstructs the order of events.",
            "Build an ordered timeline of the incident from the parsed events.",
            "mock:gpt-4.1",
        ),
        TemplateAgent(
            "Remediation Agent", "remediation",
            "Proposes containment and remediation steps.",
            "Propose containment, remediation, and hardening steps proportional to the severity.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Incident Report Agent", "reporter",
            "Writes the final incident report.",
            "Write a concise incident report: summary, severity, timeline, remediation, follow-ups.",
            "mock:gemini-pro",
        ),
    ),
    ("parsed events", "classification", "timeline", "remediation plan"),
    (
        "Parsed events and actors",
        "A threat classification with severity",
        "An incident timeline",
        "A remediation plan",
        "An incident report",
    ),
    "Pairs well with the Security Lab: inject a mock attack into the resulting "
    "run and watch trust/risk react.",
)

SUPPORT = _t(
    "customer-support-team",
    "Customer Support Agent Team",
    "Classify a support request, retrieve likely solution steps, draft a response, "
    "and review tone/risk.",
    "support",
    ("support", "triage", "policy", "tone"),
    "beginner",
    "Good for: drafting a quality-checked reply to a customer issue.",
    "A customer says their account login keeps failing after enabling "
    "two-factor authentication. Draft a helpful support response.",
    (
        TemplateAgent(
            "Ticket Classifier", "classifier",
            "Classifies the request type and urgency.",
            "Classify the ticket's category, urgency, and what the customer actually needs.",
            "mock:gemini-pro",
        ),
        TemplateAgent(
            "Troubleshooting Agent", "troubleshooter",
            "Lists the most likely causes and fixes.",
            "List the most likely causes and step-by-step fixes for the classified issue.",
            "mock:gpt-4.1",
        ),
        TemplateAgent(
            "Policy Checker Agent", "policy",
            "Checks the proposed steps against support policy.",
            "Check the proposed steps for anything risky, off-policy, or over-promising.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Response Writer Agent", "writer",
            "Drafts the customer-facing reply.",
            "Draft a clear, friendly customer reply using the approved steps.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Quality Reviewer", "reviewer",
            "Reviews tone, clarity, and risk before sending.",
            "Review the reply for tone, clarity, and anything that could mislead the customer.",
            "mock:gemini-pro",
        ),
    ),
    ("classification", "fix steps", "approved steps", "draft reply"),
    (
        "A ticket classification",
        "Troubleshooting steps",
        "A policy check",
        "A drafted customer reply",
        "A tone/risk review",
    ),
    "Shows a guardrail pattern: the policy checker sits between solution "
    "generation and the customer-facing writer.",
)

DATA_ANALYSIS = _t(
    "data-analysis-team",
    "Data Analysis Agent Team",
    "Plan an analysis, inspect a dataset description, generate insights, "
    "check assumptions, and summarize results.",
    "analytics",
    ("data", "analysis", "insights", "reporting"),
    "intermediate",
    "Good for: turning a dataset description into checked insights and an executive summary.",
    "Analyze a mock sales dataset and identify revenue trends, customer "
    "segments, and possible operational risks.",
    (
        TemplateAgent(
            "Analysis Planner", "planner",
            "Plans the analysis questions and approach.",
            "Plan the analysis: the questions to answer and the approach for each.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Data Profiler Agent", "profiler",
            "Profiles the dataset described in the input.",
            "Describe the dataset's likely shape, fields, and quality issues from the description.",
            "mock:gpt-4.1",
        ),
        TemplateAgent(
            "Insight Generator Agent", "analyst",
            "Generates candidate insights from the profile.",
            "Generate the most decision-relevant insights for the planned questions.",
            "mock:claude-sonnet",
        ),
        TemplateAgent(
            "Assumption Checker Agent", "checker",
            "Stress-tests the insights' assumptions.",
            "List the assumptions behind each insight and flag the fragile ones.",
            "mock:gemini-pro",
        ),
        TemplateAgent(
            "Executive Summary Agent", "reporter",
            "Writes the executive summary.",
            "Write an executive summary: key findings, caveats, and recommended next steps.",
            "mock:gemini-pro",
        ),
    ),
    ("analysis plan", "data profile", "insights", "checked insights"),
    (
        "An analysis plan",
        "A dataset profile",
        "Candidate insights",
        "An assumption check",
        "An executive summary",
    ),
    "The assumption checker is the interesting hop — watch how it reshapes "
    "the final summary in Replay.",
)

TEMPLATES: dict[str, WorkflowTemplate] = {
    t.template_id: t
    for t in (CODE_REVIEW, RESEARCH, RESUME, SOC, SUPPORT, DATA_ANALYSIS)
}


def agent_position(index: int) -> tuple[float, float]:
    return float(index * STEP_X), float(index * STEP_Y)


def build_workflow_in(
    template: WorkflowTemplate, *, project_id: str, name: str | None = None
) -> WorkflowIn:
    """Materialize a template into a normal v0.8 workflow definition."""
    slug_by_name = {agent.name: slugify(agent.name) for agent in template.agents}
    agents = []
    for index, agent in enumerate(template.agents):
        x, y = agent_position(index)
        agents.append(
            AgentDefIn(
                agent_id=slug_by_name[agent.name],
                name=agent.name,
                role=agent.role,
                description=agent.description,
                system_prompt=agent.system_prompt,
                provider=agent.provider,
                model_name=agent.model_name,
                temperature=agent.temperature,
                max_tokens=agent.max_tokens,
                position_x=x,
                position_y=y,
                metadata={"template_id": template.template_id},
            )
        )
    edges = [
        EdgeDefIn(
            edge_id=f"edge-{index + 1}",
            source_agent_id=slug_by_name[edge.source_agent_name],
            target_agent_id=slug_by_name[edge.target_agent_name],
            label=edge.label,
        )
        for index, edge in enumerate(template.edges)
    ]
    return WorkflowIn(
        name=name or template.name,
        description=template.description,
        project_id=project_id,
        agents=agents,
        edges=edges,
    )
