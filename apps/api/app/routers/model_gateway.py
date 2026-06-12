"""Model gateway endpoints (v0.7).

Provider configuration is read-only here — keys come from the environment.
A model call routes through one provider interface and emits telemetry through
the normal collector pipeline (graph, replay, inspector, metrics, Cost &
Tokens all integrate). Responses never include keys.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..collector import process_events
from ..deps import require_api_key
from ..model_gateway import ModelRequest, build_model_events
from ..model_gateway.registry import ProviderRegistry, build_registry
from ..model_gateway.secrets_store import (
    CONFIGURABLE_FIELDS,
    clear_provider_secret,
    set_provider_secret,
)
from ..schemas import (
    EventOut,
    ModelCallOut,
    ModelTestCallIn,
    ProviderConfigureIn,
    ProviderHealthOut,
    ProviderListOut,
    ProviderOut,
)
from starlette.concurrency import run_in_threadpool

router = APIRouter()


def _registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


@router.get("/model-gateway/providers", response_model=ProviderListOut)
async def list_providers(request: Request) -> ProviderListOut:
    registry = _registry(request)
    out: list[ProviderOut] = []
    for provider in registry.all():
        health = await provider.health_check()
        out.append(
            ProviderOut(
                name=provider.name,
                configured=provider.configured,
                status=health.status,
                requires_key=provider.requires_key,
                models=provider.models(),
                key_redacted=provider.key_redacted(),
                message=health.detail,
            )
        )
    return ProviderListOut(providers=out)


@router.get("/model-gateway/providers/{provider}/health", response_model=ProviderHealthOut)
async def provider_health(provider: str, request: Request) -> ProviderHealthOut:
    p = _registry(request).get(provider)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown provider")
    health = await p.health_check()
    return ProviderHealthOut(
        name=health.name,
        status=health.status,
        configured=health.configured,
        detail=health.detail,
        key_redacted=health.key_redacted,
    )


async def _provider_health_out(request: Request, provider_name: str) -> ProviderHealthOut:
    provider = _registry(request).get(provider_name)
    health = await provider.health_check()
    return ProviderHealthOut(
        name=health.name,
        status=health.status,
        configured=health.configured,
        detail=health.detail,
        key_redacted=health.key_redacted,
    )


@router.post(
    "/model-gateway/providers/{provider}/configure",
    response_model=ProviderHealthOut,
    dependencies=[Depends(require_api_key)],
)
async def configure_provider(
    provider: str, body: ProviderConfigureIn, request: Request
) -> ProviderHealthOut:
    """Store a provider secret in the local gitignored secrets file (v0.9.1).

    The key never touches the database, the response, the logs, or the event
    stream — only a redacted hint is ever returned.
    """
    fields = CONFIGURABLE_FIELDS.get(provider)
    if fields is None:
        if _registry(request).get(provider) is not None:
            raise HTTPException(
                status_code=422, detail=f"provider {provider!r} needs no configuration"
            )
        raise HTTPException(status_code=404, detail="unknown provider")
    values = {k: v for k, v in (("api_key", body.api_key), ("base_url", body.base_url)) if v}
    unsupported = sorted(set(values) - set(fields))
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=f"provider {provider!r} does not accept: {', '.join(unsupported)}",
        )
    if not values:
        raise HTTPException(status_code=422, detail="nothing to configure")

    settings = request.app.state.settings
    set_provider_secret(settings.secrets_file, provider, values)
    # Rebuild so the new key takes effect immediately, then report health.
    request.app.state.provider_registry = build_registry(settings)
    return await _provider_health_out(request, provider)


@router.post(
    "/model-gateway/providers/{provider}/clear",
    response_model=ProviderHealthOut,
    dependencies=[Depends(require_api_key)],
)
async def clear_provider(provider: str, request: Request) -> ProviderHealthOut:
    if provider not in CONFIGURABLE_FIELDS:
        raise HTTPException(status_code=404, detail="unknown provider")
    settings = request.app.state.settings
    clear_provider_secret(settings.secrets_file, provider)
    request.app.state.provider_registry = build_registry(settings)
    return await _provider_health_out(request, provider)


async def _run_model_call(
    request: Request, body: ModelTestCallIn, *, run_id: str | None
) -> ModelCallOut:
    registry = _registry(request)
    provider = registry.get(body.provider)
    if provider is None:
        raise HTTPException(status_code=422, detail=f"unknown provider {body.provider!r}")
    if body.model_name not in provider.models():
        # Allow free-form model names for real providers; only the mock provider
        # is strict so typos surface in the demo.
        if provider.name == "mock":
            raise HTTPException(
                status_code=422, detail=f"unknown mock model {body.model_name!r}"
            )

    model_request = ModelRequest(
        provider=body.provider,
        model_name=body.model_name,
        prompt=body.prompt,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        agent_id=body.agent_id,
        project_id=body.project_id or "demo-project",
        run_id=run_id or body.run_id,
        metadata={"simulate_failure": body.simulate_failure},
    )
    response = await provider.complete(model_request)

    # Emit telemetry only when the call is tied to a run (test calls without a
    # run still return the response but don't pollute an arbitrary run).
    event_id: str | None = None
    if model_request.run_id:
        events = build_model_events(model_request, response)
        session_factory = request.app.state.session_factory

        def _store():
            session = session_factory()
            try:
                return process_events(session, events)
            finally:
                session.close()

        stored, _ = await run_in_threadpool(_store)
        manager = request.app.state.ws_manager
        for row in stored:
            out = EventOut.model_validate(row)
            await manager.broadcast(out.project_id, {"type": "event", "data": out.model_dump(mode="json")})
            if row.event_type in ("model.completed", "model.failed"):
                event_id = row.event_id

    return ModelCallOut(
        provider=response.provider,
        model_name=response.model_name,
        output_text=response.output_text,
        status=response.status,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=response.total_tokens,
        estimated_cost_usd=response.estimated_cost_usd,
        latency_ms=response.latency_ms,
        error_message=response.error_message,
        event_id=event_id,
    )


@router.post(
    "/model-gateway/test-call",
    response_model=ModelCallOut,
    dependencies=[Depends(require_api_key)],
)
async def test_call(body: ModelTestCallIn, request: Request) -> ModelCallOut:
    return await _run_model_call(request, body, run_id=body.run_id)


@router.post(
    "/runs/{run_id}/model-call",
    response_model=ModelCallOut,
    dependencies=[Depends(require_api_key)],
)
async def run_model_call(run_id: str, body: ModelTestCallIn, request: Request) -> ModelCallOut:
    return await _run_model_call(request, body, run_id=run_id)
