"""Agent Builder Studio (v0.8) — author and run multi-agent workflows in-app.

Studio stores workflow *definitions* (agents, edges) and executes them as a
simple DAG through the v0.7 Model Gateway. A Studio run is a completely normal
AgentLab run: it emits the standard run/agent/message/model events through the
collector, so the graph, replay, inspector, metrics, trust/risk, and Cost &
Tokens views all work without special-casing.
"""
from .service import seed_default_workflow

__all__ = ["seed_default_workflow"]
