// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ModelCallResult, Provider } from "../../lib/types";

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
    name: "openai",
    configured: true,
    status: "available",
    requires_key: true,
    models: ["gpt-4.1"],
    key_redacted: "sk-...wxyz",
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

const testCall = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    providers: () => Promise.resolve({ providers }),
    testCall: (...args: unknown[]) => testCall(...args),
  },
}));

import { ModelGateway } from "./ModelGateway";

afterEach(() => {
  cleanup();
  testCall.mockReset();
});

describe("ModelGateway", () => {
  it("renders provider cards with configured/not-configured status", async () => {
    render(<ModelGateway />);
    // status badges identify the cards (provider names also appear in selects)
    await waitFor(() => expect(screen.getAllByText("Available").length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText("Not configured")).toBeTruthy();
    expect(screen.getAllByText("mock").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("anthropic").length).toBeGreaterThanOrEqual(1);
  });

  it("shows only the redacted key, never a raw one", async () => {
    render(<ModelGateway />);
    expect(await screen.findByText("sk-...wxyz")).toBeTruthy();
    // the keyless mock shows 'keyless', the unconfigured one shows 'none'
    expect(screen.getAllByText("keyless").length).toBeGreaterThanOrEqual(1);
    expect(document.body.textContent).not.toMatch(/sk-[A-Za-z0-9]{8,}/);
  });

  it("renders a successful test-call result", async () => {
    testCall.mockResolvedValue({
      provider: "mock",
      model_name: "mock:claude-sonnet",
      output_text: "Hello from the mock provider",
      status: "completed",
      input_tokens: 100,
      output_tokens: 50,
      total_tokens: 150,
      estimated_cost_usd: 0.001,
      latency_ms: 200,
      error_message: null,
      event_id: "model-abc123",
    } satisfies ModelCallResult);

    render(<ModelGateway />);
    const runButton = await screen.findByText("▶ Run test call");
    runButton.click();
    await waitFor(() => expect(screen.getByText("Hello from the mock provider")).toBeTruthy());
    expect(screen.getByText("completed")).toBeTruthy();
    expect(screen.getByText(/model-abc123/)).toBeTruthy();
  });

  it("renders a failed test-call result with the error", async () => {
    testCall.mockResolvedValue({
      provider: "mock",
      model_name: "mock:gpt-4.1",
      output_text: "",
      status: "failed",
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      estimated_cost_usd: null,
      latency_ms: 10,
      error_message: "Simulated provider failure (mock)",
      event_id: "model-fail99",
    } satisfies ModelCallResult);

    render(<ModelGateway />);
    const runButton = await screen.findByText("▶ Run test call");
    runButton.click();
    await waitFor(() =>
      expect(screen.getByText("Simulated provider failure (mock)")).toBeTruthy(),
    );
    const result = screen.getByText("Simulated provider failure (mock)").closest("div")!;
    expect(within(result.parentElement as HTMLElement).getByText("failed")).toBeTruthy();
  });
});
