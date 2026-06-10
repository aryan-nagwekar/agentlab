import { clsx } from "clsx";

import { fmtClock } from "../../lib/format";
import type { ReplayMarkers } from "../../lib/types";
import { Card } from "../ui";
import { nextMarker } from "./replayReducer";

const SPEEDS = [0.5, 1, 2, 4, 8];

export type JumpKind = "error" | "tool" | "routing" | "fault";

interface ReplayControlsProps {
  cursor: number;
  total: number;
  playing: boolean;
  speed: number;
  markers: ReplayMarkers;
  currentTimestamp: string | null;
  onTogglePlay: () => void;
  onStep: (delta: number) => void;
  onSeek: (index: number) => void;
  onSpeed: (speed: number) => void;
  onJump: (kind: JumpKind) => void;
}

export function ReplayControls({
  cursor,
  total,
  playing,
  speed,
  markers,
  currentTimestamp,
  onTogglePlay,
  onStep,
  onSeek,
  onSpeed,
  onJump,
}: ReplayControlsProps) {
  const maxIndex = Math.max(0, total - 1);
  const percent = (index: number) => (maxIndex === 0 ? 0 : (index / maxIndex) * 100);

  const jumpTargets: Record<JumpKind, number | null> = {
    error: nextMarker(markers.errors, cursor),
    tool: nextMarker(markers.tool_calls, cursor),
    routing: nextMarker(markers.routing, cursor),
    fault: nextMarker(markers.faults, cursor),
  };

  return (
    <Card className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-1">
          <TransportButton label="Restart" onClick={() => onSeek(0)} disabled={cursor === 0}>
            ⏮
          </TransportButton>
          <TransportButton label="Step back" onClick={() => onStep(-1)} disabled={cursor === 0}>
            ◀
          </TransportButton>
          <button
            type="button"
            onClick={onTogglePlay}
            disabled={total === 0}
            aria-label={playing ? "Pause" : "Play"}
            className={clsx(
              "flex h-9 w-9 items-center justify-center rounded-lg border text-[15px] transition-colors",
              playing
                ? "border-indigo-400/60 bg-indigo-500/20 text-indigo-200"
                : "border-edge bg-surface-2 text-zinc-200 hover:border-edge-strong",
            )}
          >
            {playing ? "❚❚" : "▶"}
          </button>
          <TransportButton
            label="Step forward"
            onClick={() => onStep(1)}
            disabled={cursor >= maxIndex}
          >
            ▶
          </TransportButton>
          <TransportButton
            label="Skip to end"
            onClick={() => onSeek(maxIndex)}
            disabled={cursor >= maxIndex}
          >
            ⏭
          </TransportButton>
        </div>

        <div className="relative min-w-[220px] flex-1 pt-2">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-2">
            {markers.errors.map((index) => (
              <MarkerDot key={`e${index}`} left={percent(index)} className="bg-red-400" />
            ))}
            {markers.tool_calls.map((index) => (
              <MarkerDot key={`t${index}`} left={percent(index)} className="bg-amber-400" />
            ))}
            {markers.routing.map((index) => (
              <MarkerDot key={`r${index}`} left={percent(index)} className="bg-cyan-400" />
            ))}
            {markers.faults.map((index) => (
              <MarkerDot key={`f${index}`} left={percent(index)} className="bg-rose-400" />
            ))}
          </div>
          <input
            type="range"
            min={0}
            max={maxIndex}
            value={Math.min(cursor, maxIndex)}
            onChange={(event) => onSeek(Number(event.target.value))}
            className="w-full accent-indigo-400"
            aria-label="Replay position"
          />
        </div>

        <div className="font-mono text-[11.5px] text-zinc-400">
          event <span className="text-zinc-100">{total === 0 ? 0 : cursor + 1}</span>
          <span className="text-zinc-600"> / {total}</span>
          <span className="ml-2 text-zinc-500">{fmtClock(currentTimestamp)}</span>
        </div>

        <select
          value={speed}
          onChange={(event) => onSpeed(Number(event.target.value))}
          className="rounded-md border border-edge bg-surface-2 px-2 py-1 text-[12px] text-zinc-300"
          aria-label="Playback speed"
        >
          {SPEEDS.map((value) => (
            <option key={value} value={value}>
              {value}×
            </option>
          ))}
        </select>

        <div className="flex items-center gap-1.5">
          <JumpButton
            label="Error"
            dot="bg-red-400"
            disabled={jumpTargets.error === null}
            onClick={() => onJump("error")}
          />
          <JumpButton
            label="Tool"
            dot="bg-amber-400"
            disabled={jumpTargets.tool === null}
            onClick={() => onJump("tool")}
          />
          <JumpButton
            label="Routing"
            dot="bg-cyan-400"
            disabled={jumpTargets.routing === null}
            onClick={() => onJump("routing")}
          />
          <JumpButton
            label="Fault"
            dot="bg-rose-400"
            disabled={jumpTargets.fault === null}
            onClick={() => onJump("fault")}
          />
        </div>
      </div>
    </Card>
  );
}

function TransportButton({
  children,
  label,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className="flex h-9 w-9 items-center justify-center rounded-lg border border-edge bg-surface-2 text-[12px] text-zinc-300 transition-colors hover:border-edge-strong hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function MarkerDot({ left, className }: { left: number; className: string }) {
  return (
    <span
      className={clsx("absolute top-0 h-1.5 w-1.5 -translate-x-1/2 rounded-full", className)}
      style={{ left: `${left}%` }}
    />
  );
}

function JumpButton({
  label,
  dot,
  disabled,
  onClick,
}: {
  label: string;
  dot: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={`Jump to next ${label.toLowerCase()}`}
      className="flex items-center gap-1.5 rounded-full border border-edge bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-zinc-300 transition-colors hover:border-edge-strong hover:text-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <span className={clsx("h-1.5 w-1.5 rounded-full", dot)} />
      {label}
    </button>
  );
}
