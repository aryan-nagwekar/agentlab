"""Lab Mode: safe, simulated fault injection.

Every fault is *telemetry simulation*: it emits a `fault.injected` event plus
realistic follow-up events (agent.failed, tool.failed, …) through the normal
collector pipeline, as if the failure had really happened. Nothing here kills
processes, drops real network traffic, touches secrets, or controls running
agents — faults are marked `metadata.safe_simulation: true` end to end.

The fault event wire format follows the product spec:

    {
      "event_type": "fault.injected",
      "source_agent_id": "lab-controller",
      "target_agent_id": "<victim>",
      "payload": {"fault_type": "...", "reason": "...", ...params},
      "metadata": {"safe_simulation": true, "created_by": "lab"}
    }
"""
from __future__ import annotations

import uuid
from typing import Any

from .schemas import EventIn, FaultInjectIn, FaultTemplateOut

LAB_CONTROLLER_ID = "lab-controller"

FAULT_TEMPLATES: list[FaultTemplateOut] = [
    FaultTemplateOut(
        fault_type="kill_agent",
        label="Kill agent",
        description="Simulate an abrupt agent crash; the node turns failed.",
        target_kind="agent",
        params=[{"name": "duration_seconds", "type": "number", "default": 30}],
        emits=["fault.injected", "agent.failed"],
    ),
    FaultTemplateOut(
        fault_type="overload_agent",
        label="Overload agent",
        description="Simulate task-queue saturation; the node turns overloaded.",
        target_kind="agent",
        params=[{"name": "queue_depth", "type": "number", "default": 250}],
        emits=["fault.injected", "agent.heartbeat (status=overloaded)"],
    ),
    FaultTemplateOut(
        fault_type="force_tool_failure",
        label="Force tool failure",
        description="Simulate a tool call blowing up on the target agent.",
        target_kind="agent",
        params=[{"name": "tool_name", "type": "string", "default": "web.search"}],
        emits=["fault.injected", "tool.called", "tool.failed"],
    ),
    FaultTemplateOut(
        fault_type="simulate_model_timeout",
        label="Simulate model timeout",
        description="Simulate a hung model call that times out on the target agent.",
        target_kind="agent",
        params=[
            {"name": "model", "type": "string", "default": "sim-fable-5"},
            {"name": "timeout_ms", "type": "number", "default": 30000},
        ],
        emits=["fault.injected", "model.called", "model.failed"],
    ),
    FaultTemplateOut(
        fault_type="delay_messages",
        label="Delay messages",
        description="Simulate a slow channel: a message crosses with heavy latency.",
        target_kind="channel",
        params=[{"name": "delay_ms", "type": "number", "default": 2000}],
        emits=["fault.injected", "message.sent", "message.received (delayed)"],
    ),
    FaultTemplateOut(
        fault_type="drop_messages",
        label="Drop messages",
        description="Simulate message loss on a channel; the edge turns failed.",
        target_kind="channel",
        params=[{"name": "drop_rate", "type": "number", "default": 0.3}],
        emits=["fault.injected", "message.sent", "message.failed"],
    ),
]

FAULT_TYPES: frozenset[str] = frozenset(t.fault_type for t in FAULT_TEMPLATES)
_CHANNEL_FAULTS: frozenset[str] = frozenset(
    t.fault_type for t in FAULT_TEMPLATES if t.target_kind == "channel"
)


def is_channel_fault(fault_type: str) -> bool:
    return fault_type in _CHANNEL_FAULTS


