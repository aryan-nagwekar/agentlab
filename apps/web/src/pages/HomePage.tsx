import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { ErrorNote } from "../components/ui";

const CAPABILITIES = [
  { icon: "◉", title: "Observe agent actions", body: "Every file write, command, model call, and message becomes a replayable event." },
  { icon: "⟲", title: "Replay and debug failures", body: "Step through any run packet-by-packet and see exactly which agent caused what." },
  { icon: "✓", title: "Validate outputs and claims", body: "Deterministic validators catch secrets, broken syntax, bad data flow, and risky changes." },
  { icon: "⚑", title: "Review risky actions", body: "An enforcement gateway pauses sensitive actions for human approval before they run." },
  { icon: "⛔", title: "Quarantine restricted agents", body: "Real runtime restrictions stop a flagged agent from writing files or running commands." },
];

const STEPS = [
  { n: "1", title: "Create a project or demo", body: "Spin up a governed workspace — or one-click the Bottle Shop demo." },
  { n: "2", title: "Let AgentLab orchestrate the work", body: "Agents plan and build inside a sandbox; every action is tracked and governed." },
  { n: "3", title: "Inspect, validate, approve, replay", body: "Understand the project at a glance, approve risky changes, and replay what happened." },
];

export function HomePage() {
  const navigate = useNavigate();
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tryDemo = async () => {
    setSeeding(true);
    setError(null);
    try {
      const result = await api.createBottleShopDemo();
      navigate(`/runtime/workspaces/${result.workspace_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSeeding(false);
    }
  };

  return (
    <div data-testid="home-page" className="mx-auto max-w-4xl">
      {/* Hero */}
      <section className="rounded-2xl border border-edge bg-gradient-to-b from-indigo-500/[0.08] to-transparent px-6 py-12 text-center sm:px-10 sm:py-16">
        <span className="inline-block rounded-full border border-indigo-400/30 bg-indigo-500/10 px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-indigo-200">
          AI runtime · debugger · safety control plane
        </span>
        <h1 className="mt-5 text-3xl font-bold tracking-tight text-zinc-50 sm:text-5xl">
          Build with AI. Stay in control.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-[15px] text-zinc-300 sm:text-[17px]">
          AgentLab is the visual runtime, debugger, and safety control plane for AI-built
          software.
        </p>
        <p className="mx-auto mt-3 max-w-2xl text-[13.5px] leading-6 text-zinc-500">
          See what AI agents changed, replay what happened, validate outputs, review risky
          actions, and keep software generation inside a governed runtime.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={tryDemo}
            disabled={seeding}
            className="rounded-lg border border-indigo-400/50 bg-indigo-500/25 px-5 py-2.5 text-[13.5px] font-semibold text-indigo-50 transition-colors hover:bg-indigo-500/35 disabled:opacity-50"
          >
            {seeding ? "Building demo…" : "Try Bottle Shop Demo"}
          </button>
          <Link
            to="/runtime"
            className="rounded-lg border border-edge bg-surface-1 px-5 py-2.5 text-[13.5px] font-medium text-zinc-200 transition-colors hover:bg-surface-2"
          >
            Open Runtime
          </Link>
        </div>
        {error ? <div className="mx-auto mt-4 max-w-md"><ErrorNote message={error} /></div> : null}
      </section>

      {/* What AgentLab does */}
      <section className="mt-10">
        <h2 className="text-[12px] font-semibold uppercase tracking-wider text-zinc-500">
          What AgentLab does
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((c) => (
            <div key={c.title} className="rounded-xl border border-edge bg-surface-1 px-4 py-4">
              <div className="text-[18px] text-indigo-300">{c.icon}</div>
              <div className="mt-1.5 text-[13.5px] font-semibold text-zinc-100">{c.title}</div>
              <p className="mt-1 text-[12.5px] leading-5 text-zinc-500">{c.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="mt-10">
        <h2 className="text-[12px] font-semibold uppercase tracking-wider text-zinc-500">
          How it works
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="rounded-xl border border-edge bg-surface-1 px-4 py-4">
              <div className="flex h-7 w-7 items-center justify-center rounded-full border border-indigo-400/40 bg-indigo-500/15 text-[13px] font-bold text-indigo-200">
                {s.n}
              </div>
              <div className="mt-2 text-[13.5px] font-semibold text-zinc-100">{s.title}</div>
              <p className="mt-1 text-[12.5px] leading-5 text-zinc-500">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Positioning */}
      <section className="mt-10 rounded-xl border border-edge bg-surface-1 px-5 py-5">
        <h2 className="text-[14px] font-semibold text-zinc-100">
          Not just another AI coding assistant
        </h2>
        <p className="mt-2 text-[13px] leading-6 text-zinc-400">
          Claude, Codex, Cursor, and Replit can <em>generate</em> code. AgentLab helps you
          understand, govern, and debug what AI-built software is actually doing — turning
          invisible agent work into visual, replayable, enforceable system behavior.
        </p>
      </section>

      {/* CTA */}
      <section className="mt-10 mb-4 flex flex-wrap items-center justify-center gap-3 rounded-2xl border border-indigo-400/20 bg-indigo-500/[0.06] px-6 py-8 text-center">
        <div className="w-full text-[15px] font-semibold text-zinc-100">
          See it on a real project in one click.
        </div>
        <button
          type="button"
          onClick={tryDemo}
          disabled={seeding}
          className="rounded-lg border border-indigo-400/50 bg-indigo-500/25 px-5 py-2.5 text-[13.5px] font-semibold text-indigo-50 transition-colors hover:bg-indigo-500/35 disabled:opacity-50"
        >
          {seeding ? "Building demo…" : "Try Bottle Shop Demo"}
        </button>
        <Link
          to="/runtime"
          className="rounded-lg border border-edge bg-surface-1 px-5 py-2.5 text-[13.5px] font-medium text-zinc-200 transition-colors hover:bg-surface-2"
        >
          Open Runtime workspaces
        </Link>
      </section>
    </div>
  );
}
