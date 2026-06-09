import { clsx } from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";

import { fmtClock, fmtMs } from "../../lib/format";
import {
  FAMILY_STYLES,
  eventFamily,
  eventSummary,
  isFailureEvent,
  type EventFamily,
} from "../../lib/status";
import type { AgentLabEvent } from "../../lib/types";

const FAMILY_ORDER: EventFamily[] = [
  "run",
  "agent",
  "message",
  "tool",
  "model",
  "routing",
  "trust",
  "lab",
];

interface EventTimelineProps {
  events: AgentLabEvent[];
  selectedEventId: string | null;
  onSelect: (event: AgentLabEvent) => void;
  followLive?: boolean;
  maxHeightClass?: string;
}

export function EventTimeline({
  events,
  selectedEventId,
  onSelect,
  followLive = false,
  maxHeightClass = "max-h-[540px]",
}: EventTimelineProps) {
  const [activeFamilies, setActiveFamilies] = useState<Set<EventFamily>>(new Set());
  const listRef = useRef<HTMLDivElement>(null);

  const counts = useMemo(() => {
    const tally = new Map<EventFamily, number>();
    for (const event of events) {
      const family = eventFamily(event.event_type);
      tally.set(family, (tally.get(family) ?? 0) + 1);
    }
    return tally;
  }, [events]);

  const filtered = useMemo(
    () =>
      activeFamilies.size === 0
        ? events
        : events.filter((event) => activeFamilies.has(eventFamily(event.event_type))),
    [events, activeFamilies],
  );

  useEffect(() => {
    if (followLive && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [filtered.length, followLive]);

  const toggleFamily = (family: EventFamily) => {
    setActiveFamilies((current) => {
      const next = new Set(current);
      if (next.has(family)) next.delete(family);
      else next.add(family);
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-edge px-3 py-2">
        {FAMILY_ORDER.filter((family) => (counts.get(family) ?? 0) > 0).map((family) => {
          const style = FAMILY_STYLES[family];
          const active = activeFamilies.has(family);
          return (
            <button
              key={family}
              type="button"
              onClick={() => toggleFamily(family)}
              className={clsx(
                "rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors",
                active ? style.badge : "border-edge bg-surface-2 text-zinc-500 hover:text-zinc-300",
              )}
            >
              {style.label} <span className="opacity-60">{counts.get(family)}</span>
            </button>
          );
        })}
        {activeFamilies.size > 0 ? (
          <button
            type="button"
            className="ml-1 text-[11px] text-zinc-500 hover:text-zinc-300"
            onClick={() => setActiveFamilies(new Set())}
          >
            clear
          </button>
        ) : null}
        <span className="ml-auto font-mono text-[11px] text-zinc-600">
          {filtered.length} / {events.length} events
        </span>
      </div>

      <div ref={listRef} className={clsx("flex-1 overflow-y-auto", maxHeightClass)}>
        {filtered.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-zinc-600">No events.</div>
        ) : (
          filtered.map((event) => {
            const family = FAMILY_STYLES[eventFamily(event.event_type)];
            const failed = isFailureEvent(event.event_type);
            const latency = (event.payload as Record<string, unknown>).latency_ms;
            return (
              <button
                key={event.event_id}
                type="button"
                onClick={() => onSelect(event)}
                className={clsx(
                  "grid w-full grid-cols-[92px_120px_minmax(120px,180px)_1fr_64px] items-center gap-2 border-b border-edge/60 px-3 py-1.5 text-left transition-colors",
                  event.event_id === selectedEventId
                    ? "bg-indigo-500/10"
                    : "hover:bg-surface-2/80",
                )}
              >
                <span className="font-mono text-[10.5px] text-zinc-500">
                  {fmtClock(event.timestamp)}
                </span>
                <span
                  className={clsx(
                    "truncate rounded-md border px-1.5 py-0.5 text-center font-mono text-[10px]",
                    failed ? "border-red-400/40 bg-red-400/10 text-red-300" : family.badge,
                  )}
                >
                  {event.event_type}
                </span>
                <span className="truncate font-mono text-[11px] text-zinc-400">
                  {event.source_agent_id ?? "—"}
                  {event.target_agent_id ? (
                    <span className="text-zinc-600"> → {event.target_agent_id}</span>
                  ) : null}
                </span>
                <span
                  className={clsx(
                    "truncate text-[12px]",
                    failed ? "text-red-300" : "text-zinc-300",
                  )}
                >
                  {eventSummary(event)}
                </span>
                <span className="text-right font-mono text-[10.5px] text-zinc-500">
                  {typeof latency === "number" ? fmtMs(latency) : ""}
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
