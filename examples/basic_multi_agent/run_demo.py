#!/usr/bin/env python3
"""AgentLab demo: a simulated 5-agent software pipeline.

    Planner -> Researcher -> Coder -> Security Reviewer -> Reporter

Three scenarios, no LLM keys required (model calls are simulated):
  success  clean linear run
  retry    a tool fails and is retried; security bounces a fix back to the coder
  failure  the security reviewer crashes, failing the whole run

Usage:
    python run_demo.py                     # one run of each scenario
    python run_demo.py --scenario failure  # just the failing run
    python run_demo.py --fast              # minimal sleeps (CI / seeding)
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time

# Zero-install convenience: fall back to the in-repo SDK (it is stdlib-only).
try:
    import agentlab
except ImportError:  # pragma: no cover
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "packages", "sdk-python"),
    )
    import agentlab

from agentlab import AgentLabClient

GOAL = "Build a small REST API endpoint and review it for security."


class Pipeline:
    def __init__(self, client: AgentLabClient, rng: random.Random, fast: bool) -> None:
        self.client = client
        self.rng = rng
        self.unit = 0.02 if fast else 0.12

        self.planner = client.trace_agent(
            name="PlannerAgent", role="planner", agent_id="planner"
        )(self._planner)
        self.researcher = client.trace_agent(
            name="ResearchAgent", role="researcher", agent_id="researcher"
        )(self._researcher)
        self.coder = client.trace_agent(
            name="CodingAgent", role="coder", agent_id="coder"
        )(self._coder)
        self.security = client.trace_agent(
            name="SecurityReviewAgent", role="security", agent_id="security"
        )(self._security)
        self.reporter = client.trace_agent(
            name="ReportAgent", role="reporter", agent_id="reporter"
        )(self._reporter)

    # ----------------------------------------------------------- helpers

    def _work(self, low: float = 0.5, high: float = 1.5) -> None:
        time.sleep(self.unit * self.rng.uniform(low, high))

    def _latency(self, base: float) -> float:
        return round(base * self.rng.uniform(0.7, 1.4), 1)

    def _model(self, purpose: str, prompt_tokens: int, completion_tokens: int) -> None:
        latency = self._latency(420)
        cost = round((prompt_tokens * 3 + completion_tokens * 15) / 1_000_000, 6)
        self._work()
        self.client.log_model_call(
            "sim-fable-5",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
            cost_estimate=cost,
            metadata={"purpose": purpose, "simulated": True},
        )

    # ------------------------------------------------------------ agents

    def _planner(self, goal: str, scenario: str) -> dict:
        self._model("decompose goal into tasks", 380, 140)
        self.client.routing_decision(
            task="gather background for the implementation",
            candidates=[
                {"agent_id": "researcher", "trust_score": 0.92, "latency_ms": 800, "cost": 0.01},
                {"agent_id": "cache-agent", "trust_score": 0.55, "latency_ms": 90, "cost": 0.001},
            ],
            selected_agent_id="researcher",
            reason="Fresh-data task: cached knowledge confidence is below threshold, "
            "so the higher-trust researcher wins despite higher latency.",
            confidence=0.87,
        )
        self.client.send_message(
            "researcher",
            {
                "task": "research",
                "instruction": "Collect API design + security best practices for the goal.",
                "goal": goal,
            },
            latency_ms=self._latency(35),
        )
        return {"plan": ["research", "implement", "security-review", "report"], "scenario": scenario}

    def _researcher(self, scenario: str) -> dict:
        queries = ["REST endpoint validation best practices", "OWASP API security top 10"]
        for index, query in enumerate(queries):
            flaky = scenario == "retry" and index == 0
            if flaky:
                try:
                    with self.client.trace_tool("web.search", input={"query": query}):
                        self._work(0.3, 0.6)
                        raise TimeoutError("search backend timed out after 2000ms")
                except TimeoutError:
                    pass  # observed as tool.failed; retry below
            with self.client.trace_tool("web.search", input={"query": query}) as span:
                self._work()
                span.output = {
                    "results": self.rng.randint(3, 9),
                    "top_source": "owasp.org" if "OWASP" in query else "swagger.io",
                }
        self._model("summarize findings into research brief", 900, 260)
        self.client.send_message(
            "coder",
            {
                "task": "implement",
                "summary": "Use pydantic validation, parameterized queries, auth middleware.",
                "sources": ["owasp.org/api-security", "swagger.io/best-practices"],
                "confidence": round(self.rng.uniform(0.82, 0.93), 2),
            },
            latency_ms=self._latency(40),
        )
        return {"sources": 2}

    def _coder(self, revision: int = 0) -> dict:
        purpose = "generate endpoint implementation" if revision == 0 else "apply security fix"
        self._model(purpose, 1100 + 300 * revision, 420)
        with self.client.trace_tool(
            "code.lint", input={"files": ["api/users.py"], "revision": revision}
        ) as span:
            self._work(0.4, 0.8)
            span.output = {"errors": 0, "warnings": 1 if revision == 0 else 0}
        self.client.send_message(
            "security",
            {
                "task": "security-review",
                "diff_summary": "POST /users endpoint with pydantic schema",
                "revision": revision,
            },
            latency_ms=self._latency(30),
        )
        return {"revision": revision}

    def _security(self, scenario: str, revision: int = 0) -> dict:
        if scenario == "failure":
            self._work(0.5, 0.9)
            raise RuntimeError(
                "scanner subprocess crashed (exit 137) before review could complete"
            )
        with self.client.trace_tool(
            "security.scan", input={"target": "api/users.py", "revision": revision}
        ) as span:
            self._work()
            findings = 1 if scenario == "retry" and revision == 0 else 0
            span.output = {"findings": findings, "rules_evaluated": 142}
        self._model("assess scan findings", 700, 180)
        if scenario == "retry" and revision == 0:
            self.client.send_message(
                "coder",
                {
                    "task": "fix-required",
                    "finding": "missing rate limit on POST /users",
                    "severity": "medium",
                },
                latency_ms=self._latency(28),
            )
            return {"verdict": "changes-requested", "findings": 1}
        self.client.send_message(
            "reporter",
            {"task": "report", "verdict": "approved", "findings": 0},
            latency_ms=self._latency(25),
        )
        return {"verdict": "approved", "findings": 0}

    def _reporter(self) -> dict:
        self._model("write run report", 600, 240)
        return {"report": "Endpoint implemented and approved by security review."}

    # ---------------------------------------------------------- scenario

    def execute(self, scenario: str) -> str:
        run_name = f"{scenario} · REST endpoint + security review"
        with self.client.run(name=run_name, metadata={"scenario": scenario}) as run:
            try:
                self.planner(GOAL, scenario)
                self.researcher(scenario)
                self.coder(revision=0)
                verdict = self.security(scenario, revision=0)
                if verdict["verdict"] == "changes-requested":
                    self.coder(revision=1)
                    self.security(scenario, revision=1)
                self.reporter()
                self._update_trust(scenario)
            except RuntimeError:
                # Make the incident visible on the control plane before run.failed lands.
                self.client.update_trust("security", 0.42, reason="crashed mid-review")
                self.client.update_risk("security", 0.58, reason="repeated crash pattern")
                raise
            return run.id

    def _update_trust(self, scenario: str) -> None:
        self.client.update_trust("planner", 0.97, reason="consistent task decomposition")
        self.client.update_trust("reporter", 0.96, reason="clean delivery record")
        if scenario == "retry":
            self.client.update_trust(
                "researcher", 0.81, reason="tool timeout required a retry"
            )
            self.client.update_trust("coder", 0.88, reason="security fix required")
            self.client.update_trust("security", 0.95, reason="caught a real finding")
        else:
            self.client.update_trust("researcher", 0.92, reason="reliable sources")
            self.client.update_trust("coder", 0.94, reason="lint-clean output")
            self.client.update_trust("security", 0.93, reason="thorough review")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", default=os.getenv("AGENTLAB_ENDPOINT", "http://localhost:8000")
    )
    parser.add_argument("--api-key", default=os.getenv("AGENTLAB_API_KEY", "dev-key"))
    parser.add_argument("--project", default=os.getenv("AGENTLAB_PROJECT", "demo-project"))
    parser.add_argument(
        "--scenario",
        choices=["success", "retry", "failure", "all"],
        default="all",
    )
    parser.add_argument("--runs", type=int, default=1, help="repetitions of the scenario set")
    parser.add_argument("--fast", action="store_true", help="minimal sleeps (seeding/CI)")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    client = AgentLabClient(
        project_id=args.project, api_key=args.api_key, endpoint=args.endpoint
    )
    pipeline = Pipeline(client, rng, fast=args.fast)
    scenarios = ["success", "retry", "failure"] if args.scenario == "all" else [args.scenario]

    print(f"AgentLab demo -> {args.endpoint} (project: {args.project})")
    completed: list[tuple[str, str]] = []
    for _ in range(args.runs):
        for scenario in scenarios:
            try:
                run_id = pipeline.execute(scenario)
                print(f"  ✓ {scenario:<8} run completed   {run_id}")
            except RuntimeError as exc:
                # The failure scenario is *supposed* to crash the run.
                run_id = "(see dashboard)"
                print(f"  ✗ {scenario:<8} run failed      ({exc})")
            completed.append((scenario, run_id))
            time.sleep(0.2 if args.fast else 0.6)

    if not client.flush(timeout=10):
        print("warning: some events were still buffered at exit", file=sys.stderr)
        return 1
    client.close()

    print("\nDone. Open the dashboard:")
    print("  docker compose:  http://localhost:3000")
    print("  local dev:       http://localhost:5173")
    print(f"  API check:       {args.endpoint}/api/projects/{args.project}/runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
