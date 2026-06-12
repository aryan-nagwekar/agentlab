import { useState } from "react";

import { api } from "../../lib/api";
import type { StudioAgent, StudioEdge } from "../../lib/types";
import { useAppStore } from "../../store/app";
import { SectionLabel } from "../ui";
import { ProviderSetupModal, isConfigurableProvider } from "../gateway/ProviderSetupModal";
import { ModeSwitcher } from "./ModeSwitcher";

/** Strings that look like provider API keys are never sent or stored. */
const KEY_LIKE = /(sk-[A-Za-z0-9_-]{10,}|AIza[A-Za-z0-9_-]{10,})/;

const KEY_WARNING =
  "This looks like an API key. For safety, use Settings → Model Gateway or /connect provider in Agent Mode.";
const SWITCH_TO_AGENT = "Switch to Agent Mode to perform this action.";

const QUESTION = /\?|^(why|what|how|explain|summarize|describe|tell|who|when|where)\b/i;
const ACTION =
  /\b(run|execute|start|launch|create|edit|delete|remove|add|modify|change|configure|connect|set|assign|save|build)\b/i;

interface Message {
  who: "you" | "agentlab";
  text: string;
}

interface AssistantPanelProps {
  workflowId?: string;
  workflowName?: string;
  agents?: StudioAgent[];
  edges?: StudioEdge[];
}

