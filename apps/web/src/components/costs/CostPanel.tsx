import { clsx } from "clsx";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import { fmtCost, fmtMs, fmtNum } from "../../lib/format";
import type { AgentCost, RunCost } from "../../lib/types";
import { Card, ErrorNote, SectionLabel, Spinner, Stat } from "../ui";

const PROVIDER_COLOR: Record<string, string> = {
  mock: "bg-violet-400",
  unknown: "bg-zinc-500",
};

export function CostPanel({ runId }: { runId: string }) {
  const { data, loading, error } = useFetch(() => api.runCosts(runId), [runId]);
  if (loading) return <Spinner label="Tallying tokens & cost…" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;
  return <CostPanelView cost={data} />;
}

export function CostPanelView({ cost }: { cost: RunCost }) {
  const nameOf = (id: string | null) =>
    id ? (cost.agent_breakdown.find((a) => a.agent_id === id)?.agent_name ?? id) : "—";

  const maxAgentCost = Math.max(0.000001, ...cost.agent_breakdown.map((a) => a.estimated_cost_usd));
  const maxAgentTokens = Math.max(1, ...cost.agent_breakdown.map((a) => a.total_tokens));
  const maxAgentLatency = Math.max(1, ...cost.agent_breakdown.map((a) => a.average_latency_ms ?? 0));
  const failedTotal = cost.agent_breakdown.reduce((s, a) => s + a.failed_model_calls, 0);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Stat label="Total tokens" value={fmtNum(cost.total_tokens)} />
        <Stat label="Input tokens" value={fmtNum(cost.total_input_tokens)} />
        <Stat label="Output tokens" value={fmtNum(cost.total_output_tokens)} />
        <Stat label="Estimated cost" value={fmtCost(cost.estimated_cost_usd)} tone="accent" />
        <Stat label="Most expensive" value={nameOf(cost.most_expensive_agent)} />
        <Stat label="Most token-heavy" value={nameOf(cost.most_token_heavy_agent)} />
        <Stat label="Slowest" value={nameOf(cost.slowest_agent)} />
        <Stat
          label="Failed model calls"
          value={failedTotal}
          tone={failedTotal > 0 ? "danger" : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RankBars
          title="Cost by agent"
          rows={cost.agent_breakdown}
          value={(a) => a.estimated_cost_usd}
          max={maxAgentCost}
          label={(a) => fmtCost(a.estimated_cost_usd)}
          color="bg-indigo-400"
        />
        <RankBars
          title="Tokens by agent"
          rows={cost.agent_breakdown}
          value={(a) => a.total_tokens}
          max={maxAgentTokens}
          label={(a) => fmtNum(a.total_tokens)}
          color="bg-violet-400"
        />
        <RankBars
          title="Latency by agent"
          rows={cost.agent_breakdown}
          value={(a) => a.average_latency_ms ?? 0}
          max={maxAgentLatency}
          label={(a) => fmtMs(a.average_latency_ms)}
          color="bg-sky-400"
        />
        <Card className="p-4">
          <SectionLabel>Model usage by provider</SectionLabel>
          <div className="space-y-2.5">
            {cost.model_breakdown.map((m) => (
              <div key={m.model_name} className="flex items-center gap-2">
                <span className={clsx("h-2 w-2 shrink-0 rounded-full", PROVIDER_COLOR[m.provider] ?? "bg-zinc-500")} />
                <span className="w-40 shrink-0 truncate font-mono text-[12px] text-zinc-300">{m.model_name}</span>
                <span className="flex-1 font-mono text-[11px] text-zinc-500">
                  {fmtNum(m.total_tokens)} tok · {m.call_count} call{m.call_count === 1 ? "" : "s"}
                  {m.failure_count > 0 ? ` · ${m.failure_count} failed` : ""}
                </span>
                <span className="font-mono text-[12px] text-zinc-200">{fmtCost(m.estimated_cost_usd)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-left text-[12.5px]">
          <thead>
            <tr className="border-b border-edge text-[10.5px] uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-2.5 font-medium">Agent</th>
              <th className="px-3 py-2.5 font-medium">Model</th>
              <th className="px-3 py-2.5 text-right font-medium">Input</th>
              <th className="px-3 py-2.5 text-right font-medium">Output</th>
              <th className="px-3 py-2.5 text-right font-medium">Total</th>
              <th className="px-3 py-2.5 text-right font-medium">Cost</th>
              <th className="px-3 py-2.5 text-right font-medium">Avg latency</th>
              <th className="px-3 py-2.5 text-right font-medium">Failed</th>
              <th className="px-4 py-2.5 text-right font-medium">Retries</th>
            </tr>
          </thead>
          <tbody>
            {cost.agent_breakdown.map((a) => (
              <tr key={a.agent_id} className="border-b border-edge/60 last:border-0">
                <td className="px-4 py-2 font-medium text-zinc-200">{a.agent_name ?? a.agent_id}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-zinc-400">{a.most_used_model ?? "—"}</td>
                <td className="px-3 py-2 text-right font-mono">{fmtNum(a.input_tokens)}</td>
                <td className="px-3 py-2 text-right font-mono">{fmtNum(a.output_tokens)}</td>
                <td className="px-3 py-2 text-right font-mono">{fmtNum(a.total_tokens)}</td>
                <td className="px-3 py-2 text-right font-mono text-indigo-300">{fmtCost(a.estimated_cost_usd)}</td>
                <td className="px-3 py-2 text-right font-mono">{fmtMs(a.average_latency_ms)}</td>
                <td className={clsx("px-3 py-2 text-right font-mono", a.failed_model_calls > 0 && "text-red-300")}>
                  {a.failed_model_calls}
                </td>
                <td className={clsx("px-4 py-2 text-right font-mono", a.retry_count > 0 && "text-amber-300")}>
                  {a.retry_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function RankBars({
  title,
  rows,
  value,
  max,
  label,
  color,
}: {
  title: string;
  rows: AgentCost[];
  value: (a: AgentCost) => number;
  max: number;
  label: (a: AgentCost) => string;
  color: string;
}) {
  const sorted = [...rows].sort((a, b) => value(b) - value(a));
  return (
    <Card className="p-4">
      <SectionLabel>{title}</SectionLabel>
      <div className="space-y-2">
        {sorted.map((a) => (
          <div key={a.agent_id} className="flex items-center gap-2">
            <span className="w-20 shrink-0 truncate text-[11px] text-zinc-400">{a.agent_name ?? a.agent_id}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-3">
              <div
                className={clsx("h-full rounded-full", color)}
                style={{ width: `${Math.max(2, (value(a) / max) * 100)}%` }}
              />
            </div>
            <span className="w-16 shrink-0 text-right font-mono text-[11px] text-zinc-300">{label(a)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
