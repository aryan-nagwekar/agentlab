// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Provider, StudioAgent } from "../../lib/types";
import { AgentEditor } from "./AgentEditor";

const providers: Provider[] = [
  {
    name: "mock",
    configured: true,
    status: "available",
    requires_key: false,
    models: ["mock:claude-sonnet", "mock:gpt-4.1"],
    key_redacted: null,
  },
  {
    name: "anthropic",
    configured: false,
    status: "not_configured",
    requires_key: true,
    models: ["claude-sonnet-4-6"],
    key_redacted: null,
  },
];

const agent: StudioAgent = {
  agent_id: "writer",
  name: "Writer",
  role: "writer",
  provider: "mock",
  model_name: "mock:claude-sonnet",
  temperature: 0.2,
  max_tokens: 1000,
  position_x: 0,
  position_y: 0,
};

afterEach(cleanup);

describe("AgentEditor", () => {
  it("edits agent fields", () => {
    const onChange = vi.fn();
    render(
      <AgentEditor agent={agent} providers={providers} onChange={onChange} onDelete={vi.fn()} />,
    );
    fireEvent.change(screen.getByDisplayValue("Writer"), { target: { value: "Lead Writer" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ name: "Lead Writer" }));
    fireEvent.change(screen.getByDisplayValue("writer"), { target: { value: "editor" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ role: "editor" }));
  });

  it("renders the provider selector with configured status", () => {
    render(
      <AgentEditor agent={agent} providers={providers} onChange={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(screen.getByText("mock")).toBeTruthy();
    expect(screen.getByText("anthropic (not configured)")).toBeTruthy();
  });

  it("switching provider defaults the model and warns when unconfigured", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <AgentEditor agent={agent} providers={providers} onChange={onChange} onDelete={vi.fn()} />,
    );
    fireEvent.change(screen.getByDisplayValue("mock"), { target: { value: "anthropic" } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "anthropic", model_name: "claude-sonnet-4-6" }),
    );
    rerender(
      <AgentEditor
        agent={{ ...agent, provider: "anthropic", model_name: "claude-sonnet-4-6" }}
        providers={providers}
        onChange={onChange}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/is not configured — running/)).toBeTruthy();
    expect(screen.getAllByText(/model\.failed/).length).toBeGreaterThanOrEqual(1);
  });

  it("delete button calls onDelete", () => {
    const onDelete = vi.fn();
    render(
      <AgentEditor agent={agent} providers={providers} onChange={vi.fn()} onDelete={onDelete} />,
    );
    fireEvent.click(screen.getByText("Delete agent"));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
