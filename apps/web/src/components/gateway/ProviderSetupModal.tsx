import { useState } from "react";

import { api } from "../../lib/api";
import type { ProviderHealth } from "../../lib/types";
import { Badge, ErrorNote } from "../ui";

/** Which secure fields each configurable provider accepts. */
const PROVIDER_FIELDS: Record<string, { apiKey: boolean; baseUrl: boolean; keyEnv: string }> = {
  openai: { apiKey: true, baseUrl: true, keyEnv: "OPENAI_API_KEY" },
  anthropic: { apiKey: true, baseUrl: false, keyEnv: "ANTHROPIC_API_KEY" },
  gemini: { apiKey: true, baseUrl: true, keyEnv: "GEMINI_API_KEY" },
  ollama: { apiKey: false, baseUrl: true, keyEnv: "" },
};

const TEST_MODEL: Record<string, string> = {
  openai: "gpt-4.1-mini",
  anthropic: "claude-haiku-4-5",
  gemini: "gemini-2.0-flash",
  ollama: "llama3.2",
};

export function isConfigurableProvider(provider: string): boolean {
  return provider in PROVIDER_FIELDS;
}

interface ProviderSetupModalProps {
  provider: string;
  onClose: () => void;
  onSaved?: (health: ProviderHealth) => void;
}

export function ProviderSetupModal({ provider, onClose, onSaved }: ProviderSetupModalProps) {
  const fields = PROVIDER_FIELDS[provider];
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<ProviderHealth | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);

  const title = provider.charAt(0).toUpperCase() + provider.slice(1);

  const save = async () => {
    setBusy("save");
    setError(null);
    try {
      const health = await api.configureProvider(provider, {
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        ...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
      });
      setSaved(health);
      setApiKey(""); // the raw key leaves component state the moment it is saved
      onSaved?.(health);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const testCall = async () => {
    setBusy("test");
    setError(null);
    setTestResult(null);
    try {
      const result = await api.testCall({
        provider,
        model_name: TEST_MODEL[provider],
        prompt: "Reply with one short word.",
      });
      setTestResult(
        result.status === "completed"
          ? `✓ test call completed (${result.total_tokens ?? "?"} tokens)`
          : `✕ test call failed: ${result.error_message ?? "unknown error"}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const clear = async () => {
    setBusy("clear");
    setError(null);
    try {
      const health = await api.clearProvider(provider);
      setSaved(health);
      setTestResult(null);
      onSaved?.(health);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Configure ${title}`}
    >
      <div className="w-full max-w-md rounded-xl border border-edge bg-surface-1 p-5 shadow-2xl">
        <div className="flex items-center">
          <h2 className="text-[15px] font-semibold text-zinc-100">Configure {title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-md px-2 py-1 text-[13px] text-zinc-500 hover:text-zinc-200"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="mt-2 rounded-md border border-amber-400/25 bg-amber-400/5 px-2.5 py-2 text-[11.5px] leading-5 text-amber-200/90">
          Never paste API keys into chat. Use this secure setup field. The key is stored only in a
          local gitignored file on the server — never in the database, logs, events, or responses.
        </div>

        <div className="mt-4 space-y-3">
          {fields.apiKey ? (
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                {fields.keyEnv}
              </span>
              <input
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="paste your API key"
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12.5px] text-zinc-200"
              />
            </label>
          ) : null}
          {fields.baseUrl ? (
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Base URL {fields.apiKey ? "(optional)" : ""}
              </span>
              <input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={provider === "ollama" ? "http://localhost:11434" : "https://…"}
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200"
              />
            </label>
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={save}
            disabled={busy !== null || (!apiKey.trim() && !baseUrl.trim())}
            className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
          >
            {busy === "save" ? "Saving…" : "Save locally"}
          </button>
          <button
            type="button"
            onClick={testCall}
            disabled={busy !== null}
            className="rounded-lg border border-edge bg-surface-2 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-0 disabled:opacity-40"
          >
            {busy === "test" ? "Testing…" : "Test call"}
          </button>
          <button
            type="button"
            onClick={clear}
            disabled={busy !== null}
            className="ml-auto rounded-lg border border-red-400/25 bg-red-400/5 px-2.5 py-1.5 text-[11.5px] text-red-300/90 transition-colors hover:bg-red-400/15 disabled:opacity-40"
          >
            {busy === "clear" ? "Removing…" : "Remove saved key"}
          </button>
        </div>

        {error ? <div className="mt-3"><ErrorNote message={error} /></div> : null}
        {saved ? (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-edge bg-surface-2 px-3 py-2 text-[12px]">
            <Badge
              className={
                saved.configured
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                  : "border-zinc-600/30 bg-zinc-600/10 text-zinc-400"
              }
            >
              {saved.status}
            </Badge>
            <span className="text-zinc-300">
              {title}{" "}
              {saved.configured && saved.key_redacted
                ? `configured: ${saved.key_redacted}`
                : saved.configured
                  ? "configured"
                  : "not configured"}
            </span>
          </div>
        ) : null}
        {testResult ? (
          <div className="mt-2 text-[12px] text-zinc-400">{testResult}</div>
        ) : null}
      </div>
    </div>
  );
}
