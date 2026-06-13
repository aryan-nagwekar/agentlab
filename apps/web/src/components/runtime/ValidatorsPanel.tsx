import { useState } from "react";

import { useFetch } from "../../hooks/useFetch";
import { api } from "../../lib/api";
import type { RuntimeValidatorResult } from "../../lib/types";
import { fmtClock } from "../../lib/format";
import { Card, ErrorNote, SectionLabel, Spinner } from "../ui";

const CHAT_HINT = "Switch to Agent Mode to perform this action.";

// Validators that take a workspace path/run-id; the rest take a JSON payload.
const FILE_VALIDATORS = new Set(["secret_exposure", "code_syntax", "command_result"]);

const PAYLOAD_HINT: Record<string, string> = {
  research_claim:
    '{"claim":"Acme bottles","source_url":"https://acme.example","evidence_text":"price MOQ shipping supplier_name"}',
  data_flow:
    '{"consumer":{"label":"product page","fields":{"price":"number"}},"producer":{"label":"product API","fields":{"cost":"number"}}}',
  business_risk: '{"target":"src/payment/checkout.ts","description":"wire stripe"}',
};

export function ValidatorsPanel({
  workspaceId,
  readOnly,
  chatMode,
}: {
  workspaceId: string;
  readOnly: boolean;
  chatMode: boolean;
}) {
  const registryState = useFetch(() => api.runtimeValidators(), []);
  const resultsState = useFetch(() => api.validatorResults(workspaceId), [workspaceId]);
  const registry = registryState.data ?? [];

  const [validatorType, setValidatorType] = useState("secret_exposure");
  const [targetRef, setTargetRef] = useState("");
  const [payloadText, setPayloadText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = chatMode || readOnly;
  const hintTitle = chatMode ? CHAT_HINT : undefined;
  const isFileValidator = FILE_VALIDATORS.has(validatorType);
  const results = resultsState.data ?? [];

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      let payload: Record<string, unknown> = {};
      if (!isFileValidator && payloadText.trim()) {
        try {
          payload = JSON.parse(payloadText);
        } catch {
          setError("Payload must be valid JSON.");
          setBusy(false);
          return;
        }
      }
      await api.runValidator(workspaceId, {
        validator_type: validatorType,
        target_ref: targetRef.trim(),
        payload,
      });
      resultsState.refetch(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (resultsState.loading) {
    return (
      <Card className="px-4 py-4">
        <SectionLabel>Validators</SectionLabel>
        <Spinner label="Loading validators…" />
      </Card>
    );
  }

  return (
    <Card className="px-4 py-4">
      <div className="flex items-center justify-between">
        <SectionLabel>Validators</SectionLabel>
        <span className="rounded-md border border-edge bg-surface-0 px-1.5 py-0.5 text-[10px] text-zinc-500">
          {registry.length || "—"} deterministic · evidence-based · no web
        </span>
      </div>

      <p className="mt-2 text-[11.5px] leading-5 text-zinc-600">
        Deterministic checks over files, recorded command results, and structured
        claim/data-flow/business metadata. No code is executed and no URLs are
        fetched; evidence is bounded and secrets are redacted.
      </p>

      {/* Run form */}
      {!readOnly ? (
        <div className="mt-3 space-y-2 rounded-lg border border-edge bg-surface-0 px-3 py-2.5">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Validator
              </span>
              <select
                value={validatorType}
                onChange={(e) => setValidatorType(e.target.value)}
                disabled={disabled}
                className="rounded-lg border border-edge bg-surface-2 px-2 py-1.5 font-mono text-[12px] text-zinc-200 disabled:opacity-60"
              >
                {registry.map((v) => (
                  <option key={v.type} value={v.type}>
                    {v.type}
                  </option>
                ))}
              </select>
            </label>
            {isFileValidator ? (
              <label className="flex min-w-[160px] flex-1 flex-col gap-1">
                <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                  {validatorType === "command_result" ? "Run id (optional)" : "File path"}
                </span>
                <input
                  value={targetRef}
                  onChange={(e) => setTargetRef(e.target.value)}
                  placeholder={validatorType === "command_result" ? "(latest in this run)" : "src/app.py"}
                  disabled={disabled}
                  className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[12px] text-zinc-200 disabled:opacity-60"
                />
              </label>
            ) : null}
            <button
              type="button"
              disabled={disabled || busy}
              title={hintTitle}
              onClick={run}
              className="rounded-lg border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[12px] font-medium text-indigo-200 transition-colors hover:bg-indigo-500/25 disabled:opacity-40"
            >
              {busy ? "Running…" : "Run validator"}
            </button>
          </div>
          {!isFileValidator ? (
            <label className="flex flex-col gap-1">
              <span className="text-[10.5px] font-semibold uppercase tracking-wider text-zinc-500">
                Payload (JSON)
              </span>
              <textarea
                value={payloadText}
                onChange={(e) => setPayloadText(e.target.value)}
                rows={3}
                placeholder={PAYLOAD_HINT[validatorType] ?? "{}"}
                disabled={disabled}
                className="rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 font-mono text-[11px] text-zinc-200 disabled:opacity-60"
              />
            </label>
          ) : null}
          <p className="text-[10.5px] text-zinc-600">
            {registry.find((v) => v.type === validatorType)?.description}
          </p>
        </div>
      ) : null}

      {error ? <div className="mt-2"><ErrorNote message={error} /></div> : null}

      {/* Results */}
      {results.length === 0 ? (
        <p className="mt-3 text-[12px] text-zinc-600" data-testid="validators-empty">
          No validation results yet — run a validator to produce evidence-based results.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {results.slice(0, 8).map((result) => (
            <ResultCard key={result.result_id} result={result} />
          ))}
        </div>
      )}
    </Card>
  );
}

function ResultCard({ result }: { result: RuntimeValidatorResult }) {
  const isSecret = result.validator_type === "secret_exposure" && !result.passed;
  return (
    <div
      data-testid="validator-result"
      className={`rounded-lg border px-3 py-2.5 ${
        result.passed
          ? "border-edge bg-surface-0"
          : "border-red-400/30 bg-red-400/[0.04]"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span
          data-testid="result-badge"
          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
            result.passed
              ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
              : "border-red-400/40 bg-red-400/10 text-red-300"
          }`}
        >
          {result.passed ? "passed" : "failed"}
        </span>
        <span className="font-mono text-[11.5px] text-zinc-300">{result.validator_type}</span>
        {result.target_ref ? (
          <span className="truncate font-mono text-[11px] text-zinc-500">{result.target_ref}</span>
        ) : null}
        {result.risk_delta !== 0 ? (
          <span className="text-[10.5px] text-red-300/80">+{result.risk_delta.toFixed(2)} risk</span>
        ) : null}
        <span className="ml-auto shrink-0 font-mono text-[10px] text-zinc-600">
          {fmtClock(result.created_at)}
        </span>
      </div>

      {result.explanation ? (
        <p className="mt-1.5 text-[11.5px] text-zinc-400">{result.explanation}</p>
      ) : null}

      {isSecret ? (
        <>
          <p data-testid="secret-warning" className="mt-1 text-[11px] font-medium text-red-300/90">
            ⚠ Secret-like content detected — evidence below is redacted.
          </p>
          {Array.isArray((result.evidence as { findings?: unknown }).findings) ? (
            <div className="mt-1 space-y-0.5">
              {((result.evidence as { findings: Array<{ line: number; snippet: string }> }).findings).map(
                (f, i) => (
                  <pre
                    key={i}
                    className="overflow-x-auto rounded bg-surface-2 px-2 py-1 font-mono text-[10.5px] text-zinc-400"
                  >
                    line {f.line}: {f.snippet}
                  </pre>
                ),
              )}
            </div>
          ) : null}
        </>
      ) : null}

      {result.failures.length > 0 ? (
        <ul data-testid="result-failures" className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-red-300/80">
          {result.failures.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      ) : null}

      {result.suggested_action ? (
        <p data-testid="suggested-action" className="mt-1.5 text-[11px] text-amber-200/80">
          Suggested: {result.suggested_action}
        </p>
      ) : null}
    </div>
  );
}
