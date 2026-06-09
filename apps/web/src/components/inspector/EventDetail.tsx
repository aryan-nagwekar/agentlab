import { clsx } from "clsx";
import { useState } from "react";

import { fmtClock, fmtMs } from "../../lib/format";
import { FAMILY_STYLES, eventFamily, eventSummary, isFailureEvent } from "../../lib/status";
import type { AgentLabEvent } from "../../lib/types";
import { JsonView, RawJson } from "../JsonView";
import { Badge, CopyButton, SectionLabel } from "../ui";

interface EventDetailProps {
  event: AgentLabEvent;
  allEvents: AgentLabEvent[];
  onSelectEvent: (event: AgentLabEvent) => void;
}

export function EventDetail({ event, allEvents, onSelectEvent }: EventDetailProps) {
  const [tab, setTab] = useState<"summary" | "raw">("summary");
  const family = FAMILY_STYLES[eventFamily(event.event_type)];
  const failed = isFailureEvent(event.event_type);

  const parentId = event.metadata.parent_event_id as string | undefined;
  const parent = parentId ? allEvents.find((e) => e.event_id === parentId) : undefined;
  const children = allEvents.filter((e) => e.metadata.parent_event_id === event.event_id);
  const latency = (event.payload as Record<string, unknown>).latency_ms;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-edge px-4 py-3">
        <div className="flex items-center gap-2">
          <Badge className={failed ? "border-red-400/40 bg-red-400/10 text-red-300" : family.badge}>
            {event.event_type}
          </Badge>
          <span className="font-mono text-[11px] text-zinc-500">{fmtClock(event.timestamp)}</span>
        </div>
        <div className="mt-2 text-[13px] text-zinc-200">{eventSummary(event)}</div>
        {(event.source_agent_id || event.target_agent_id) && (
          <div className="mt-1.5 font-mono text-[11px] text-zinc-400">
            {event.source_agent_id ?? "—"}
            {event.target_agent_id ? (
              <span className="text-zinc-600"> → {event.target_agent_id}</span>
            ) : null}
          </div>
        )}
      </div>

      <div className="flex gap-1 border-b border-edge px-3 pt-2">
        {(["summary", "raw"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={clsx(
              "rounded-t-md px-3 py-1.5 text-[12px] font-medium transition-colors",
              tab === key
                ? "border border-b-0 border-edge bg-surface-2 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300",
            )}
          >
            {key === "summary" ? "Summary" : "Raw JSON"}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {tab === "summary" ? (
          <>
            <div className="grid grid-cols-2 gap-2 text-[12px]">
              <Field label="event id" value={event.event_id} mono />
              <Field label="run" value={event.run_id} mono />
              {typeof latency === "number" ? (
                <Field label="latency" value={fmtMs(latency)} mono />
              ) : null}
              {typeof event.metadata.message_id === "string" ? (
                <Field label="message id" value={event.metadata.message_id} mono />
              ) : null}
              {typeof event.metadata.tool_call_id === "string" ? (
                <Field label="tool call" value={event.metadata.tool_call_id} mono />
              ) : null}
              {typeof event.metadata.model_call_id === "string" ? (
                <Field label="model call" value={event.metadata.model_call_id} mono />
              ) : null}
            </div>

            <div>
              <SectionLabel>Payload</SectionLabel>
              <div className="rounded-lg border border-edge bg-surface-0 p-3 font-mono text-[11.5px]">
                <JsonView value={event.payload} />
              </div>
            </div>

            <div>
              <SectionLabel>Metadata</SectionLabel>
              <div className="rounded-lg border border-edge bg-surface-0 p-3 font-mono text-[11.5px]">
                <JsonView value={event.metadata} />
              </div>
            </div>

            {(parent || children.length > 0) && (
              <div>
                <SectionLabel>Related events</SectionLabel>
                <div className="space-y-1">
                  {parent ? (
                    <RelatedRow label="parent" event={parent} onClick={() => onSelectEvent(parent)} />
                  ) : null}
                  {children.slice(0, 12).map((child) => (
                    <RelatedRow
                      key={child.event_id}
                      label="child"
                      event={child}
                      onClick={() => onSelectEvent(child)}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div>
            <div className="mb-2 flex justify-end">
              <CopyButton text={JSON.stringify(event, null, 2)} />
            </div>
            <RawJson value={event} />
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0 rounded-md border border-edge bg-surface-2 px-2 py-1.5">
      <div className="text-[9.5px] uppercase tracking-wider text-zinc-600">{label}</div>
      <div className={clsx("truncate text-zinc-300", mono && "font-mono text-[11px]")}>{value}</div>
    </div>
  );
}

function RelatedRow({
  label,
  event,
  onClick,
}: {
  label: string;
  event: AgentLabEvent;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md border border-edge bg-surface-2 px-2 py-1.5 text-left transition-colors hover:border-edge-strong"
    >
      <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[9.5px] uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      <span className="truncate font-mono text-[11px] text-zinc-400">{event.event_type}</span>
      <span className="truncate text-[11px] text-zinc-500">{eventSummary(event)}</span>
    </button>
  );
}
