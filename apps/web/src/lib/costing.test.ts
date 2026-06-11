/**
 * Pins the JS costing mirror (lib/costing.ts) to the Python engine
 * (apps/api/app/costing.py + pricing.py).
 */
import { describe, expect, it } from "vitest";

import { aggregateCost, estimateCost, normalizeModelEvent } from "./costing";
import type { AgentLabEvent } from "./types";

let n = 0;
function modelEvent(
  type: "model.completed" | "model.failed",
  source: string,
  payload: Record<string, unknown>,
): AgentLabEvent {
  n += 1;
  return {
    id: n,
    event_id: `e${n}`,
    event_type: type,
    timestamp: new Date(Date.UTC(2026, 5, 10, 0, 0, 0, n)).toISOString(),
    project_id: "p",
    run_id: "r",
    source_agent_id: source,
    target_agent_id: null,
    payload,
    metadata: {},
  };
}

describe("estimateCost (mirror of pricing.py)", () => {
  it("prices a known model", () => {
    expect(estimateCost("mock:claude-sonnet", 1000, 500)).toEqual({ cost: 0.0105, status: "ok" });
  });
  it("local model is free", () => {
    expect(estimateCost("mock:local-ollama", 5000, 5000)).toEqual({ cost: 0, status: "ok" });
  });
  it("unknown model has no price", () => {
    expect(estimateCost("real:gpt-9", 100, 100)).toEqual({ cost: null, status: "unknown" });
  });
});

describe("normalizeModelEvent", () => {
  it("reads new fields", () => {
    const c = normalizeModelEvent(
      modelEvent("model.completed", "coder", {
        model_name: "mock:claude-sonnet",
        input_tokens: 1000,
        output_tokens: 500,
      }),
    );
    expect(c.estimatedCostUsd).toBe(0.0105);
    expect(c.pricingStatus).toBe("ok");
  });
  it("reads legacy fields", () => {
    const c = normalizeModelEvent(
      modelEvent("model.completed", "a", { model: "mock:gpt-4.1", prompt_tokens: 900, completion_tokens: 260 }),
    );
    expect(c.inputTokens).toBe(900);
    expect(c.totalTokens).toBe(1160);
    expect(c.provider).toBe("mock");
  });
  it("handles missing tokens", () => {
    const c = normalizeModelEvent(modelEvent("model.completed", "a", { model: "mock:gpt-4.1" }));
    expect(c.totalTokens).toBe(0);
    expect(c.estimatedCostUsd).toBe(0);
  });
  it("unknown pricing renders gracefully", () => {
    const c = normalizeModelEvent(modelEvent("model.completed", "a", { model: "custom-llm", total_tokens: 100 }));
    expect(c.estimatedCostUsd).toBeNull();
    expect(c.pricingStatus).toBe("unknown");
  });
});

describe("aggregateCost (replay cost fold)", () => {
  const events = [
    modelEvent("model.completed", "coder", { model_name: "mock:claude-sonnet", input_tokens: 1100, output_tokens: 600 }),
    modelEvent("model.completed", "researcher", { model_name: "mock:gpt-4.1", input_tokens: 2400, output_tokens: 300 }),
    modelEvent("model.failed", "security", { model_name: "mock:local-ollama", input_tokens: 650, output_tokens: 0 }),
  ];

  it("totals tokens and cost", () => {
    const c = aggregateCost(events);
    expect(c.totalTokens).toBe(1700 + 2700 + 650);
    expect(c.estimatedCostUsd).toBe(0.0123 + 0.0072); // 0.0195, ollama free
    expect(c.byAgent.get("coder")!.cost).toBe(0.0123);
  });

  it("folds by replay cursor", () => {
    const partial = aggregateCost(events.slice(0, 1));
    const full = aggregateCost(events);
    expect(partial.estimatedCostUsd).toBe(0.0123);
    expect(partial.totalTokens).toBe(1700);
    expect(full.estimatedCostUsd).toBeGreaterThan(partial.estimatedCostUsd);
  });

  it("ignores non-model events", () => {
    const withNoise: AgentLabEvent[] = [
      ...events,
      { ...events[0], event_id: "x", event_type: "message.sent" },
    ];
    expect(aggregateCost(withNoise).totalTokens).toBe(aggregateCost(events).totalTokens);
  });
});
