/**
 * Pins the JS scoring mirror (lib/scoring.ts) to the Python engine
 * (apps/api/app/scoring.py + apps/api/tests/test_scoring.py).
 */
import { describe, expect, it } from "vitest";

import { scoreEvents, scoreTier } from "./scoring";
import type { AgentLabEvent } from "./types";

let n = 0;
function ev(
  eventType: string,
  opts: { source?: string | null; target?: string | null; payload?: Record<string, unknown> } = {},
): AgentLabEvent {
  n += 1;
  return {
    id: n,
    event_id: `e${n}`,
    event_type: eventType,
    timestamp: new Date(Date.UTC(2026, 5, 10, 0, 0, 0, n)).toISOString(),
    project_id: "p",
    run_id: "r",
    source_agent_id: opts.source ?? null,
    target_agent_id: opts.target ?? null,
    payload: opts.payload ?? {},
    metadata: {},
  };
}

const score = (events: AgentLabEvent[], id: string) =>
  scoreEvents(events).get(id) ?? { trust: 1, risk: 0 };

describe("scoreEvents (mirror of app/scoring.py)", () => {
  it("defaults to trust 1 / risk 0", () => {
    expect(score([ev("agent.started", { source: "a" })], "a")).toEqual({ trust: 1, risk: 0 });
  });

  it("agent.failed reduces trust, raises risk", () => {
    expect(score([ev("agent.failed", { source: "a" })], "a")).toEqual({ trust: 0.85, risk: 0.1 });
  });

  it("message.flagged raises risk strongly", () => {
    expect(score([ev("message.flagged", { source: "a", target: "b" })], "a")).toEqual({
      trust: 0.8,
      risk: 0.25,
    });
  });

  it("attack.injected scores the target, not lab-controller", () => {
    const scores = scoreEvents([
      ev("attack.injected", { source: "lab-controller", target: "mal", payload: { attack_type: "x" } }),
    ]);
    expect(scores.has("lab-controller")).toBe(false);
    expect(scores.get("mal")).toEqual({ trust: 0.75, risk: 0.3 });
  });

  it("fault.injected scores the victim (target)", () => {
    expect(score([ev("fault.injected", { source: "lab", target: "v" })], "v")).toEqual({
      trust: 0.95,
      risk: 0.1,
    });
  });

  it("suspicious sets the trust ceiling and risk floor", () => {
    const s = score([ev("agent.suspicious", { source: "a" })], "a");
    expect(s.trust).toBeLessThanOrEqual(0.5);
    expect(s.risk).toBeGreaterThanOrEqual(0.6);
  });

  it("quarantine lands trust 0.1-0.2 and risk >= 0.9 (the headline fix)", () => {
    const sequence = [
      ev("agent.joined", { source: "mal", payload: { status: "suspicious" } }),
      ev("attack.injected", { source: "lab", target: "mal", payload: { attack_type: "fake" } }),
      ev("message.flagged", { source: "mal", target: "planner" }),
      ev("attack.injected", { source: "lab", target: "mal", payload: { attack_type: "exfil" } }),
      ev("agent.quarantined", { source: "mal" }),
    ];
    const s = score(sequence, "mal");
    expect(s.trust).toBeGreaterThanOrEqual(0.1);
    expect(s.trust).toBeLessThanOrEqual(0.25);
    expect(s.trust).not.toBe(1); // never trust 1.0 when quarantined
    expect(s.risk).toBeGreaterThanOrEqual(0.9);
    expect(scoreTier(s.trust, s.risk)).toBe("high-risk");
  });

  it("evolves per cursor (replay reproducibility)", () => {
    const seq = [
      ev("agent.started", { source: "a" }),
      ev("agent.failed", { source: "a" }),
      ev("message.flagged", { source: "a", target: "b" }),
    ];
    expect(score(seq.slice(0, 1), "a").trust).toBe(1);
    expect(score(seq.slice(0, 2), "a").trust).toBe(0.85);
    expect(score(seq.slice(0, 3), "a").trust).toBe(0.65);
  });

  it("clamps to [0,1]", () => {
    const many = Array.from({ length: 20 }, () => ev("agent.failed", { source: "a" }));
    expect(score(many, "a")).toEqual({ trust: 0, risk: 1 });
  });

  it("trust.updated is a manual override", () => {
    expect(score([ev("trust.updated", { source: "a", payload: { trust_score: 0.42 } })], "a").trust).toBe(
      0.42,
    );
  });
});

describe("scoreTier", () => {
  it("bands by trust and risk", () => {
    expect(scoreTier(1, 0)).toBe("trusted");
    expect(scoreTier(0.7, 0.1)).toBe("caution");
    expect(scoreTier(0.45, 0.65)).toBe("suspicious");
    expect(scoreTier(0.1, 0.95)).toBe("high-risk");
  });
});
