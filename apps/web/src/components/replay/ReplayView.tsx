import { useCallback, useEffect, useMemo, useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { AgentLabEvent } from "../../lib/types";
import { InspectorPanel, type Selection } from "../inspector/InspectorPanel";
import { EventTimeline } from "../timeline/EventTimeline";
import { TopologyView } from "../topology/TopologyView";
import { Badge, Card, ErrorNote, Spinner } from "../ui";
import { ReplayControls, type JumpKind } from "./ReplayControls";
import { foldReplayGraph, nextMarker } from "./replayReducer";

interface ReplayViewProps {
  runId: string;
  projectId: string;
  runStatus: string;
}

export function ReplayView({ runId, projectId, runStatus }: ReplayViewProps) {
  const replayState = useFetch(() => api.runReplay(runId), [runId]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [manualSelection, setManualSelection] = useState<Selection>(null);

  const tape = replayState.data;
  const events = useMemo(() => tape?.events ?? [], [tape]);
  const maxIndex = Math.max(0, events.length - 1);

  const graph = useMemo(
    () => foldReplayGraph(events.slice(0, cursor + 1), runId, projectId),
    [events, cursor, runId, projectId],
  );
  const visibleEvents = useMemo(() => events.slice(0, cursor + 1), [events, cursor]);
  const currentEvent: AgentLabEvent | undefined = events[Math.min(cursor, maxIndex)];

  // Inspector follows the playhead unless the user pinned something.
  const selection: Selection =
    manualSelection ?? (currentEvent ? { kind: "event", event: currentEvent } : null);

  // Playback: pace by real inter-event gaps / speed, clamped so both --fast
  // seeded runs and slow live runs stay watchable.
  useEffect(() => {
    if (!playing) return;
    if (cursor >= maxIndex) {
      setPlaying(false);
      return;
    }
    const current = events[cursor];
    const next = events[cursor + 1];
    const realDelta = Math.max(
      0,
      new Date(next.timestamp).getTime() - new Date(current.timestamp).getTime(),
    );
    const delay = Math.min(1200, Math.max(80, realDelta / speed));
    const timer = window.setTimeout(
      () => setCursor((value) => Math.min(value + 1, maxIndex)),
      delay,
    );
    return () => window.clearTimeout(timer);
  }, [playing, cursor, speed, events, maxIndex]);

  const seek = useCallback(
    (index: number) => {
      setCursor(Math.max(0, Math.min(index, maxIndex)));
      setManualSelection(null);
    },
    [maxIndex],
  );

  const step = useCallback(
    (delta: number) => {
      setPlaying(false);
      setManualSelection(null);
      // Functional update: rapid steps (keyboard repeat) must not read a
      // stale render's cursor.
      setCursor((value) => Math.max(0, Math.min(value + delta, maxIndex)));
    },
    [maxIndex],
  );

  const jump = useCallback(
    (kind: JumpKind) => {
      if (!tape) return;
      const pool =
        kind === "error"
          ? tape.markers.errors
          : kind === "tool"
            ? tape.markers.tool_calls
            : tape.markers.routing;
      const target = nextMarker(pool, cursor);
      if (target !== null) {
        setPlaying(false);
        seek(target);
      }
    },
    [tape, cursor, seek],
  );

  // Keyboard transport: space = play/pause, arrows = step.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (event.code === "Space") {
        event.preventDefault();
        setPlaying((value) => !value);
      } else if (event.code === "ArrowRight") {
        event.preventDefault();
        step(1);
      } else if (event.code === "ArrowLeft") {
        event.preventDefault();
        step(-1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [step]);

  if (replayState.loading) return <Spinner label="Loading replay tape…" />;
  if (replayState.error) return <ErrorNote message={replayState.error} />;
  if (!tape || events.length === 0) {
    return <Card className="p-8 text-center text-sm text-zinc-600">No events to replay.</Card>;
  }

  return (
    <div className="space-y-4">
      <ReplayControls
        cursor={cursor}
        total={events.length}
        playing={playing}
        speed={speed}
        markers={tape.markers}
        currentTimestamp={currentEvent?.timestamp ?? null}
        onTogglePlay={() => setPlaying((value) => !value)}
        onStep={step}
        onSeek={(index) => {
          setPlaying(false);
          seek(index);
        }}
        onSpeed={setSpeed}
        onJump={jump}
      />

      {runStatus === "running" ? (
        <div className="rounded-lg border border-sky-400/30 bg-sky-400/5 px-3 py-2 text-[12px] text-sky-300">
          This run is still receiving events — the replay tape covers the {events.length} events
          loaded when this tab opened.
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
        <Card className="h-[520px] overflow-hidden">
          <TopologyView
            graph={graph}
            live={playing}
            selectedNodeId={manualSelection?.kind === "node" ? manualSelection.id : null}
            selectedEdgeId={manualSelection?.kind === "edge" ? manualSelection.id : null}
            onSelectNode={(id) => setManualSelection(id ? { kind: "node", id } : null)}
            onSelectEdge={(id) => setManualSelection({ kind: "edge", id })}
          />
        </Card>
        <div className="flex h-[520px] flex-col gap-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Inspector
            </span>
            {manualSelection === null ? (
              <Badge className="border-indigo-400/30 bg-indigo-500/10 text-indigo-300">
                following playhead
              </Badge>
            ) : (
              <button
                type="button"
                className="text-[11px] text-zinc-500 hover:text-zinc-300"
                onClick={() => setManualSelection(null)}
              >
                ↩ follow playhead
              </button>
            )}
          </div>
          <div className="min-h-0 flex-1">
            <InspectorPanel
              selection={selection}
              events={visibleEvents}
              nodes={graph.nodes}
              edges={graph.edges}
              projectId={projectId}
              onSelect={setManualSelection}
              onClose={() => setManualSelection(null)}
            />
          </div>
        </div>
      </div>

      <Card className="flex h-[280px] flex-col overflow-hidden">
        <EventTimeline
          events={visibleEvents}
          selectedEventId={selection?.kind === "event" ? selection.event.event_id : null}
          onSelect={(event) => setManualSelection({ kind: "event", event })}
          followLive={manualSelection === null}
          maxHeightClass="max-h-none"
        />
      </Card>
    </div>
  );
}
