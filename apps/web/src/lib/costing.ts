/**
 * Cost & token attribution — a port of app/costing.py + app/pricing.py.
 *
 * The live Cost & Tokens tab fetches from the API; replay folds the run's
 * events client-side so cost/tokens evolve with the cursor. Both sides share
 * this pricing table and the same normalization, pinned by tests.
 */
import type { AgentLabEvent } from "./types";

export const MODEL_PRICING: Record<string, { input_per_1m: number; output_per_1m: number }> = {
  "mock:gpt-4.1": { input_per_1m: 2.0, output_per_1m: 8.0 },
  "mock:claude-sonnet": { input_per_1m: 3.0, output_per_1m: 15.0 },
  "mock:gemini-pro": { input_per_1m: 1.25, output_per_1m: 5.0 },
  "mock:local-ollama": { input_per_1m: 0.0, output_per_1m: 0.0 },
};

const round6 = (x: number) => Math.round(x * 1e6) / 1e6;

export function providerOf(modelName: string | null | undefined): string {
  if (!modelName) return "unknown";
  return modelName.includes(":") ? modelName.split(":", 1)[0] : "unknown";
}

export function estimateCost(
  modelName: string | null | undefined,
  inputTokens: number,
  outputTokens: number,
): { cost: number | null; status: "ok" | "unknown" } {
  if (!modelName || !(modelName in MODEL_PRICING)) return { cost: null, status: "unknown" };
  const rates = MODEL_PRICING[modelName];
  const cost = ((inputTokens || 0) * rates.input_per_1m + (outputTokens || 0) * rates.output_per_1m) / 1e6;
  return { cost: round6(cost), status: "ok" };
}

function num(value: unknown, fallback = 0): number {
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isFinite(n) ? n : fallback;
}

export interface ModelCall {
  agentId: string | null;
  provider: string;
  modelName: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  estimatedCostUsd: number | null;
  pricingStatus: string;
  latencyMs: number | null;
  status: "completed" | "failed";
  errorMessage: string | null;
}

export function normalizeModelEvent(event: AgentLabEvent): ModelCall {
  const p = event.payload as Record<string, unknown>;
  const modelName = String(p.model_name ?? p.model ?? "unknown");
  const provider = String(p.provider ?? providerOf(modelName));
  const inputTokens = num(p.input_tokens ?? p.prompt_tokens ?? 0);
  const outputTokens = num(p.output_tokens ?? p.completion_tokens ?? 0);
  const totalTokens = num(p.total_tokens) || inputTokens + outputTokens;
  const status = event.event_type === "model.failed" ? "failed" : "completed";

  let { cost, status: pricingStatus } = estimateCost(modelName, inputTokens, outputTokens) as {
    cost: number | null;
    status: string;
  };
  if (cost === null) {
    const provided = p.estimated_cost_usd ?? p.cost_estimate;
    if (provided !== undefined && provided !== null) {
      cost = round6(num(provided));
      pricingStatus = "provided";
    }
  }
  return {
    agentId: event.source_agent_id,
    provider,
    modelName,
    inputTokens,
    outputTokens,
    totalTokens,
    estimatedCostUsd: cost,
    pricingStatus,
    latencyMs: p.latency_ms !== undefined ? num(p.latency_ms) : null,
    status,
    errorMessage: status === "failed" ? String(p.error ?? p.error_message ?? "") : null,
  };
}

export interface RunCostTotals {
  totalTokens: number;
  totalInputTokens: number;
  totalOutputTokens: number;
  estimatedCostUsd: number;
  byAgent: Map<string, { tokens: number; cost: number }>;
}

/** Fold model.* events into cost/token totals (for replay evolution). */
export function aggregateCost(events: AgentLabEvent[]): RunCostTotals {
  const totals: RunCostTotals = {
    totalTokens: 0,
    totalInputTokens: 0,
    totalOutputTokens: 0,
    estimatedCostUsd: 0,
    byAgent: new Map(),
  };
  for (const event of events) {
    if (event.event_type !== "model.completed" && event.event_type !== "model.failed") continue;
    const call = normalizeModelEvent(event);
    totals.totalTokens += call.totalTokens;
    totals.totalInputTokens += call.inputTokens;
    totals.totalOutputTokens += call.outputTokens;
    const cost = call.estimatedCostUsd ?? 0;
    totals.estimatedCostUsd = round6(totals.estimatedCostUsd + cost);
    const key = call.agentId ?? "unknown";
    const agent = totals.byAgent.get(key) ?? { tokens: 0, cost: 0 };
    agent.tokens += call.totalTokens;
    agent.cost = round6(agent.cost + cost);
    totals.byAgent.set(key, agent);
  }
  return totals;
}

export function isModelEvent(eventType: string): boolean {
  return eventType.startsWith("model.");
}
