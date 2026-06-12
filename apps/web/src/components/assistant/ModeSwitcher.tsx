import { clsx } from "clsx";

import { useAppStore, type StudioMode } from "../../store/app";

const MODES: { id: StudioMode; label: string; hint: string }[] = [
  { id: "chat", label: "Chat Mode", hint: "Ask questions — read-only, no actions" },
  { id: "agent", label: "Agent Mode", hint: "Run workflows, edit agents, configure providers" },
];

export function ModeSwitcher() {
  const mode = useAppStore((s) => s.studioMode);
  const setMode = useAppStore((s) => s.setStudioMode);
  return (
    <div
      role="tablist"
      aria-label="Studio mode"
      className="flex rounded-lg border border-edge bg-surface-1 p-0.5"
    >
      {MODES.map((entry) => (
        <button
          key={entry.id}
          type="button"
          role="tab"
          aria-selected={mode === entry.id}
          title={entry.hint}
          onClick={() => setMode(entry.id)}
          className={clsx(
            "rounded-md px-2.5 py-1 text-[11.5px] font-medium transition-colors",
            mode === entry.id
              ? entry.id === "agent"
                ? "bg-indigo-500/20 text-indigo-200"
                : "bg-sky-500/20 text-sky-200"
              : "text-zinc-500 hover:text-zinc-300",
          )}
        >
          {entry.label}
        </button>
      ))}
    </div>
  );
}
