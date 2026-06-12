import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge, Card, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useFetch } from "../hooks/useFetch";
import { api } from "../lib/api";

const CATEGORY_BADGE: Record<string, string> = {
  engineering: "border-indigo-400/30 bg-indigo-400/10 text-indigo-300",
  research: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  careers: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  security: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  support: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  analytics: "border-violet-400/30 bg-violet-400/10 text-violet-300",
};

export function StudioTemplatesPage() {
  const { data: templates, loading, error } = useFetch(() => api.studioTemplates(), []);
  const navigate = useNavigate();
  const [creating, setCreating] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const createFromTemplate = async (templateId: string) => {
    setCreating(templateId);
    setCreateError(null);
    try {
      const created = await api.createWorkflowFromTemplate(templateId, {});
      navigate(`${created.open_url}?template=${created.template_id}`);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
      setCreating(null);
    }
  };

  if (loading) return <Spinner label="Loading templates…" />;
  if (error) return <ErrorNote message={error} />;

  return (
    <>
      <PageHeader
        title="Start from template"
        subtitle="Prebuilt agent-team blueprints — create a workflow, customize it in Studio, then run it with zero API keys"
        actions={
          <Link
            to="/studio"
            className="rounded-lg border border-edge bg-surface-1 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-2"
          >
            ← My workflows
          </Link>
        }
      />
      {createError ? <ErrorNote message={createError} /> : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {(templates ?? []).map((template) => (
          <Card key={template.template_id} className="flex h-full flex-col px-4 py-4">
            <div className="flex items-start gap-2">
              <div className="text-[14.5px] font-semibold text-zinc-100">{template.name}</div>
              <Badge
                className={`ml-auto shrink-0 ${CATEGORY_BADGE[template.category] ?? "border-zinc-600/30 bg-zinc-600/10 text-zinc-400"}`}
              >
                {template.category}
              </Badge>
            </div>
            <p className="mt-1.5 text-[12.5px] leading-5 text-zinc-500">{template.description}</p>
            <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">{template.use_case}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {template.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-md border border-edge bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500"
                >
                  {tag}
                </span>
              ))}
            </div>
            <div className="mt-auto flex items-center gap-2 pt-4">
              <span className="text-[11px] text-zinc-600">
                {template.agent_count} agents · {template.difficulty}
              </span>
              <div className="ml-auto flex gap-2">
                <Link
                  to={`/studio/templates/${template.template_id}`}
                  className="rounded-md border border-edge bg-surface-1 px-2.5 py-1.5 text-[11.5px] font-medium text-zinc-300 transition-colors hover:bg-surface-2"
                >
                  Preview
                </Link>
                <button
                  type="button"
                  onClick={() => createFromTemplate(template.template_id)}
                  disabled={creating !== null}
                  className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-2.5 py-1.5 text-[11.5px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
                >
                  {creating === template.template_id ? "Creating…" : "Create workflow"}
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
