import { ModelGateway } from "../components/gateway/ModelGateway";
import { Card, PageHeader, SectionLabel, StatusDot } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { API_BASE, api } from "../lib/api";
import { useAppStore } from "../store/app";

export function SettingsPage() {
  const wsStatus = useAppStore((s) => s.wsStatus);
  const health = useFetch(() => api.health(), []);

  const rows: Array<{ label: string; value: React.ReactNode }> = [
    {
      label: "Collector endpoint",
      value: (
        <span className="font-mono text-[12px]">{API_BASE || `${window.location.origin} (same-origin proxy)`}</span>
      ),
    },
    {
      label: "API status",
      value: health.data ? (
        <span className="flex items-center gap-2">
          <StatusDot className="bg-emerald-400" />
          <span>
            {health.data.service} v{health.data.version}
          </span>
        </span>
      ) : health.error ? (
        <span className="flex items-center gap-2">
          <StatusDot className="bg-red-400" /> unreachable
        </span>
      ) : (
        "checking…"
      ),
    },
    {
      label: "Live stream",
      value: (
        <span className="flex items-center gap-2">
          <StatusDot
            className={
              wsStatus === "live"
                ? "bg-emerald-400"
                : wsStatus === "connecting"
                  ? "bg-amber-400"
                  : "bg-zinc-600"
            }
          />
          {wsStatus === "live"
            ? "connected (WebSocket)"
            : wsStatus === "connecting"
              ? "connecting…"
              : "idle — opens on project/run pages"}
        </span>
      ),
    },
    {
      label: "Authentication",
      value: (
        <span>
          open local mode — set{" "}
          <code className="font-mono text-[12px] text-zinc-300">AGENTLAB_API_KEYS</code> on the API
          to require <code className="font-mono text-[12px] text-zinc-300">X-API-Key</code> on the
          write path
        </span>
      ),
    },
    {
      label: "Theme",
      value: "dark (infra-native; light mode is not on the roadmap)",
    },
  ];

  return (
    <>
      <PageHeader title="Settings" subtitle="Local deployment configuration (read-only in v0.1)" />
      <Card>
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex flex-col gap-1 border-b border-edge px-4 py-3.5 text-[13px] last:border-0 sm:flex-row sm:items-center"
          >
            <div className="w-48 shrink-0 text-zinc-500">{row.label}</div>
            <div className="text-zinc-300">{row.value}</div>
          </div>
        ))}
      </Card>

      <div className="mt-8">
        <PageHeader title="Model Gateway" subtitle="Local-first BYOK — call providers through one interface (mock works without keys)" />
        <ModelGateway />
      </div>

      <div className="mt-8">
        <SectionLabel>Configuration reference</SectionLabel>
        <Card className="px-4 py-3 font-mono text-[12px] leading-7 text-zinc-400">
          <div>AGENTLAB_DATABASE_URL &nbsp;<span className="text-zinc-600"># sqlite:///./agentlab.db | postgresql+psycopg://…</span></div>
          <div>AGENTLAB_API_KEYS &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-zinc-600"># comma-separated; empty = open local mode</span></div>
          <div>OPENAI_API_KEY &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-zinc-600"># model gateway BYOK (server-side only)</span></div>
          <div>ANTHROPIC_API_KEY &nbsp;&nbsp;&nbsp;<span className="text-zinc-600"># model gateway BYOK (server-side only)</span></div>
          <div>GEMINI_API_KEY &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-zinc-600"># model gateway BYOK (or GOOGLE_API_KEY)</span></div>
          <div>OLLAMA_BASE_URL &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-zinc-600"># default http://localhost:11434; Docker: host.docker.internal</span></div>
          <div>AGENTLAB_DISABLED &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-zinc-600"># =1 turns the SDK into a no-op</span></div>
        </Card>
      </div>
    </>
  );
}
