import { Badge, Card, PageHeader, SectionLabel } from "../components/ui";

const FAULTS = [
  { id: "kill_agent", label: "Kill agent", description: "Terminate a running agent mid-task" },
  { id: "delay_messages", label: "Delay messages", description: "Add latency to a channel" },
  { id: "drop_messages", label: "Drop messages", description: "Randomly drop a % of messages" },
  { id: "corrupt_message", label: "Corrupt message", description: "Mutate a payload in flight" },
  { id: "force_tool_failure", label: "Force tool failure", description: "Make a tool call fail" },
  { id: "simulate_model_timeout", label: "Model timeout", description: "Simulate a hung model call" },
  { id: "overload_agent", label: "Overload agent", description: "Flood an agent with tasks" },
];

const ATTACKS = [
  { id: "inject_malicious_agent", label: "Inject malicious agent" },
  { id: "prompt_injection_message", label: "Prompt-injection message" },
  { id: "data_exfiltration_attempt", label: "Data exfiltration attempt (mock)" },
  { id: "fake_capability_advertising", label: "Fake capability advertising" },
  { id: "trust_poisoning", label: "Trust poisoning" },
  { id: "high_frequency_spam", label: "High-frequency spam" },
];

export function LabPage() {
  return (
    <>
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
            Fault Injection Lab <Badge className="border-amber-400/40 bg-amber-400/10 text-amber-300">arrives in v0.3</Badge>
          </span>
        }
        subtitle="Chaos-test agent systems: inject faults and simulated attacks, watch the topology react"
      />

      <Card className="mb-6 border-indigo-400/20 bg-indigo-500/5 px-5 py-4 text-[13px] leading-6 text-zinc-400">
        Lab Mode ships in <span className="font-medium text-zinc-200">v0.3 (Phase 4)</span>,
        after the replay debugger. The event schema already accepts{" "}
        <code className="font-mono text-[12px] text-indigo-300">fault.injected</code>,{" "}
        <code className="font-mono text-[12px] text-indigo-300">attack.injected</code> and{" "}
        <code className="font-mono text-[12px] text-indigo-300">agent.quarantined</code>, and the
        topology can already render <span className="text-purple-300">quarantined</span> and{" "}
        <span className="text-orange-300">overloaded</span> agents — the controls below activate
        once Lab Mode lands. All attack scenarios are sandboxed simulations with mock data only.
      </Card>

      <SectionLabel>Planned fault injections</SectionLabel>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {FAULTS.map((fault) => (
          <Card key={fault.id} className="px-4 py-3 opacity-70">
            <div className="text-[13px] font-medium text-zinc-300">{fault.label}</div>
            <div className="mt-0.5 text-[12px] text-zinc-600">{fault.description}</div>
            <button
              type="button"
              disabled
              className="mt-3 cursor-not-allowed rounded-md border border-edge bg-surface-2 px-2.5 py-1 text-[11px] text-zinc-600"
            >
              Inject (v0.3)
            </button>
          </Card>
        ))}
      </div>

      <SectionLabel>Planned attack simulations (sandboxed)</SectionLabel>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {ATTACKS.map((attack) => (
          <Card key={attack.id} className="px-4 py-3 opacity-70">
            <div className="text-[13px] font-medium text-zinc-300">{attack.label}</div>
            <button
              type="button"
              disabled
              className="mt-3 cursor-not-allowed rounded-md border border-rose-400/20 bg-rose-400/5 px-2.5 py-1 text-[11px] text-rose-300/50"
            >
              Simulate (v0.3)
            </button>
          </Card>
        ))}
      </div>
    </>
  );
}