def _lab_metadata(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {"safe_simulation": True, "created_by": "lab"}
    if extra:
        meta.update(extra)
    return meta


def build_fault_events(
    project_id: str, run_id: str, request: FaultInjectIn
) -> list[EventIn]:
    """The fault.injected event plus realistic follow-up telemetry."""
    params = request.params or {}
    target = request.target_agent_id
    channel_source = request.source_agent_id
    reason = request.reason or f"Simulated {request.fault_type} from Lab Mode"

    def make(
        event_type: str,
        *,
        source: str | None,
        tgt: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventIn:
        return EventIn(
            event_type=event_type,
            project_id=project_id,
            run_id=run_id,
            source_agent_id=source,
            target_agent_id=tgt,
            payload=payload or {},
            metadata=_lab_metadata(metadata),
        )

    fault_payload: dict[str, Any] = {
        "fault_type": request.fault_type,
        "reason": reason,
        **params,
    }
    if channel_source:
        fault_payload["channel"] = {"source_agent_id": channel_source, "target_agent_id": target}
    fault = make(
        "fault.injected", source=LAB_CONTROLLER_ID, tgt=target, payload=fault_payload
    )
    events = [fault]
    link = {"fault_event_id": fault.event_id}

    if request.fault_type == "kill_agent":
        events.append(
            make(
                "agent.failed",
                source=target,
                payload={
                    "error": "SimulatedCrash: agent terminated by Lab Mode (no real process was killed)",
                    "latency_ms": 0,
                    "reason": reason,
                },
                metadata=link,
            )
        )

    elif request.fault_type == "overload_agent":
        events.append(
            make(
                "agent.heartbeat",
                source=target,
                payload={
                    "status": "overloaded",
                    "stats": {"queue_depth": params.get("queue_depth", 250), "simulated": True},
                },
                metadata=link,
            )
        )

    elif request.fault_type == "force_tool_failure":
        tool_name = str(params.get("tool_name") or "web.search")
        tool_call_id = f"tool-{uuid.uuid4().hex[:12]}"
        tool_meta = {**link, "tool_call_id": tool_call_id}
        events.append(
            make(
                "tool.called",
                source=target,
                payload={"tool_name": tool_name, "input": {"injected_by": "lab"}},
                metadata=tool_meta,
            )
        )
        events.append(
            make(
                "tool.failed",
                source=target,
                payload={
                    "tool_name": tool_name,
                    "error": "SimulatedToolError: forced failure from Lab Mode",
                    "latency_ms": 42,
                },
                metadata=tool_meta,
            )
        )

    elif request.fault_type == "simulate_model_timeout":
        model = str(params.get("model") or "sim-fable-5")
        timeout_ms = float(params.get("timeout_ms") or 30000)
        model_meta = {**link, "model_call_id": f"model-{uuid.uuid4().hex[:12]}"}
        events.append(
            make("model.called", source=target, payload={"model": model}, metadata=model_meta)
        )
        events.append(
            make(
                "model.failed",
                source=target,
                payload={
                    "model": model,
                    "error": f"SimulatedTimeout: no tokens after {timeout_ms:.0f}ms",
                    "latency_ms": timeout_ms,
                },
                metadata=model_meta,
            )
        )

    elif request.fault_type == "delay_messages":
        delay_ms = float(params.get("delay_ms") or 2000)
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        message_meta = {**link, "message_id": message_id}
        content = {"note": "synthetic message delayed by Lab Mode", "delay_ms": delay_ms}
        events.append(
            make(
                "message.sent",
                source=channel_source,
                tgt=target,
                payload={"content": content},
                metadata=message_meta,
            )
        )
        events.append(
            make(
                "message.received",
                source=channel_source,
                tgt=target,
                payload={"latency_ms": delay_ms},
                metadata=message_meta,
            )
        )

    elif request.fault_type == "drop_messages":
        drop_rate = float(params.get("drop_rate") or 0.3)
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        message_meta = {**link, "message_id": message_id}
        events.append(
            make(
                "message.sent",
                source=channel_source,
                tgt=target,
                payload={"content": {"note": "synthetic message dropped by Lab Mode"}},
                metadata=message_meta,
            )
        )
        events.append(
            make(
                "message.failed",
                source=channel_source,
                tgt=target,
                payload={"error": f"SimulatedDrop: message lost (drop_rate={drop_rate})"},
                metadata=message_meta,
            )
        )

    return events
