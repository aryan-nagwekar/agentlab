import { clsx } from "clsx";

import type { WorkspaceStatus } from "../../lib/types";
import { Badge } from "../ui";

export const STATUS_STYLE: Record<WorkspaceStatus, string> = {
  draft: "border-zinc-600/30 bg-zinc-600/10 text-zinc-400",
  active: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  paused: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  completed: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  archived: "border-zinc-600/30 bg-zinc-700/20 text-zinc-500",
  failed: "border-red-400/40 bg-red-400/10 text-red-300",
};

export function WorkspaceStatusBadge({
  status,
  className,
}: {
  status: WorkspaceStatus;
  className?: string;
}) {
  return <Badge className={clsx(STATUS_STYLE[status], className)}>{status}</Badge>;
}
