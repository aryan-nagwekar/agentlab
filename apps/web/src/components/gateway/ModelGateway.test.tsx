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
  {
    name: "gemini",
    configured: true,
    status: "available",
    requires_key: true,
    models: ["gemini-1.5-flash", "gemini-2.0-flash"],
    key_redacted: "AIz...9876",
    message: "Configured.",
  },
  {
    name: "ollama",
    configured: true,
    status: "unavailable",
    requires_key: false,
    models: ["llama3.1"],
    key_redacted: null,
    message:
      "No Ollama server at http://localhost:11434. Start it with `ollama serve` (then `ollama pull llama3.2`), or point OLLAMA_BASE_URL at your server — Docker users: http://host.docker.internal:11434.",
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

  it("renders the gemini card with a redacted key and no raw key", async () => {
    render(<ModelGateway />);
    expect(await screen.findByText("gemini", { selector: "span" })).toBeTruthy();
    expect(screen.getByText("AIz...9876")).toBeTruthy();
    expect(screen.getByText("gemini-2.0-flash")).toBeTruthy();
    // a configured+available provider shows no troubleshooting hint
    expect(screen.queryByText("Configured.")).toBeNull();
    expect(document.body.textContent).not.toMatch(/AIza[A-Za-z0-9_-]{8,}/);
  });

  it("shows the troubleshooting message on the unavailable ollama card", async () => {
    render(<ModelGateway />);
    const hint = await screen.findByText(/No Ollama server at http:\/\/localhost:11434/);
    expect(hint.textContent).toContain("ollama serve");
    expect(hint.textContent).toContain("host.docker.internal");
    expect(screen.getByText("Unavailable")).toBeTruthy();
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
