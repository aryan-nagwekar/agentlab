import { useNavigate } from "react-router-dom";

import { fmtDate, runDuration } from "../lib/format";
import { runStatus } from "../lib/status";
import type { Run } from "../lib/types";
import { Card, StatusDot } from "./ui";

export function RunsTable({ runs, showProject }: { runs: Run[]; showProject?: boolean }) {
  const navigate = useNavigate();
  if (runs.length === 0) {
    return <div className="px-4 py-8 text-center text-sm text-zinc-600">No runs yet.</div>;
  }
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-left text-[12.5px]">
        <thead>
          <tr className="border-b border-edge text-[10.5px] uppercase tracking-wider text-zinc-500">
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-3 py-2.5 font-medium">Run</th>
            {showProject ? <th className="px-3 py-2.5 font-medium">Project</th> : null}
            <th className="px-3 py-2.5 font-medium">Started</th>
            <th className="px-3 py-2.5 text-right font-medium">Duration</th>
            <th className="px-3 py-2.5 text-right font-medium">Agents</th>
            <th className="px-3 py-2.5 text-right font-medium">Msgs</th>
            <th className="px-3 py-2.5 text-right font-medium">Events</th>
            <th className="px-4 py-2.5 text-right font-medium">Errors</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const status = runStatus(run.status);
            return (
              <tr
                key={run.id}
                onClick={() => navigate(`/runs/${run.id}`)}
                className="cursor-pointer border-b border-edge/60 transition-colors last:border-0 hover:bg-surface-2"
              >
                <td className="px-4 py-2.5">
                  <span className="flex items-center gap-2">
                    <StatusDot className={status.dot} pulse={run.status === "running"} />
                    <span className="text-zinc-400">{status.label}</span>
                  </span>
                </td>
                <td className="max-w-[320px] px-3 py-2.5">
                  <div className="truncate font-medium text-zinc-200">{run.name ?? run.id}</div>
                  <div className="truncate font-mono text-[10.5px] text-zinc-600">{run.id}</div>
                </td>
                {showProject ? (
                  <td className="px-3 py-2.5 font-mono text-[11px] text-zinc-500">
                    {run.project_id}
                  </td>
                ) : null}
                <td className="px-3 py-2.5 text-zinc-500">{fmtDate(run.started_at)}</td>
                <td className="px-3 py-2.5 text-right font-mono">{runDuration(run)}</td>
                <td className="px-3 py-2.5 text-right font-mono">{run.agent_count ?? "—"}</td>
                <td className="px-3 py-2.5 text-right font-mono">{run.message_count ?? "—"}</td>
                <td className="px-3 py-2.5 text-right font-mono">{run.event_count ?? "—"}</td>
                <td
                  className={`px-4 py-2.5 text-right font-mono ${
                    run.error_count > 0 ? "text-red-300" : "text-zinc-500"
                  }`}
                >
                  {run.error_count}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
