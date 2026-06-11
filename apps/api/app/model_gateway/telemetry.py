"""Bridge a gateway model call into AgentLab telemetry.

Emits model.called + model.completed/model.failed through the normal collector
pipeline, so gateway calls show up in the graph, replay, inspector, metrics, and
the v0.6 Cost & Tokens system for free. Payloads never contain the API key or
the raw prompt text beyond a short preview.
"""
from __future__ import annotations

import uuid

from ..schemas import EventIn
from .base import ModelRequest, ModelResponse


def build_model_events(request: ModelRequest, response: ModelResponse) -> list[EventIn]:
    model_call_id = f"model-{uuid.uuid4().hex[:12]}"
    meta = {"model_call_id": model_call_id, "via": "model-gateway"}
    base_payload = {
        "provider": response.provider,
        "model": response.model_name,
        "model_name": response.model_name,
    }

    called = EventIn(
        event_type="model.called",
        project_id=request.project_id or "default",
        run_id=request.run_id or "gateway",
        source_agent_id=request.agent_id,
        payload={**base_payload, "prompt_preview": request.prompt[:120]},
        metadata=meta,
    )

    result_payload = {
        **base_payload,
        "input_tokens": response.input_tokens or 0,
        "output_tokens": response.output_tokens or 0,
        "total_tokens": response.total_tokens
        or ((response.input_tokens or 0) + (response.output_tokens or 0)),
        "latency_ms": response.latency_ms,
        "status": response.status,
    }
    if response.estimated_cost_usd is not None:
        result_payload["estimated_cost_usd"] = response.estimated_cost_usd

    if response.status == "failed":
        result = EventIn(
            event_type="model.failed",
            project_id=request.project_id or "default",
            run_id=request.run_id or "gateway",
            source_agent_id=request.agent_id,
            payload={**result_payload, "error": response.error_message or "model call failed",
                     "error_message": response.error_message or "model call failed"},
            metadata=meta,
        )
    else:
        result = EventIn(
            event_type="model.completed",
            project_id=request.project_id or "default",
            run_id=request.run_id or "gateway",
            source_agent_id=request.agent_id,
            payload={**result_payload, "output_preview": response.output_text[:200]},
            metadata=meta,
        )
    return [called, result]
