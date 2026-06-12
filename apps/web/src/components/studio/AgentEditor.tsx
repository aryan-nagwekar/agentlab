import type { Provider, StudioAgent } from "../../lib/types";
import { SectionLabel } from "../ui";

interface AgentEditorProps {
  agent: StudioAgent;
  providers: Provider[];
  onChange: (agent: StudioAgent) => void;
  onDelete: () => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </span>
      {children}
    </label>
  );
}

const inputClass =
  "rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200";

export function AgentEditor({ agent, providers, onChange, onDelete }: AgentEditorProps) {
  const provider = providers.find((p) => p.name === agent.provider);
  const set = (patch: Partial<StudioAgent>) => onChange({ ...agent, ...patch });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <SectionLabel>Agent — {agent.agent_id}</SectionLabel>
        <button
          type="button"
          onClick={onDelete}
          className="rounded-md border border-red-400/30 bg-red-400/10 px-2 py-1 text-[11px] text-red-300 transition-colors hover:bg-red-400/20"
        >
          Delete agent
        </button>
      </div>
      <Field label="Name">
        <input className={inputClass} value={agent.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Role">
        <input className={inputClass} value={agent.role} onChange={(e) => set({ role: e.target.value })} />
      </Field>
      <Field label="Description">
        <input
          className={inputClass}
          value={agent.description ?? ""}
          onChange={(e) => set({ description: e.target.value || null })}
        />
      </Field>
      <Field label="System prompt">
        <textarea
          className={inputClass}
          rows={3}
          value={agent.system_prompt ?? ""}
          onChange={(e) => set({ system_prompt: e.target.value || null })}
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Provider">
          <select
            className={inputClass}
            value={agent.provider}
            onChange={(e) => {
              const next = providers.find((p) => p.name === e.target.value);
              set({ provider: e.target.value, model_name: next?.models[0] ?? agent.model_name });
            }}
          >
            {providers.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
                {p.configured ? "" : " (not configured)"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model">
          <input
            className={`${inputClass} font-mono text-[12px]`}
            value={agent.model_name}
            onChange={(e) => set({ model_name: e.target.value })}
            list={`studio-models-${agent.agent_id}`}
          />
          <datalist id={`studio-models-${agent.agent_id}`}>
            {(provider?.models ?? []).map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Temperature">
          <input
            className={`${inputClass} font-mono`}
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={agent.temperature}
            onChange={(e) => set({ temperature: Number(e.target.value) })}
          />
        </Field>
        <Field label="Max tokens">
          <input
            className={`${inputClass} font-mono`}
            type="number"
            min={1}
            max={8000}
            value={agent.max_tokens}
            onChange={(e) => set({ max_tokens: Number(e.target.value) })}
          />
        </Field>
      </div>
      {provider && !provider.configured ? (
        <div className="rounded-md border border-amber-400/25 bg-amber-400/5 px-2.5 py-2 text-[11.5px] leading-5 text-amber-200/90">
          Provider <span className="font-mono">{provider.name}</span> is not configured — running
          this workflow will fail cleanly with <span className="font-mono">model.failed</span>{" "}
          unless a key is set. The <span className="font-mono">mock</span> provider needs no key.
        </div>
      ) : null}
    </div>
  );
}
