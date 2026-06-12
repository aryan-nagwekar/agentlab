# AgentLab — Project Handoff Packet

> Snapshot taken 2026-06-12, at the start of the v0.7.1 Model Gateway patch.
> Status in §6 reflects that moment; see git history for anything later.
>
> **Addendum (2026-06-12, later):** v0.7.1 shipped (Gemini provider + Ollama
> troubleshooting, 134 pytest + 44 vitest). v0.8 Agent Builder Studio shipped:
> `apps/api/app/studio/` (workflow/agent/edge definitions, DAG validation,
> deterministic executor through the Model Gateway), `/api/studio/*` endpoints,
> Studio UI (React Flow canvas, agent/edge editors, run panel), seeded "Code
> Review Agent Team" (mock-only). Studio runs emit normal AgentLab events —
> graph/replay/inspector/metrics/trust-risk/costs all work unchanged.
>
> v0.9 Project Templates shipped: `app/studio/templates.py` registry of six
> 5-agent blueprints (code-review-team, research-team, resume-tailoring-team,
> soc-investigation-team, customer-support-team, data-analysis-team), `GET
> /api/studio/templates[/{id}]` + `POST …/{id}/create-workflow` (materializes
> a normal v0.8 workflow), gallery + preview UI at /studio/templates, default
> input carried into the editor's run panel via `?template=`.
>
> v0.9.1 Chat Mode / Agent Mode + secure provider setup shipped: Studio mode
> switcher (Chat = read-only Q&A via a deterministic local assistant; Agent =
> actions, `/connect <provider>`, `/run`); secure provider modal (password
> field) backed by `POST /model-gateway/providers/{p}/configure|clear`;
> secrets in gitignored `.agentlab-secrets.json` (0600, overlays env, never
> DB/logs/events/responses); key-like chat pastes blocked with a warning.
> v1.0 Runtime Workspaces shipped (Runtime master plan saved at
> docs/AGENTLAB_RUNTIME_V1_PLAN.md): `app/runtime/` workspace + artifact
> models (metadata only), status lifecycle (DELETE = archive), workspace.*
> events (registry extended in API + SDK) into a per-workspace activity run
> (`{workspace_id}-activity`) so activity/timeline/replay work unchanged;
> `/api/runtime/workspaces` CRUD + `/activity` + `/artifacts`; Runtime UI
> (list, create, detail with status banner / goal / activity / health
> placeholder). NO execution: no sandbox, command runner, file writes,
> enforcement, approvals, validators, quarantine, or bottle demo.
> Next gated milestone: **Runtime v1.1 Workspace Agent Definitions +
> Permissions** (spec to be provided; requires explicit approval).

## 1. One-paragraph product summary

AgentLab is a production-style observability and control plane for multi-agent AI systems — "Wireshark + Mininet + Kubernetes for AI agents." It instruments agent apps via a zero-dependency Python SDK, collects events into a FastAPI backend, and renders a dark-mode React dashboard: live agent topology (React Flow), message-level inspection, run metrics, a replay debugger, a fault-injection lab, a malicious-agent cyber range, a deterministic trust/risk engine, a cost/token profiler, and a local-first model gateway with BYOK. What makes it different from prompt-tracing tools (LangSmith/Langfuse): it treats a multi-agent run as a network (agents=nodes, messages=packets, runs=captures) and is the debugging/testing/control layer on top of any framework. Repo is a portfolio-grade project at `/Users/aryannagwekar/public1/agentlab` (own git repo, branch `main`). Built incrementally with an explicit owner approval gate between every version.

## 2. Completed versions

Each shipped with: live browser verification, generated screenshots (`apps/web npm run screenshots` → `docs/screenshots/`), docs (README/ARCHITECTURE/ROADMAP/PRODUCT_SPEC), and a final report ending in an approval question.

