import { clsx } from "clsx";
import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import { fmtCost, fmtMs, fmtNum } from "../../lib/format";
import type { ModelCallResult, Provider } from "../../lib/types";
import { Badge, Card, ErrorNote, SectionLabel, Spinner, StatusDot } from "../ui";

const STATUS_STYLE: Record<string, { dot: string; label: string; badge: string }> = {
  available: { dot: "bg-emerald-400", label: "Available", badge: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" },
  not_configured: { dot: "bg-zinc-600", label: "Not configured", badge: "border-zinc-600/30 bg-zinc-600/10 text-zinc-400" },
  unavailable: { dot: "bg-amber-400", label: "Unavailable", badge: "border-amber-400/30 bg-amber-400/10 text-amber-300" },
  error: { dot: "bg-red-400", label: "Error", badge: "border-red-400/30 bg-red-400/10 text-red-300" },
};

export function ModelGateway() {
  const { data, loading, error, refetch } = useFetch(() => api.providers(), []);

  if (loading) return <Spinner label="Checking providers…" />;
  if (error) return <ErrorNote message={error} />;
  const providers = data?.providers ?? [];

  return (
    <div className="space-y-6">
      <Card className="border-indigo-400/20 bg-indigo-500/5 px-4 py-3 text-[12.5px] leading-6 text-zinc-400">
        <span className="font-medium text-indigo-300">Local-first BYOK.</span> Provider keys are
        read from the server's environment (<code className="font-mono text-[11.5px]">.env</code>),
        held only in memory, and <span className="text-zinc-300">never stored, returned to the
        browser, or logged</span> — only a redacted hint is shown. The{" "}
        <span className="font-mono text-[11.5px]">mock</span> provider needs no key.
      </Card>

      <div>
        <SectionLabel>Providers</SectionLabel>
        <div className="grid gap-3 sm:grid-cols-2">
          {providers.map((p) => (
            <ProviderCard key={p.name} provider={p} />
          ))}
        </div>
      </div>

      <TestCall providers={providers} onResult={() => refetch(true)} />
    </div>
  );
}

function ProviderCard({ provider }: { provider: Provider }) {
  const style = STATUS_STYLE[provider.status] ?? STATUS_STYLE.error;
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-center gap-2">
        <StatusDot className={style.dot} />
        <span className="text-[14px] font-semibold capitalize text-zinc-100">{provider.name}</span>
        <Badge className={clsx("ml-auto", style.badge)}>{style.label}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-zinc-500">
        <span>{provider.configured ? "configured" : "not configured"}</span>
        {provider.requires_key ? (
          <span className="font-mono">
            key:{" "}
            {provider.key_redacted ? (
              <span className="text-zinc-300">{provider.key_redacted}</span>
            ) : (
              <span className="text-zinc-600">none</span>
            )}
          </span>
        ) : (
          <span className="text-zinc-600">keyless</span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {provider.models.slice(0, 4).map((m) => (
          <span key={m} className="rounded-md border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
            {m}
          </span>
        ))}
        {provider.models.length > 4 ? (
          <span className="px-1 text-[10px] text-zinc-600">+{provider.models.length - 4}</span>
        ) : null}
      </div>
      {provider.message && provider.status !== "available" ? (
        <div
          className={clsx(
            "mt-2 rounded-md border px-2 py-1.5 text-[11px] leading-5",
            provider.status === "unavailable" || provider.status === "not_configured"
              ? "border-amber-400/25 bg-amber-400/5 text-amber-200/90"
              : "border-red-400/25 bg-red-400/5 text-red-300",
          )}
        >
          {provider.message}
        </div>
      ) : null}
    </Card>
  );
}

function TestCall({ providers, onResult }: { providers: Provider[]; onResult: () => void }) {
  const usable = providers.filter((p) => p.configured && p.status !== "unavailable");
  const [provider, setProvider] = useState(usable[0]?.name ?? "mock");
  const current = providers.find((p) => p.name === provider) ?? providers[0];
  const [model, setModel] = useState(current?.models[0] ?? "mock:claude-sonnet");
  const [prompt, setPrompt] = useState("Say hello from AgentLab.");
  const [simulateFailure, setSimulateFailure] = useState(false);
  const [result, setResult] = useState<ModelCallResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const models = providers.find((p) => p.name === provider)?.models ?? [];

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.testCall({
        provider,
        model_name: model,
        prompt,
        agent_id: "gateway-tester",
        project_id: "demo-project",
        run_id: "gateway-test",
        simulate_failure: simulateFailure,
      });
      setResult(res);
      onResult();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <SectionLabel>Test a model call</SectionLabel>
      <Card className="space-y-3 px-4 py-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">Provider</span>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                const next = providers.find((p) => p.name === e.target.value);
                setModel(next?.models[0] ?? "");
              }}
              className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.configured}>
                  {p.name}
                  {p.configured ? "" : " (not configured)"}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">Model</span>
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              list="gateway-models"
              className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200"
            />
            <datalist id="gateway-models">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">Prompt</span>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            className="rounded-lg border border-edge bg-surface-0 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
          />
        </label>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={run}
            disabled={busy || !prompt.trim()}
            className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Calling…" : "▶ Run test call"}
          </button>
          {provider === "mock" ? (
            <label className="flex items-center gap-1.5 text-[11.5px] text-zinc-500">
              <input type="checkbox" checked={simulateFailure} onChange={(e) => setSimulateFailure(e.target.checked)} className="accent-rose-400" />
              simulate failure
            </label>
          ) : null}
          <span className="ml-auto text-[11px] text-zinc-600">emits telemetry into the “gateway-test” run</span>
        </div>

        {err ? <ErrorNote message={err} /> : null}
        {result ? <TestResult result={result} /> : null}
      </Card>
    </div>
  );
}

function TestResult({ result }: { result: ModelCallResult }) {
  const failed = result.status === "failed";
  return (
    <div className={clsx("rounded-lg border px-3 py-2.5", failed ? "border-red-400/30 bg-red-400/5" : "border-edge bg-surface-2")}>
      <div className="flex items-center gap-2">
        <Badge className={failed ? "border-red-400/40 bg-red-400/10 text-red-300" : "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"}>
          {result.status}
        </Badge>
        <span className="font-mono text-[11px] text-zinc-400">{result.model_name}</span>
        <span className="ml-auto flex gap-3 font-mono text-[11px] text-zinc-400">
          <span>{fmtNum(result.total_tokens)} tok</span>
          <span>{result.estimated_cost_usd === null ? "—" : fmtCost(result.estimated_cost_usd)}</span>
          <span>{fmtMs(result.latency_ms)}</span>
        </span>
      </div>
      {failed ? (
        <div className="mt-2 text-[12px] text-red-300">{result.error_message}</div>
      ) : (
        <div className="mt-2 whitespace-pre-wrap text-[12px] text-zinc-300">{result.output_text}</div>
      )}
      {result.event_id ? (
        <div className="mt-2 font-mono text-[10.5px] text-zinc-600">
          event {result.event_id.slice(0, 12)} — visible in the run timeline, replay & Cost & Tokens
        </div>
      ) : null}
    </div>
  );
}
