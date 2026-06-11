import { Link } from "react-router-dom";

import { tierStyle } from "../../lib/scoring";
import type { RiskSummaryAgent, RunRiskSummary } from "../../lib/types";
import { Card } from "../ui";

export function RiskSummaryView({
  summary,
  projectId,
}: {
  summary: RunRiskSummary;
  projectId?: string;
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryAgentCard label="Highest risk" agent={summary.highest_risk_agent} projectId={projectId} metric="risk" />
        <SummaryAgentCard label="Lowest trust" agent={summary.lowest_trust_agent} projectId={projectId} metric="trust" />
        <NumberCard label="Avg trust" value={summary.avg_trust} fmt={(v) => v.toFixed(2)} />
        <NumberCard label="Avg risk" value={summary.avg_risk} fmt={(v) => v.toFixed(2)} tone={(summary.avg_risk ?? 0) >= 0.3 ? "danger" : undefined} />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <CountCard label="Suspicious agents" value={summary.suspicious_agents} />
        <CountCard label="Quarantined" value={summary.quarantined_agents} danger={summary.quarantined_agents > 0} />
        <CountCard label="Flagged messages" value={summary.flagged_messages} danger={summary.flagged_messages > 0} />
        <CountCard label="Attack events" value={summary.attack_events} danger={summary.attack_events > 0} />
        <CountCard label="Fault events" value={summary.fault_events} danger={summary.fault_events > 0} />
      </div>
    </div>
  );
}

function SummaryAgentCard({
  label,
  agent,
  projectId,
  metric,
}: {
  label: string;
  agent: RiskSummaryAgent | null;
  projectId?: string;
  metric: "trust" | "risk";
}) {
  if (!agent) {
    return (
      <Card className="px-4 py-3">
        <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{label}</div>
        <div className="mt-1 text-[13px] text-zinc-600">—</div>
      </Card>
    );
  }
  const t = tierStyle(agent.trust_score, agent.risk_score);
  const value = metric === "risk" ? agent.risk_score : agent.trust_score;
  return (
    <Card className="px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{label}</div>
      <Link
        to={`/agents/${agent.agent_id}${projectId ? `?project=${projectId}` : ""}`}
        className="mt-1 block truncate text-[14px] font-semibold text-zinc-100 hover:text-indigo-300"
      >
        {agent.name ?? agent.agent_id}
      </Link>
      <div className="mt-1.5 flex items-center gap-2">
        <span className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-wider ${t.badge}`}>
          {t.label}
        </span>
        <span className="font-mono text-[12px] text-zinc-300">
          {metric} {value.toFixed(2)}
        </span>
      </div>
    </Card>
  );
}

function NumberCard({
  label,
  value,
  fmt,
  tone,
}: {
  label: string;
  value: number | null;
  fmt: (v: number) => string;
  tone?: "danger";
}) {
  return (
    <Card className="px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold ${tone === "danger" ? "text-red-300" : "text-zinc-100"}`}>
        {value === null ? "—" : fmt(value)}
      </div>
    </Card>
  );
}

function CountCard({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  return (
    <Card className="px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold ${danger ? "text-red-300" : "text-zinc-100"}`}>
        {value}
      </div>
    </Card>
  );
}
