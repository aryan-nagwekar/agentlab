// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AgentLabEvent } from "../../lib/types";
import { EventDetail } from "./EventDetail";

function modelCompleted(payload: Record<string, unknown>): AgentLabEvent {
  return {
    id: 1,
    event_id: "evt-1",
    event_type: "model.completed",
    timestamp: "2026-06-15T16:43:00.000Z",
    project_id: "demo",
    run_id: "run-1",
    source_agent_id: "summary-agent",
    target_agent_id: null,
    payload: { provider: "ollama", model: "qwen2.5-coder", status: "completed", ...payload },
    metadata: {},
  };
}

afterEach(cleanup);

describe("EventDetail model output", () => {
  it("renders the full output_text for a Studio model.completed event", () => {
    const event = modelCompleted({
      output_preview: "Summary of Findings".slice(0, 200),
      output_text: "Summary of Findings\n\nMulti-agent AI systems face several risks.",
    });
    render(<EventDetail event={event} allEvents={[event]} onSelectEvent={() => {}} />);
    // The readable "Output" block surfaces the full answer (also echoed in raw JSON).
    expect(screen.getByText("Output")).toBeTruthy();
    expect(
      screen.getAllByText(/Multi-agent AI systems face several risks/).length,
    ).toBeGreaterThan(0);
  });

  it("falls back to output_preview when no full output is present", () => {
    const event = modelCompleted({ output_preview: "Just a short preview" });
    render(<EventDetail event={event} allEvents={[event]} onSelectEvent={() => {}} />);
    expect(screen.getAllByText(/Just a short preview/).length).toBeGreaterThan(0);
  });
});