- **v0.1 Live Observability** — SDK (`packages/sdk-python/agentlab/`: `_events.py` 22-type registry, `_context.py` contextvars run→agent→span, `_transport.py` buffered bg-thread urllib POST w/ retry+outage buffering, `client.py`, `decorators.py`). FastAPI collector (`apps/api/app/`: `collector.py` projections, `models.py`, `graph.py`, `metrics.py`, `ws.py`, routers). Append-only `events` table is source of truth; runs/agents/messages/tool_calls/routing_decisions are ingest-time projections. React dashboard (Vite+TS+Tailwind v4, React Flow v12, Recharts, zustand). Docker Compose + nginx + Makefile + CI. Limitation: `create_all` not Alembic; single-node WS.
- **v0.2 Replay Debugger** — `app/replay.py` `fold_events` (pure event fold), endpoints `/runs/{id}/replay` (tape+markers) & `/replay/graph?index=k`. Frontend `components/replay/` (`replayReducer.ts` mirror, ReplayControls, ReplayView): play/pause/step/scrub, jump-to-error/tool/routing, inspector follows playhead. Limitation: tape loads once (≤5000 events), folds from scratch per cursor.
- **v0.3 Fault Injection Lab** — `app/lab.py` (6 fault types), endpoints `/lab/fault-templates`, POST/GET `/runs/{id}/faults`. Faults = `fault.injected` + realistic follow-up telemetry. Frontend Lab page. `markers.faults` + Fault jump. Limitation: telemetry simulation only (no live traffic interception); quarantine is a visualization marker.
- **v0.4 Malicious Agent Simulation** — `app/attacks.py` (8 attack types), endpoints `/lab/attack-templates`, POST/GET `/runs/{id}/attacks`. New event types `agent.joined`/`agent.suspicious`/`message.flagged`. Security Lab UI (mode toggle), suspicious/quarantine node states, flagged amber edges, `markers.attacks` + Attack jump. SAFETY: all mock — `MOCK_` literals, `safe_simulation:true`, `real_secrets_accessed:false`, `real_network_access:false`; no real files/env/network/shell. lab-controller excluded from topology.
- **v0.5 Trust/Risk Engine** — `app/scoring.py` deterministic pure event-fold (Effect rule table: deltas + floors/ceilings; attack/fault score the TARGET not lab-controller; suspicious=trust≤0.5/risk≥0.6, quarantine=trust 0.1–0.2/risk≥0.9). ONE rule table shared by collector (stored Agent row)+graph+replay+metrics+JS mirror `apps/web/src/lib/scoring.ts`. Endpoints `/runs/{id}/scores|score-history|risk-summary`, `/agents/{id}/scores`. Fixed headline bug: quarantined malicious agent reads trust 0.10/risk 1.0, not 1.0. Scores derived on read → no `score.updated` emitted → no feedback loops. UI: tier badges, ScorePanel (reason+factors+history), RiskSummaryView, replay score evolution. Limitation: scores+explains but does NOT enforce (no routing impact/decay).
- **v0.6 Cost/Token Attribution** — `app/pricing.py` static MODEL_PRICING (mock providers, USD/1M tokens, local-ollama free) + `app/costing.py` pure fold over `model.*` events → per-agent/model/run tokens+cost+latency+failures+retries. Cost ALWAYS recomputed from tokens (single source) shared by costs endpoints + metrics + graph + collector-finalize + JS mirror `apps/web/src/lib/costing.ts`. Endpoints `/runs/{id}/costs|token-summary`, `/agents/{id}/costs`, `/projects/{id}/cost-summary`. SDK `log_model_call` gained provider/model_name/input/output_tokens (back-compat). UI: Cost & Tokens tab (cards, ranking bars, model-by-provider, agent table), model-call inspector, replay "Cost so far" strip. Demo: coder most-expensive (claude-sonnet), researcher most-token-heavy (gpt-4.1), security free (local-ollama). Limitation: static pricing, mock providers only; failed call still costs input tokens (intentional).
- **v0.7 Model Gateway / BYOK** — `app/model_gateway/`: `base.py` (ModelRequest/Response/ProviderHealth/ModelProvider + `redact_key`), `providers/` mock (keyless deterministic)/openai_compatible/anthropic/ollama, `_http.py` (stdlib urllib via asyncio.to_thread; strips headers from errors), `registry.py` (built from Settings → app.state), `telemetry.py` (gateway call → `model.called`+`completed`/`failed` through collector). `routers/model_gateway.py`: GET `/model-gateway/providers`, `/providers/{p}/health`, POST `/model-gateway/test-call`, `/runs/{id}/model-call`. SDK `client.model_call()` (clean `model.failed` if gateway unreachable, never raises). KEY SAFETY: keys env-only via Settings validation_alias + populate_by_name=True; never stored/returned/logged; only `redact_key` hint (`sk-...abcd`) exposed; a test plants a fake key and greps responses for leaks. UI: Settings → Model Gateway (provider cards + safe test-call). Demo `--use-gateway`. Frontend tests use Testing Library + jsdom (`// @vitest-environment jsdom`). Limitation: local-first BYOK only (no cloud secret storage), no Gemini provider yet (was deferred → now v0.7.1).