export function AssistantPanel({ workflowId, workflowName, agents, edges }: AssistantPanelProps) {
  const mode = useAppStore((s) => s.studioMode);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const [connectProvider, setConnectProvider] = useState<string | null>(null);

  const reply = (text: string) => setMessages((m) => [...m, { who: "agentlab", text }]);

  const latestRun = async () => {
    if (!workflowId) return null;
    const runs = await api.studioWorkflowRuns(workflowId);
    return runs[0] ?? null;
  };

  const answerChat = async (text: string): Promise<string> => {
    const lower = text.toLowerCase();
    if (/fail|error|wrong|broke/.test(lower)) {
      const run = await latestRun();
      if (!run) return "No runs yet — run the workflow first (Agent Mode), then I can explain it.";
      if (run.status !== "failed")
        return `The latest run (${run.run_id}) completed — nothing failed.`;
      const failures = await api.runEvents(run.run_id, { event_type: "run.failed" });
      const payload = (failures[0]?.payload ?? {}) as {
        failed_agents?: string[];
        skipped_agents?: string[];
      };
      return (
        `The latest run (${run.run_id}) failed. ` +
        `Failed agents: ${(payload.failed_agents ?? []).join(", ") || "unknown"}. ` +
        `Skipped downstream: ${(payload.skipped_agents ?? []).join(", ") || "none"}. ` +
        "Open Replay and jump to the error to step through it."
      );
    }
    if (/cost|token|expensive|spend/.test(lower)) {
      const run = await latestRun();
      if (!run) return "No runs yet, so no cost data. Run the workflow first.";
      const costs = await api.runCosts(run.run_id);
      return (
        `Latest run used ${costs.total_tokens} tokens (~$${costs.estimated_cost_usd.toFixed(4)}). ` +
        `Most expensive agent: ${costs.most_expensive_agent ?? "n/a"}; ` +
        `most token-heavy: ${costs.most_token_heavy_agent ?? "n/a"}. ` +
        "The Cost & Tokens tab has the full breakdown."
      );
    }
    if (/trust|risk|suspicious|quarantine/.test(lower)) {
      const run = await latestRun();
      if (!run) return "No runs yet — trust/risk scores are derived per run.";
      const risk = await api.runRiskSummary(run.run_id);
      return (
        `Latest run: average trust ${risk.avg_trust?.toFixed(2) ?? "n/a"}, average risk ` +
        `${risk.avg_risk?.toFixed(2) ?? "n/a"}; ${risk.suspicious_agents} suspicious and ` +
        `${risk.quarantined_agents} quarantined agent(s). Failures lower reliability without ` +
        "marking an agent malicious — only attack events do that."
      );
    }
    if (/replay|event|step/.test(lower)) {
      return (
        "Replay reconstructs the run event-by-event: open the run, pick the Replay tab, then " +
        "play/scrub or jump to errors, tool calls, and routing decisions. Studio runs replay " +
        "exactly like SDK runs."
      );
    }
    if (/workflow|agent|team|do\b|graph/.test(lower) && agents?.length) {
      const chain = agents.map((a) => `${a.name} (${a.role}, ${a.model_name})`).join(" → ");
      return (
        `“${workflowName ?? "This workflow"}” has ${agents.length} agents and ` +
        `${edges?.length ?? 0} connections: ${chain}. Each agent's prompt combines its role, ` +
        "system prompt, the workflow input, and upstream outputs."
      );
    }
    if (/next|improve|suggest/.test(lower)) {
      return (
        "Suggestions: run the workflow and check Cost & Tokens for the most expensive agent; " +
        "step through Replay to inspect hand-offs; tighten system prompts; or switch an agent " +
        "to a real provider via /connect in Agent Mode."
      );
    }
    return (
      "I can explain this workflow, summarize what the agents did, explain why a run failed, " +
      "break down cost/token usage, or describe trust/risk. For actions (run, edit, connect a " +
      "provider), switch to Agent Mode."
    );
  };

  const handleCommand = async (text: string): Promise<void> => {
    const [command, ...args] = text.trim().split(/\s+/);
    if (command === "/connect") {
      const provider = (args[0] ?? "").toLowerCase();
      if (!provider) {
        reply("Usage: /connect <gemini | openai | anthropic | ollama>");
        return;
      }
      if (!isConfigurableProvider(provider)) {
        reply(
          `Unknown provider ${provider}. I can connect: gemini, openai, anthropic, ollama. ` +
            "(The mock provider needs no key.)",
        );
        return;
      }
      setConnectProvider(provider);
      reply(
        `Opening secure setup for ${provider}. Paste the key only into the password field — ` +
          "never into this chat.",
      );
      return;
    }
    if (command === "/run") {
      if (!workflowId) {
        reply("Open a workflow first, then /run will execute it.");
        return;
      }
      reply("Running the workflow…");
      try {
        const result = await api.runStudioWorkflow(workflowId, {
          input: "Run this workflow with a representative input.",
        });
        reply(
          `Run ${result.status}: ${result.run_id}. Open it at ${result.open_run_url} for the ` +
            "graph, Replay, and Cost & Tokens.",
        );
      } catch (e) {
        reply(`Run failed to start: ${e instanceof Error ? e.message : String(e)}`);
      }
      return;
    }
    reply("Commands: /connect <provider> · /run");
  };

  const send = async () => {
    const text = input.trim();
    if (!text) return;
    setWarning(null);

    // Hard rule, both modes: key-like strings never enter the transcript.
    if (KEY_LIKE.test(text)) {
      setWarning(KEY_WARNING);
      return;
    }

    setInput("");
    setMessages((m) => [...m, { who: "you", text }]);

    if (text.startsWith("/")) {
      if (mode === "chat") {
        reply(SWITCH_TO_AGENT);
        return;
      }
      await handleCommand(text);
      return;
    }

    if (mode === "chat" && ACTION.test(text) && !QUESTION.test(text)) {
      reply(SWITCH_TO_AGENT);
      return;
    }

    try {
      reply(await answerChat(text));
    } catch (e) {
      reply(`I couldn't fetch that: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Assistant</SectionLabel>
        <ModeSwitcher />
      </div>
      <p className="text-[10.5px] leading-4 text-zinc-600">
        {mode === "chat"
          ? "Chat Mode — questions and explanations only; no project actions."
          : "Agent Mode — /connect <provider> opens secure setup; /run executes this workflow."}{" "}
        Never paste API keys into chat.
      </p>
      <div className="max-h-56 space-y-2 overflow-y-auto" data-testid="assistant-transcript">
        {messages.map((message, index) => (
          <div
            key={index}
            className={
              message.who === "you"
                ? "ml-6 rounded-lg border border-indigo-400/20 bg-indigo-500/10 px-2.5 py-1.5 text-[12px] leading-5 text-zinc-200"
                : "mr-6 rounded-lg border border-edge bg-surface-2 px-2.5 py-1.5 text-[12px] leading-5 text-zinc-300"
            }
          >
            {message.text}
          </div>
        ))}
      </div>
      {warning ? (
        <div
          role="alert"
          className="rounded-md border border-red-400/30 bg-red-400/10 px-2.5 py-2 text-[11.5px] leading-5 text-red-300"
        >
          {warning}
        </div>
      ) : null}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
          placeholder={mode === "chat" ? "Ask about this workflow…" : "Message or /connect gemini…"}
          aria-label="Assistant message"
          className="min-w-0 flex-1 rounded-lg border border-edge bg-surface-0 px-2.5 py-1.5 text-[12.5px] text-zinc-200"
        />
        <button
          type="button"
          onClick={() => void send()}
          className="rounded-lg border border-edge bg-surface-2 px-3 py-1.5 text-[12px] font-medium text-zinc-300 transition-colors hover:bg-surface-1"
        >
          Send
        </button>
      </div>
      {connectProvider ? (
        <ProviderSetupModal
          provider={connectProvider}
          onClose={() => setConnectProvider(null)}
        />
      ) : null}
    </div>
  );
}
