import { useState } from "react";

/** Compact collapsible JSON tree for payload/metadata inspection. */
export function JsonView({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null) return <span className="text-zinc-500">null</span>;
  if (value === undefined) return <span className="text-zinc-500">undefined</span>;
  switch (typeof value) {
    case "string":
      return <span className="break-all text-emerald-300">"{value}"</span>;
    case "number":
      return <span className="text-amber-300">{String(value)}</span>;
    case "boolean":
      return <span className="text-violet-300">{String(value)}</span>;
    case "object":
      return <JsonBranch value={value as object} depth={depth} />;
    default:
      return <span className="text-zinc-400">{String(value)}</span>;
  }
}

function JsonBranch({ value, depth }: { value: object; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const isArray = Array.isArray(value);
  const entries = isArray
    ? (value as unknown[]).map((item, index) => [index, item] as const)
    : Object.entries(value);

  if (entries.length === 0) {
    return <span className="text-zinc-500">{isArray ? "[]" : "{}"}</span>;
  }

  if (!open) {
    return (
      <button
        type="button"
        className="rounded text-zinc-500 hover:text-zinc-300"
        onClick={() => setOpen(true)}
      >
        {isArray ? `[… ${entries.length}]` : `{… ${entries.length}}`}
      </button>
    );
  }

  return (
    <span>
      <button
        type="button"
        className="rounded text-zinc-500 hover:text-zinc-300"
        onClick={() => setOpen(false)}
      >
        {isArray ? "[" : "{"}
      </button>
      <div className="ml-4 border-l border-edge pl-3">
        {entries.map(([key, item]) => (
          <div key={String(key)} className="leading-6">
            <span className="text-sky-300">{isArray ? key : `"${key}"`}</span>
            <span className="text-zinc-600">: </span>
            <JsonView value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
      <span className="text-zinc-500">{isArray ? "]" : "}"}</span>
    </span>
  );
}

export function RawJson({ value }: { value: unknown }) {
  return (
    <pre className="overflow-auto rounded-lg border border-edge bg-surface-0 p-3 font-mono text-[11.5px] leading-5 text-zinc-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
