import { clsx } from "clsx";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import { factorLabel, tierStyle } from "../../lib/scoring";
import type { AgentScore, ScoreChange, ScoreFactor } from "../../lib/types";
import { SectionLabel, Spinner } from "../ui";

/** Trust/risk explanation for one agent: tier, latest reason, factors, history. */
export function ScorePanel({
  agentId,
  projectId,
  runId,
}: {
  agentId: string;
  projectId?: string;
  runId?: string;
}) {
  const { data, loading, error } = useFetch(
    () => api.agentScores(agentId, projectId, runId),
    [agentId, projectId, runId],
  );
  if (loading) return <Spinner label="Scoring…" />;
  if (error || !data) return <div className="px-1 py-2 text-[12px] text-zinc-600">No score data.</div>;
  return <ScorePanelView score={data} />;
}

export function ScorePanelView({ score }: { score: AgentScore }) {
  const t = tierStyle(score.trust_score, score.risk_score);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className={clsx("rounded-full border px-2 py-0.5 text-[11px] font-medium", t.badge)}>
          {t.label}
        </span>
        {score.latest_reason ? (
          <span className="truncate text-[12px] text-zinc-400" title={score.latest_reason}>
            {score.latest_reason}
          </span>
        ) : null}
      </div>

      <div className="space-y-2">
        <Meter label="Trust" value={score.trust_score} tone="trust" />
        <Meter label="Risk" value={score.risk_score} tone="risk" />
      </div>

      {score.risk_factors.length > 0 ? (
        <Factors title="Why risk rose" rows={score.risk_factors} metric="risk_delta" />
      ) : null}
      {score.trust_factors.length > 0 ? (
        <Factors title="Why trust changed" rows={score.trust_factors} metric="trust_delta" />
      ) : null}

      {score.history.length > 0 ? (
        <div>
          <SectionLabel>Score history</SectionLabel>
          <div className="space-y-1">
            {score.history
              .slice()
              .reverse()
              .map((change, index) => (
                <HistoryRow key={`${change.event_index}-${index}`} change={change} />
              ))}
          </div>
        </div>
      ) : (
        <div className="text-[12px] text-zinc-600">No score changes — this agent stayed nominal.</div>
      )}
    </div>
  );
}

function Meter({ label, value, tone }: { label: string; value: number; tone: "trust" | "risk" }) {
  const pct = Math.round(value * 100);
  const color =
    tone === "trust"
      ? value >= 0.8
        ? "bg-emerald-400"
        : value >= 0.5
          ? "bg-amber-400"
          : "bg-red-400"
      : value >= 0.6
        ? "bg-red-400"
        : value >= 0.3
          ? "bg-amber-400"
          : "bg-emerald-400";
  return (
    <div className="flex items-center gap-2">
      <span className="w-10 text-[10px] uppercase tracking-wider text-zinc-600">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
        <div className={clsx("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 text-right font-mono text-[11px] text-zinc-300">{value.toFixed(2)}</span>
    </div>
  );
}

function Factors({ title, rows, metric }: { title: string; rows: ScoreFactor[]; metric: "trust_delta" | "risk_delta" }) {
  return (
    <div>
      <SectionLabel>{title}</SectionLabel>
      <div className="space-y-1">
        {rows.slice(0, 5).map((row) => {
          const delta = row[metric];
          const positive = delta > 0;
          return (
            <div
              key={row.event_type}
              className="flex items-center gap-2 rounded-md border border-edge bg-surface-2 px-2 py-1 text-[11px]"
            >
              <span className="flex-1 truncate text-zinc-300">{factorLabel(row.event_type)}</span>
              <span className="font-mono text-zinc-600">×{row.count}</span>
              <span
                className={clsx(
                  "w-12 text-right font-mono",
                  metric === "risk_delta"
                    ? positive
                      ? "text-red-300"
                      : "text-emerald-300"
                    : positive
                      ? "text-emerald-300"
                      : "text-red-300",
                )}
              >
                {positive ? "+" : ""}
                {delta.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HistoryRow({ change }: { change: ScoreChange }) {
  const trustDown = change.trust_delta < 0;
  const riskUp = change.risk_delta > 0;
  return (
    <div className="rounded-md border border-edge bg-surface-2 px-2.5 py-1.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-zinc-500">#{change.event_index}</span>
        <span className="truncate font-mono text-[10.5px] text-zinc-400">
          {change.caused_by_event_type}
        </span>
        <span className="ml-auto flex gap-2 font-mono text-[10.5px]">
          {Math.abs(change.trust_delta) > 0 ? (
            <span className={trustDown ? "text-red-300" : "text-emerald-300"}>
              T {change.previous_trust.toFixed(2)}→{change.new_trust.toFixed(2)}
            </span>
          ) : null}
          {Math.abs(change.risk_delta) > 0 ? (
            <span className={riskUp ? "text-red-300" : "text-emerald-300"}>
              R {change.previous_risk.toFixed(2)}→{change.new_risk.toFixed(2)}
            </span>
          ) : null}
        </span>
      </div>
      <div className="mt-0.5 truncate text-[11px] text-zinc-500">{change.reason}</div>
    </div>
  );
}
