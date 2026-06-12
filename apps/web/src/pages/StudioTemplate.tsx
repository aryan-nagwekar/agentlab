import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { StudioCanvas } from "../components/studio/StudioCanvas";
import { Badge, Card, ErrorNote, PageHeader, SectionLabel, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";
import type { StudioAgent, StudioEdge } from "../lib/types";

export function StudioTemplatePage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const templateState = useFetch(() => api.studioTemplate(templateId!), [templateId]);
  const providersState = useFetch(() => api.providers(), []);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (templateState.loading || providersState.loading)
    return <Spinner label="Loading template…" />;
  if (templateState.error) return <ErrorNote message={templateState.error} />;
  const template = templateState.data!;
  const providers = providersState.data?.providers ?? [];

  // The template preview reuses the Studio canvas read-only.
  const previewAgents: StudioAgent[] = template.agents.map((a) => ({
    agent_id: a.agent_id,
    name: a.name,
    role: a.role,
    provider: a.provider,
    model_name: a.model_name,
    temperature: a.temperature,
    max_tokens: a.max_tokens,
    position_x: a.position_x,
    position_y: a.position_y,
  }));
  const previewEdges: StudioEdge[] = template.edges.map((e, i) => ({
    edge_id: `preview-${i}`,
    source_agent_id: e.source_agent_id,
    target_agent_id: e.target_agent_id,
    label: e.label,
  }));

  const create = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const created = await api.createWorkflowFromTemplate(template.template_id, {
        name: name.trim() || undefined,
      });
      navigate(`${created.open_url}?template=${created.template_id}`);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
      setCreating(false);
    }
  };

  return (
    <>
      <PageHeader
        title={template.name}
        subtitle={template.description}
        actions={
          <Link
            to="/studio/templates"
            className="rounded-lg border border-edge bg-surface-1 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-2"
          >
            ← All templates
          </Link>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge className="border-indigo-400/30 bg-indigo-400/10 text-indigo-300">
          {template.category}
        </Badge>
        <Badge className="border-zinc-600/30 bg-zinc-600/10 text-zinc-400">
          {template.difficulty}
        </Badge>
        <span className="text-[11.5px] text-zinc-600">{template.use_case}</span>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="min-w-0 flex-1 space-y-4">
          <Card className="h-[360px] overflow-hidden p-0">
            <StudioCanvas
              agents={previewAgents}
              edges={previewEdges}
              providers={providers}
              selectedAgentId={null}
              selectedEdgeId={null}
              onSelectAgent={() => {}}
              onSelectEdge={() => {}}
              onMoveAgent={() => {}}
              onConnect={() => {}}
            />
          </Card>
          <Card className="px-4 py-4">
            <SectionLabel>Agent team</SectionLabel>
            <div className="space-y-2">
              {template.agents.map((agent) => (
                <div
                  key={agent.agent_id}
                  className="rounded-lg border border-edge bg-surface-2 px-3 py-2.5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-semibold text-zinc-100">{agent.name}</span>
                    <span className="text-[10.5px] font-medium uppercase tracking-wider text-zinc-500">
                      {agent.role}
                    </span>
                    <span className="ml-auto font-mono text-[10.5px] text-zinc-500">
                      {agent.provider} · {agent.model_name}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-5 text-zinc-500">{agent.description}</p>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setShowAdvanced((s) => !s)}
              className="mt-3 text-[11.5px] text-zinc-500 hover:text-zinc-300"
            >
              {showAdvanced ? "▾ Hide system prompts" : "▸ Show system prompts"}
            </button>
            {showAdvanced ? (
              <div className="mt-2 space-y-2">
                {template.agents.map((agent) => (
                  <div key={agent.agent_id} className="rounded-md bg-surface-0 px-3 py-2">
                    <div className="font-mono text-[10.5px] text-zinc-500">{agent.agent_id}</div>
                    <div className="mt-0.5 text-[11.5px] leading-5 text-zinc-400">
                      {agent.system_prompt}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </Card>
        </div>

        <div className="w-full shrink-0 space-y-4 lg:w-[340px]">
          <Card className="px-4 py-4">
            <SectionLabel>Create workflow</SectionLabel>
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Workflow name (optional)
              </span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={template.name}
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
              />
            </label>
            <button
              type="button"
              onClick={create}
              disabled={creating}
              className="mt-3 w-full rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-2 text-[12.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {creating ? "Creating…" : "Create workflow → Open in Studio"}
            </button>
            {createError ? <div className="mt-2"><ErrorNote message={createError} /></div> : null}
            <p className="mt-3 text-[11px] leading-5 text-zinc-600">
              All agents default to the keyless <span className="font-mono">mock</span> provider —
              you can switch any agent to a real provider in the editor.
            </p>
          </Card>
          <Card className="px-4 py-4">
            <SectionLabel>Default input</SectionLabel>
            <p className="rounded-lg border border-edge bg-surface-0 px-3 py-2 text-[12px] leading-5 text-zinc-400">
              {template.default_input}
            </p>
          </Card>
          <Card className="px-4 py-4">
            <SectionLabel>Expected outputs</SectionLabel>
            <ul className="space-y-1 text-[12px] leading-5 text-zinc-400">
              {template.expected_outputs.map((output) => (
                <li key={output}>· {output}</li>
              ))}
            </ul>
          </Card>
          <Card className="px-4 py-4">
            <SectionLabel>Demo notes</SectionLabel>
            <p className="text-[12px] leading-5 text-zinc-500">{template.demo_notes}</p>
          </Card>
        </div>
      </div>
    </>
  );
}
