import { clsx } from "clsx";

import type { WorkspaceAgentStatus } from "../../lib/types";
import { Badge } from "../ui";

export const AGENT_STATUS_STYLE: Record<WorkspaceAgentStatus, string> = {
  ready: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  running: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  caution: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  suspicious: "border-orange-400/40 bg-orange-400/10 text-orange-300",
  quarantined: "border-red-400/40 bg-red-400/10 text-red-300",
  disabled: "border-zinc-600/30 bg-zinc-700/20 text-zinc-500",
};

export function AgentStatusBadge({
  status,
  className,
}: {
  status: WorkspaceAgentStatus;
  className?: string;
}) {
  return <Badge className={clsx(AGENT_STATUS_STYLE[status], className)}>{status}</Badge>;
}
