// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RuntimeValidatorInfo, RuntimeValidatorResult } from "../../lib/types";

const registry: RuntimeValidatorInfo[] = [
  { type: "secret_exposure", description: "Scan for secret-like patterns.", target_type: "file", inputs: [] },
  { type: "code_syntax", description: "Validate .py/.json syntax.", target_type: "file", inputs: [] },
  { type: "research_claim", description: "Validate a claim against evidence.", target_type: "claim", inputs: [] },
];

function result(overrides: Partial<RuntimeValidatorResult> = {}): RuntimeValidatorResult {
  return {
    result_id: "val-1",
    workspace_id: "ws-abc123",
    workflow_id: null,
    task_id: null,
    agent_id: null,
    validator_type: "code_syntax",
    target_type: "file",
    target_ref: "app.py",
    passed: true,
    confidence: 1,
    evidence: { language: "python" },
    failures: [],
    suggested_action: null,
    risk_delta: 0,
    trust_delta: 0,
    explanation: "Python syntax is valid.",
    created_at: "2026-06-13T10:00:00Z",
    ...overrides,
  };
}

const runtimeValidators = vi.fn();
const validatorResults = vi.fn();
const runValidator = vi.fn();
vi.mock("../../lib/api", () => ({
  api: {
    runtimeValidators: (...a: unknown[]) => runtimeValidators(...a),
    validatorResults: (...a: unknown[]) => validatorResults(...a),
    runValidator: (...a: unknown[]) => runValidator(...a),
  },
}));

import { ValidatorsPanel } from "./ValidatorsPanel";

function renderPanel(props: Partial<{ readOnly: boolean; chatMode: boolean }> = {}) {
  return render(
    <ValidatorsPanel
      workspaceId="ws-abc123"
      readOnly={props.readOnly ?? false}
      chatMode={props.chatMode ?? false}
    />,
  );
}

beforeEach(() => {
  runtimeValidators.mockResolvedValue(registry);
  validatorResults.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ValidatorsPanel", () => {
  it("renders the registry count and run form", async () => {
    renderPanel();
    expect(
      await screen.findByText("3 deterministic · evidence-based · no web"),
    ).toBeTruthy();
    expect(screen.getByText("Run validator")).toBeTruthy();
  });

  it("renders the empty state", async () => {
    renderPanel();
    expect(await screen.findByTestId("validators-empty")).toBeTruthy();
  });

  it("runs a file validator", async () => {
    runValidator.mockResolvedValue(result());
    renderPanel();
    fireEvent.change(await screen.findByPlaceholderText("src/app.py"), {
      target: { value: "app.py" },
    });
    fireEvent.click(screen.getByText("Run validator"));
    await waitFor(() =>
      expect(runValidator).toHaveBeenCalledWith("ws-abc123", {
        validator_type: "secret_exposure",
        target_ref: "app.py",
        payload: {},
      }),
    );
  });

  it("renders a passing result", async () => {
    validatorResults.mockResolvedValue([result()]);
    renderPanel();
    const card = await screen.findByTestId("validator-result");
    expect(screen.getByTestId("result-badge").textContent).toBe("passed");
    expect(card.textContent).toContain("Python syntax is valid.");
  });

  it("renders a failing result with failures and suggested action", async () => {
    validatorResults.mockResolvedValue([
      result({
        passed: false,
        failures: ["Python syntax error at line 1: invalid syntax"],
        suggested_action: "fix the Python syntax error before using this file",
        risk_delta: 0.1,
        explanation: "Python syntax error at line 1.",
      }),
    ]);
    renderPanel();
    expect((await screen.findByTestId("result-badge")).textContent).toBe("failed");
    expect(screen.getByTestId("result-failures").textContent).toContain("syntax error");
    expect(screen.getByTestId("suggested-action").textContent).toContain("fix the Python syntax");
  });

  it("renders the redacted secret-exposure warning", async () => {
    validatorResults.mockResolvedValue([
      result({
        validator_type: "secret_exposure",
        passed: false,
        failures: ["line 1: api_key secret-like value"],
        evidence: { findings: [{ line: 1, kind: "api_key", snippet: "API_KEY = '[redacted]'" }] },
        explanation: "Found 1 secret-like value(s); the exposed text is redacted.",
      }),
    ]);
    renderPanel();
    expect((await screen.findByTestId("secret-warning")).textContent).toContain(
      "Secret-like content detected",
    );
    expect(screen.getByTestId("validator-result").textContent).toContain("[redacted]");
  });

  it("renders a claim-rejected result and schema mismatch explanation", async () => {
    validatorResults.mockResolvedValue([
      result({
        validator_type: "research_claim",
        target_type: "claim",
        passed: false,
        failures: ["no source_url provided for the claim"],
        explanation: "The claim is not supported by complete, cited evidence.",
      }),
      result({
        result_id: "val-2",
        validator_type: "data_flow",
        passed: false,
        explanation: "product page expects `price`, but product API does not provide it.",
      }),
    ]);
    renderPanel();
    const cards = await screen.findAllByTestId("validator-result");
    expect(cards[0].textContent).toContain("not supported by complete, cited evidence");
    expect(cards[1].textContent).toContain("expects `price`");
  });

  it("shows an error when payload JSON is invalid", async () => {
    renderPanel();
    // switch to a payload validator
    fireEvent.change((await screen.findAllByRole("combobox"))[0], {
      target: { value: "research_claim" },
    });
    fireEvent.change(screen.getByPlaceholderText(/"claim"/), {
      target: { value: "{ not json" },
    });
    fireEvent.click(screen.getByText("Run validator"));
    expect(await screen.findByText("Payload must be valid JSON.")).toBeTruthy();
    expect(runValidator).not.toHaveBeenCalled();
  });

  it("disables the run action in Chat Mode", async () => {
    renderPanel({ chatMode: true });
    const button = (await screen.findByText("Run validator")) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.title).toBe("Switch to Agent Mode to perform this action.");
  });

  it("hides the run form for read-only workspaces", async () => {
    validatorResults.mockResolvedValue([result()]);
    renderPanel({ readOnly: true });
    await screen.findByTestId("validator-result");
    expect(screen.queryByText("Run validator")).toBeNull();
  });
});