## 3. Current architecture

- **Backend (`apps/api/app/`)**: FastAPI app factory `main.py` (`create_app(Settings)`, lifespan create_all w/ Postgres retry, CORS, `/api/health`, WS). `config.py` Settings (env_prefix `AGENTLAB_`, populate_by_name=True; provider keys via `validation_alias=AliasChoices(...)`). `db.py` (engine per app), `models.py` (Project/Run/Agent[PK project_id+id]/Event[append-only, `meta`→`metadata` col]/Message/ToolCall/RoutingDecision), `schemas.py` (Pydantic wire contract). Routers: events, projects, runs, agents, lab, scoring, costs, model_gateway. Engines: `scoring.py`, `costing.py`, `pricing.py`, `graph.py`, `replay.py`, `metrics.py`, `model_gateway/`.
- **Event pipeline**: SDK buffered transport → POST `/api/events` (single or `{events:[...]}`, idempotent by `event_id`, optional X-API-Key) → `collector.process_events` (auto-create project/run/agent shells, per-type projections, applies scoring+costing to stored Agent/Run rows) → WS broadcast per project. Read APIs derive graph/metrics/scores/costs/replay on read from the event stream.
- **DB/projections**: SQLite default (`AGENTLAB_DATABASE_URL`), Postgres in compose. `events` append-only source of truth; everything else is a projection. JSON cols (JSONB on Postgres). Timestamps naive UTC, serialized with Z.
- **WebSocket**: WS `/ws/projects/{project_id}`, server-push `{type:"event", data:EventOut}`, per-project ConnectionManager, dead-socket eviction never breaks ingest. Frontend `hooks/useProjectStream.ts` reconnecting.
- **Replay fold**: ordered tape (timestamp, id); `fold_events`/`foldReplayGraph` reconstruct topology at cursor k; scoring + costing JS mirrors give per-cursor evolution. Same-semantics Python↔JS pinned by pytest+vitest.
- **Frontend (`apps/web/src/`)**: `lib/` (api.ts, types.ts, format.ts, status.ts, scoring.ts, costing.ts), `components/` (topology, timeline, inspector, replay, metrics, scoring, costs, gateway, layout, ui), `pages/` (Dashboard, Projects, ProjectDetail, RunDetail[tabs: topology/timeline/metrics/cost/replay], AgentDetail, Lab, Settings). RunDetail inspector gets runId for run-scoped score panels.
- **SDK (`packages/sdk-python/agentlab/`)**: zero runtime deps; `AGENTLAB_DISABLED=1` no-op; `model_call` does direct urllib POST to gateway (stores `self._api_key`).

## 4. Important commands

