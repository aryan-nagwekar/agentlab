import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import { fmtCost, fmtMs, fmtNum, fmtPercent } from "../../lib/format";
import { tierStyle } from "../../lib/scoring";
import type { AgentLabEvent, RunMetrics } from "../../lib/types";
import { RiskSummaryView } from "../scoring/RiskSummary";
import { Badge, Card, SectionLabel, Stat, TrustBar } from "../ui";

const AXIS = { fill: "#71717a", fontSize: 11 } as const;
const TOOLTIP_STYLE = {
  backgroundColor: "#131318",
  border: "1px solid #2e2e38",
  borderRadius: 8,
  fontSize: 12,
  color: "#e4e4e7",
} as const;

const HIGHLIGHT_LABELS: Record<string, string> = {
  slowest_agent: "Slowest",
  most_expensive_agent: "Most expensive",
  most_active_agent: "Most active",
  most_unreliable_agent: "Most unreliable",
  highest_risk_agent: "Highest risk",
  lowest_trust_agent: "Lowest trust",
};

export function RunMetricsView({
  metrics,
  events,
  projectId,
  runId,
}: {
  metrics: RunMetrics;
  events: AgentLabEvent[];
  projectId?: string;
  runId?: string;
}) {
  const totals = metrics.totals;
  const riskSummary = useFetch(
    () => (runId ? api.runRiskSummary(runId) : Promise.resolve(null)),
    [runId],
  );

  const timeline = useMemo(() => {
    if (events.length === 0) return [];
    const buckets = new Map<string, number>();
    for (const event of events) {
      const key = event.timestamp.slice(11, 19); // HH:MM:SS
      buckets.set(key, (buckets.get(key) ?? 0) + 1);
    }
    return [...buckets.entries()].map(([time, count]) => ({ time, count }));
  }, [events]);

  const latencyData = metrics.per_agent
    .filter((row) => row.avg_latency_ms != null)
    .map((row) => ({ name: row.agent_id, latency: row.avg_latency_ms }));
  const tokenData = metrics.per_agent
    .filter((row) => row.tokens > 0)
    .map((row) => ({ name: row.agent_id, tokens: row.tokens }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="Agents" value={totals.agents} />
        <Stat label="Messages" value={totals.messages} />
        <Stat label="Tool calls" value={totals.tool_calls} />
        <Stat label="Model calls" value={totals.model_calls} />
        <Stat label="Events" value={fmtNum(totals.events)} />
        <Stat label="Tokens" value={fmtNum(totals.tokens)} />
        <Stat label="Est. cost" value={fmtCost(totals.cost_estimate)} />
        <Stat label="Avg op latency" value={fmtMs(totals.avg_latency_ms)} />
        <Stat label="P95 op latency" value={fmtMs(totals.p95_latency_ms)} />
        <Stat
          label="Errors"
          value={totals.error_count}
          tone={totals.error_count > 0 ? "danger" : undefined}
          hint={totals.error_count > 0 ? `${fmtPercent(totals.error_rate)} of events` : undefined}
        />
        {totals.attacks > 0 || totals.flagged_messages > 0 || totals.suspicious_agents > 0 ? (
          <>
            <Stat label="Attacks" value={totals.attacks} tone={totals.attacks > 0 ? "danger" : undefined} />
            <Stat
              label="Flagged msgs"
              value={totals.flagged_messages}
              tone={totals.flagged_messages > 0 ? "danger" : undefined}
            />
            <Stat
              label="Suspicious agents"
              value={totals.suspicious_agents}
              tone={totals.suspicious_agents > 0 ? "danger" : undefined}
            />
          </>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        {Object.entries(metrics.highlights).map(([key, highlight]) =>
          highlight ? (
            <Badge key={key} className="border-edge bg-surface-2 px-3 py-1 text-[12px] text-zinc-300">
              <span className="text-zinc-500">{HIGHLIGHT_LABELS[key] ?? key}:</span>
              <span className="font-medium text-zinc-100">{highlight.name}</span>
              <span className="font-mono text-zinc-400">
                {highlight.unit === "ms"
                  ? fmtMs(highlight.value)
                  : highlight.unit === "USD"
                    ? fmtCost(highlight.value)
                    : highlight.unit === "trust" || highlight.unit === "risk"
                      ? `${highlight.unit} ${highlight.value.toFixed(2)}`
                      : `${fmtNum(highlight.value)} ${highlight.unit}`}
              </span>
            </Badge>
          ) : null,
        )}
      </div>

      {riskSummary.data ? (
        <div>
          <SectionLabel>Trust &amp; risk summary</SectionLabel>
          <RiskSummaryView summary={riskSummary.data} projectId={projectId} />
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <SectionLabel>Avg task latency by agent</SectionLabel>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={latencyData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="#1f1f26" vertical={false} />
              <XAxis dataKey="name" tick={AXIS} axisLine={{ stroke: "#2e2e38" }} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(99,102,241,0.06)" }} />
              <Bar dataKey="latency" name="avg ms" fill="#818cf8" radius={[4, 4, 0, 0]} maxBarSize={42} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card className="p-4">
          <SectionLabel>Tokens by agent</SectionLabel>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={tokenData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="#1f1f26" vertical={false} />
              <XAxis dataKey="name" tick={AXIS} axisLine={{ stroke: "#2e2e38" }} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(167,139,250,0.06)" }} />
              <Bar dataKey="tokens" fill="#a78bfa" radius={[4, 4, 0, 0]} maxBarSize={42} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card className="p-4">
        <SectionLabel>Event volume over time</SectionLabel>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={timeline} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <defs>
              <linearGradient id="eventFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1f1f26" vertical={false} />
            <XAxis dataKey="time" tick={AXIS} axisLine={{ stroke: "#2e2e38" }} tickLine={false} />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Area type="monotone" dataKey="count" stroke="#34d399" fill="url(#eventFill)" strokeWidth={1.5} />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-left text-[12.5px]">
          <thead>
            <tr className="border-b border-edge text-[10.5px] uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-2.5 font-medium">Agent</th>
              <th className="px-3 py-2.5 font-medium">Role</th>
              <th className="px-3 py-2.5 text-right font-medium">Msgs</th>
              <th className="px-3 py-2.5 text-right font-medium">Tools</th>
              <th className="px-3 py-2.5 text-right font-medium">Models</th>
              <th className="px-3 py-2.5 text-right font-medium">Tokens</th>
              <th className="px-3 py-2.5 text-right font-medium">Cost</th>
              <th className="px-3 py-2.5 text-right font-medium">Avg task</th>
              <th className="px-3 py-2.5 text-right font-medium">Errors</th>
              <th className="px-4 py-2.5 font-medium">Trust</th>
              <th className="px-4 py-2.5 font-medium">Tier</th>
            </tr>
          </thead>
          <tbody>
            {metrics.per_agent.map((row) => {
              const t = tierStyle(row.trust_score, row.risk_score);
              return (
                <tr key={row.agent_id} className="border-b border-edge/60 last:border-0">
                  <td className="px-4 py-2 font-medium text-zinc-200">{row.name}</td>
                  <td className="px-3 py-2 text-zinc-500">{row.role ?? "—"}</td>
                  <td className="px-3 py-2 text-right font-mono">{row.messages}</td>
                  <td className="px-3 py-2 text-right font-mono">{row.tool_calls}</td>
                  <td className="px-3 py-2 text-right font-mono">{row.model_calls}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtNum(row.tokens)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtCost(row.cost_estimate)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtMs(row.avg_latency_ms)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${row.errors > 0 ? "text-red-300" : ""}`}>
                    {row.errors}
                  </td>
                  <td className="px-4 py-2">
                    <TrustBar value={row.trust_score} compact />
                  </td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full border px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-wider ${t.badge}`}>
                      {t.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
