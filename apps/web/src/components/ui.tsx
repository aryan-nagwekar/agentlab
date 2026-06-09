import { clsx } from "clsx";
import { useState, type ReactNode } from "react";

export function Card({
  children,
  className,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        "rounded-xl border border-edge bg-surface-1",
        onClick && "cursor-pointer transition-colors hover:border-edge-strong hover:bg-surface-2",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        className ?? "border-edge bg-surface-2 text-zinc-400",
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({ className, pulse }: { className: string; pulse?: boolean }) {
  return (
    <span
      className={clsx("inline-block h-2 w-2 shrink-0 rounded-full", className, pulse && "live-dot")}
    />
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "danger" | "accent";
}) {
  return (
    <Card className="px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">{label}</div>
      <div
        className={clsx(
          "mt-1 font-mono text-xl font-semibold",
          tone === "danger" ? "text-red-300" : tone === "accent" ? "text-indigo-300" : "text-zinc-100",
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-[11px] text-zinc-500">{hint}</div> : null}
    </Card>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">{title}</h1>
        {subtitle ? <div className="mt-1 text-sm text-zinc-500">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-12 text-sm text-zinc-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-700 border-t-indigo-400" />
      {label ?? "Loading…"}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-400/30 bg-red-400/5 px-4 py-3 text-sm text-red-300">
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="text-2xl">⏳</div>
      <div className="text-sm font-medium text-zinc-300">{title}</div>
      {children ? <div className="max-w-md text-sm text-zinc-500">{children}</div> : null}
    </Card>
  );
}

export function CodeSnippet({ command }: { command: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-edge bg-surface-0 px-3 py-2 font-mono text-[12px] text-zinc-300">
      <span className="select-none text-zinc-600">$</span>
      <span className="overflow-x-auto whitespace-nowrap">{command}</span>
      <CopyButton text={command} />
    </div>
  );
}

export function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={clsx(
        "ml-auto shrink-0 rounded-md border border-edge bg-surface-2 px-2 py-0.5 text-[11px] text-zinc-400",
        "transition-colors hover:border-edge-strong hover:text-zinc-200",
        className,
      )}
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1200);
        });
      }}
    >
      {copied ? "Copied ✓" : "Copy"}
    </button>
  );
}

export function TrustBar({ value, compact }: { value: number; compact?: boolean }) {
  const percent = Math.round(value * 100);
  const tone =
    value >= 0.8 ? "bg-emerald-400" : value >= 0.6 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className={clsx("flex items-center gap-2", compact ? "w-24" : "w-full")}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
        <div className={clsx("h-full rounded-full", tone)} style={{ width: `${percent}%` }} />
      </div>
      <span className="font-mono text-[11px] text-zinc-400">{value.toFixed(2)}</span>
    </div>
  );
}