```sh
make install                                   # venv + editable installs + npm install
make dev                                       # API :8000 (SQLite) + seed-if-empty + dashboard :5173
make demo                                      # seed demo runs
make test                                      # backend + SDK pytest  (apps/api/tests + packages/sdk-python/tests)
cd apps/web && npm test                        # vitest (incl. jsdom component tests)
cd apps/web && npm run build                   # tsc --noEmit && vite build
cd apps/web && npm run screenshots             # Playwright → docs/screenshots (needs API+demo seeded)
make up-demo                                   # docker compose stack + seed (:3000)
python examples/basic_multi_agent/run_demo.py --fast --seed 5                    # seed all 5 scenarios
python examples/basic_multi_agent/run_demo.py --scenario success --use-gateway   # route via gateway (mock)
# Model gateway:
curl localhost:8000/api/model-gateway/providers
curl -X POST localhost:8000/api/runs/<run>/model-call -H 'Content-Type: application/json' \
  -d '{"provider":"mock","model_name":"mock:claude-sonnet","prompt":"hi","agent_id":"planner","project_id":"demo-project"}'
# Ollama check:
curl http://localhost:11434/api/tags           # ollama serve; ollama pull llama3.2
```

Preview server config: `agentlab-web` entry in `/Users/aryannagwekar/public1/.claude/launch.json` (shared with aryan-junction — don't clobber). React Flow nodes need real pointerdown/up events in preview, not synthetic `.click()`.

## 5. Environment variables

| Var | Required? | Notes |
| --- | --- | --- |
| `AGENTLAB_DATABASE_URL` | optional | default `sqlite:///./agentlab.db`; compose injects Postgres |
| `AGENTLAB_API_KEYS` | optional | comma-sep; empty = open local mode; if set, write path needs X-API-Key |
| `AGENTLAB_CORS_ORIGINS` | optional | default localhost:3000,5173 |
| `AGENTLAB_DISABLED` | optional | `=1` makes SDK a no-op |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | optional | gateway BYOK; base_url default api.openai.com/v1 (also OpenRouter via `OPENROUTER_API_KEY`) |
| `ANTHROPIC_API_KEY` | optional | gateway BYOK |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | optional | added in v0.7.1; GEMINI preferred (AliasChoices left-to-right); `GEMINI_BASE_URL` overridable for tests |
| `OLLAMA_BASE_URL` | optional | default http://localhost:11434; Docker users: http://host.docker.internal:11434 |

**Key security rules (NON-NEGOTIABLE)**: keys read from server env only (never DB), never returned to frontend, never logged, never in exceptions (HTTP helper strips headers), never committed (`.env` gitignored; `.env.example` placeholders only). UI shows redacted hint only (`sk-...abcd` / `AIza...abcd`). Mock provider works with zero keys. A pytest plants a fake key and greps all responses to prove no leak.

## 6. Current exact status (at snapshot time)

- **Version**: v0.7 fully shipped & committed (api/web both at 0.7.0). **v0.7.1 IN PROGRESS, UNCOMMITTED.**
- **Latest commits (HEAD = 419e144)**: `419e144` docs(v0.7) · `744fc11` feat(web) gateway UI · `2f9287c` feat(api+sdk) gateway · then v0.6 commits.
- **Test counts (v0.7, all green)**: 130 pytest (apps/api + SDK), 42 vitest. Clean web build, zero console errors.
- **Known bugs**: none open. (v0.4 trust=1.0 bug fixed in v0.5.)
- **Known limitations**: static pricing/mock providers for cost; gateway local-first BYOK only; scoring doesn't enforce; replay tape snapshot ≤5000 events; create_all not Alembic; read API unauthenticated in local mode.
- **Fully demoable**: all of v0.1–v0.7 (topology, replay, fault lab, security lab, trust/risk, cost/tokens, model gateway test-call).
- **Not built yet**: Gemini provider UI/tests + Ollama troubleshooting (v0.7.1, partially done), Agent Builder Studio (v0.8), framework adapters, teams/auth, hosted platform.

### EXACT v0.7.1 in-progress state (uncommitted working-tree changes)

DONE (uncommitted):

- `apps/api/app/model_gateway/providers/gemini.py` — full GeminiProvider (generateContent API, key as `?key=` query param, defensive usageMetadata parsing, models gemini-1.5-flash/1.5-pro/2.0-flash/2.5-flash, not_configured w/o key, complete/health_check, redact_key).
- `apps/api/app/config.py` — added `gemini_api_key` (AliasChoices GEMINI_API_KEY, GOOGLE_API_KEY, AGENTLAB_GEMINI_API_KEY) + `gemini_base_url`.
- `apps/api/app/model_gateway/registry.py` — registered GeminiProvider between anthropic and ollama.

STILL TODO for v0.7.1:

- `schemas.py` ProviderOut: add `message: str | None = None`.
- `routers/model_gateway.py` list_providers: populate `message=health.detail`.
- `providers/ollama.py` health_check: richer troubleshooting detail (mention OLLAMA_BASE_URL value + host.docker.internal for Docker).
- Version bumps to 0.7.1: `apps/api/app/main.py` API_VERSION, `apps/api/pyproject.toml`, `apps/web/package.json`, `apps/web/src/components/layout/Shell.tsx` ("v0.7.1 · local mode").
- `.env.example`: add GEMINI_API_KEY/GOOGLE_API_KEY + Ollama Docker host.docker.internal note.
- Backend tests (`apps/api/tests/test_model_gateway.py`): Gemini in registry, not_configured w/o key, configured w/ key, redacted, no key leak (extend planted-secret test to include Gemini), gemini test-call failure captured safely (use gemini_base_url → `http://127.0.0.1:9/...` for fast connection-refused), ollama unavailable helpful message.
- Frontend: `lib/types.ts` `Provider.message?: string`; `components/gateway/ModelGateway.tsx` render message hint (amber for unavailable/not_configured); `ModelGateway.test.tsx` add Gemini card + Ollama-unavailable-message tests (extend fixture with gemini + ollama-unavailable).
- Docs: README (Gemini in providers list + Ollama troubleshooting block: curl /api/tags, ollama serve, ollama pull llama3.2, Docker host.docker.internal), ARCHITECTURE, ROADMAP, PRODUCT_SPEC; mention Gemini key stays server-side, Agent Builder Studio remains v0.8.
- Run `make test` + `cd apps/web && npm test && npm run build`; live-verify provider cards (5 now: Mock/OpenAI/Anthropic/Gemini/Ollama) + key-leak grep; commit; final report.

## 7. Next planned work

1. **FIRST — finish v0.7.1 Model Gateway patch** (above TODO list). Do NOT start Agent Builder Studio until this is committed and green.
2. **THEN — v0.8 Agent Builder Studio** (only after explicit approval): visual workflow builder; create agents; assign provider/model per agent (built on the gateway); connect agents; run workflow; emit normal AgentLab telemetry (reuse `model.`/`agent.`/`message.*` events so graph/replay/cost/trust all work for free); show replay/cost/failure attribution. No SaaS/auth/billing/templates/cloud-secrets.

## 8. Critical product direction

The arc: turn AgentLab from an observability tool into "a full multi-agent development studio where users connect OpenAI/Claude/Gemini/Ollama, build workflows, run them, and visually see which agent failed, which used the most tokens, which cost the most, and what happened step by step." Every layer so far (gateway, cost, trust, replay) is the substrate for the v0.8 studio. Keep the "instrument → collect → visualize → inspect → replay → test → attribute" loop intact; the studio just adds authoring on top.

## 9. Rules for the next assistant

- Keep versions disciplined; one version at a time; always end each version with a final report and the approval question, then STOP.
- Do NOT build SaaS/auth/RBAC/billing/Slack-alerts/cloud-secret-storage/policy-engine yet.
- Do NOT skip v0.7.1 — finish Gemini + Ollama patching first.
- Do NOT start Agent Builder Studio until the Model Gateway is stable & committed.
- Keep the mock provider working without any keys; never expose/store/log API keys (redacted only); keep `.env` gitignored.
- Keep ALL tests passing (run `make test` + `npm test` + `npm run build` before every commit); maintain Python↔JS mirror parity (scoring.py↔scoring.ts, costing.py↔costing.ts, replay fold).
- Single-source-of-truth discipline: derive on read; don't duplicate aggregation logic.
- Verify live in browser preview with real screenshots before claiming done; never assert without evidence.
- Commit style: `feat(scope):`/`docs(vX):` with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Branch `main`.
- Project memory lives at `/Users/aryannagwekar/.claude/projects/-Users-aryannagwekar-public1/memory/agentlab-project.md` (update phase status there).

## 10. Exact next prompt to paste into a new chat

> Continue the AgentLab project at /Users/aryannagwekar/public1/agentlab (branch main). Read /Users/aryannagwekar/.claude/projects/-Users-aryannagwekar-public1/memory/agentlab-project.md and ARCHITECTURE.md first.
>
> Finish v0.7.1 Model Gateway patch (do NOT start v0.8 Agent Builder Studio yet). v0.7 is fully committed (HEAD 419e144, 130 pytest + 42 vitest green). v0.7.1 is partially done in the working tree, uncommitted: model_gateway/providers/gemini.py (GeminiProvider) exists, config.py has gemini_api_key/gemini_base_url, and registry.py registers Gemini. Run git status and make test to confirm the starting point.
>
> Complete v0.7.1:
> - schemas.py ProviderOut: add message: str | None; routers/model_gateway.py list_providers: set message=health.detail.
> - providers/ollama.py health_check: richer troubleshooting message (include the OLLAMA_BASE_URL value and a host.docker.internal:11434 hint for Docker users).
> - Bump versions to 0.7.1: app/main.py API_VERSION, apps/api/pyproject.toml, apps/web/package.json, Shell.tsx.
> - .env.example: add GEMINI_API_KEY/GOOGLE_API_KEY + Ollama Docker host.docker.internal note.
> - Backend tests (test_model_gateway.py): Gemini registry/not-configured/configured/redacted/no-key-leak (extend the planted-fake-key grep test to include a fake GEMINI_API_KEY), Gemini test-call failure captured safely (point gemini_base_url at http://127.0.0.1:9/... for a fast connection-refused), Ollama unavailable returns the helpful message. Keep all existing v0.7 tests green.
> - Frontend: types.ts Provider.message?; ModelGateway.tsx render the troubleshooting hint (amber for unavailable/not_configured) and show OLLAMA_BASE_URL; ModelGateway.test.tsx add Gemini-card + Ollama-unavailable-message tests; never show a raw key.
> - Docs (README/ARCHITECTURE/ROADMAP/PRODUCT_SPEC): Gemini added in v0.7.1 (key server-side, redacted), Ollama troubleshooting (curl localhost:11434/api/tags, ollama serve, ollama pull llama3.2, Docker host.docker.internal), keys still never stored in DB, Agent Builder Studio remains v0.8.
> - Run make test + cd apps/web && npm test && npm run build; verify live that 5 provider cards render (Mock/OpenAI/Anthropic/Gemini/Ollama) with redacted keys and a key-leak grep finds nothing; regenerate the model-gateway screenshot; commit.
>
> Security rules: keys env-only, never stored/returned/logged/committed; redacted in UI; mock provider works without keys. Discipline: keep all tests passing, derive-on-read single source of truth, maintain Python↔JS mirror parity, verify live with screenshots.
>
> When v0.7.1 is complete, stop and give the final report (files changed, commits, tests, Gemini status, Ollama troubleshooting improvement, security guarantees, demoability) and ask: "Do you approve AgentLab v0.7.1 Model Gateway patch so I can continue to v0.8 Agent Builder Studio?"
