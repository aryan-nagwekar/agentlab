/**
 * Trust/risk scoring — a faithful port of app/scoring.py.
 *
 * The live topology gets scores straight from the API (the /graph endpoint runs
 * the Python engine). Replay folds events client-side, so it reuses this mirror
 * to evolve trust/risk as the cursor advances. The two implementations are
 * pinned to the same rules by tests on both sides.
 */
import type { AgentLabEvent } from "./types";

export const DEFAULT_TRUST = 1.0;
export const DEFAULT_RISK = 0.0;

interface Effect {
  trustDelta?: number;
  riskDelta?: number;
  trustCeil?: number;
  trustFloor?: number;
  riskFloor?: number;
}

const SUSPICIOUS: Effect = { trustCeil: 0.5, riskFloor: 0.6 };
const QUARANTINE: Effect = { trustCeil: 0.2, trustFloor: 0.1, riskFloor: 0.9 };

const EFFECTS: Record<string, Effect> = {
  "agent.completed": { trustDelta: 0.05, riskDelta: -0.02 },
  "tool.completed": { trustDelta: 0.01 },
  "model.completed": { trustDelta: 0.01 },
  "message.received": { trustDelta: 0.01 },
  "agent.failed": { trustDelta: -0.15, riskDelta: 0.1 },
  "tool.failed": { trustDelta: -0.1, riskDelta: 0.08 },
  "model.failed": { trustDelta: -0.1, riskDelta: 0.08 },
  "message.failed": { trustDelta: -0.07, riskDelta: 0.05 },
  "fault.injected": { trustDelta: -0.05, riskDelta: 0.1 },
  "message.flagged": { trustDelta: -0.2, riskDelta: 0.25 },
  "agent.suspicious": SUSPICIOUS,
  "attack.injected": { trustDelta: -0.25, riskDelta: 0.3 },
  "agent.quarantined": QUARANTINE,
};

const clamp = (x: number) => Math.max(0, Math.min(1, x));
const round4 = (x: number) => Math.round(x * 1e4) / 1e4;

export function scoreSubject(event: AgentLabEvent): string | null {
  if (event.event_type === "attack.injected" || event.event_type === "fault.injected") {
    return event.target_agent_id;
  }
  return event.source_agent_id;
}

function effectFor(event: AgentLabEvent): Effect | null {
  if (event.event_type === "agent.joined") {
    const status = (event.payload as Record<string, unknown>).status;
    if (status === "quarantined") return QUARANTINE;
    if (status === "suspicious") return SUSPICIOUS;
    return null;
  }
  return EFFECTS[event.event_type] ?? null;
}

export interface AgentScore {
  trust: number;
  risk: number;
}

function applyEffect(score: AgentScore, effect: Effect): AgentScore {
  let trust = clamp(score.trust + (effect.trustDelta ?? 0));
  let risk = clamp(score.risk + (effect.riskDelta ?? 0));
  if (effect.trustCeil !== undefined) trust = Math.min(trust, effect.trustCeil);
  if (effect.trustFloor !== undefined) trust = Math.max(trust, effect.trustFloor);
  if (effect.riskFloor !== undefined) risk = Math.max(risk, effect.riskFloor);
  return { trust: round4(trust), risk: round4(risk) };
}

/** Fold an ordered event slice into per-agent scores. */
export function scoreEvents(events: AgentLabEvent[]): Map<string, AgentScore> {
  const scores = new Map<string, AgentScore>();
  for (const event of events) {
    const subject = scoreSubject(event);
    if (!subject) continue;
    const current = scores.get(subject) ?? { trust: DEFAULT_TRUST, risk: DEFAULT_RISK };
    const payload = event.payload as Record<string, unknown>;
    if (event.event_type === "trust.updated") {
      const v = payload.trust_score;
      if (typeof v === "number") scores.set(subject, { ...current, trust: round4(clamp(v)) });
      else scores.set(subject, current);
      continue;
    }
    if (event.event_type === "risk.updated") {
      const v = payload.risk_score;
      if (typeof v === "number") scores.set(subject, { ...current, risk: round4(clamp(v)) });
      else scores.set(subject, current);
      continue;
    }
    const effect = effectFor(event);
    scores.set(subject, effect ? applyEffect(current, effect) : current);
  }
  return scores;
}

// ----------------------------------------------------------------- tiers / UI

export type Tier = "trusted" | "caution" | "suspicious" | "high-risk";

export function scoreTier(trust: number, risk: number): Tier {
  if (trust <= 0.2 || risk >= 0.9) return "high-risk";
  if (trust < 0.5 || risk >= 0.6) return "suspicious";
  if (trust < 0.8 || risk >= 0.3) return "caution";
  return "trusted";
}

export interface TierStyle {
  label: string;
  text: string;
  badge: string;
  bar: string;
}

export const TIER_STYLES: Record<Tier, TierStyle> = {
  trusted: {
    label: "Trusted",
    text: "text-emerald-300",
    badge: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    bar: "bg-emerald-400",
  },
  caution: {
    label: "Caution",
    text: "text-amber-300",
    badge: "border-amber-400/30 bg-amber-400/10 text-amber-300",
    bar: "bg-amber-400",
  },
  suspicious: {
    label: "Suspicious",
    text: "text-orange-300",
    badge: "border-orange-400/30 bg-orange-400/10 text-orange-300",
    bar: "bg-orange-400",
  },
  "high-risk": {
    label: "High risk",
    text: "text-red-300",
    badge: "border-red-400/30 bg-red-400/10 text-red-300",
    bar: "bg-red-400",
  },
};

export function tierStyle(trust: number, risk: number): TierStyle {
  return TIER_STYLES[scoreTier(trust, risk)];
}

export function factorLabel(eventType: string): string {
  return (
    {
      "agent.completed": "Completed tasks",
      "agent.failed": "Task failures",
      "tool.failed": "Tool failures",
      "model.failed": "Model failures",
      "message.failed": "Message failures",
      "message.flagged": "Flagged messages",
      "agent.suspicious": "Flagged suspicious",
      "agent.quarantined": "Quarantined",
      "attack.injected": "Simulated attacks",
      "fault.injected": "Injected faults",
      "agent.joined": "Unverified join",
      "trust.updated": "Manual trust override",
      "risk.updated": "Manual risk override",
    }[eventType] ?? eventType
  );
}
