# AgentLab — Privacy & Security

AgentLab is **local-first by design**. This document states what data it
handles, the security controls it enforces, and — honestly — what it does
**not** guarantee. Companion docs: [BYOK_AND_SECRETS.md](BYOK_AND_SECRETS.md),
[SANDBOX_SAFETY.md](SANDBOX_SAFETY.md),
[ENFORCEMENT_POLICY.md](ENFORCEMENT_POLICY.md),
[HUMAN_APPROVAL.md](HUMAN_APPROVAL.md).

---

## Privacy

### Local-first

By default AgentLab runs on your machine. Workspaces, generated project files,
runtime events, validation results, approvals, quarantine history, and replay
data are stored **locally** (SQLite + the gitignored `.agentlab-workspaces/`
folder) unless you deploy or modify the system. There is no telemetry phone-home
and no intentional collection of personal data.

### Minimum-necessary data

AgentLab follows a "collect only what you need" posture. It records the metadata
needed to observe, debug, and govern a run — not your personal information.

### What logs / replay may contain

Event and replay payloads may contain: workspace/run/agent IDs, **logical**
(workspace-relative) file paths, command display strings and exit codes, model-call
metadata (provider/model/token counts), validation results, enforcement
decisions, and approval decisions. They are designed to **exclude** raw secrets,
file contents, full command output, and host filesystem paths (see Security
controls below).

### Your responsibilities

- Do **not** put real credentials, real customer data, or regulated data into
  demo projects or workspaces.
- API keys are user-provided (BYOK) and **must not be committed** —
  `.env` and `.agentlab-secrets.json` are gitignored.
- Treat the local database and the server's own application logs as sensitive
  stores and protect/dispose of them like any other (events redact secrets, but
  you control the host).

### If hosted later

These terms assume local/single-user operation. A hosted, multi-tenant
deployment would require updated privacy terms, stronger isolation, per-user key
management, retention/deletion policy, and access controls — none of which are
part of the local-first v1.

---

## Security model

AgentLab reduces risk through **layered, deterministic controls**, each enforced
*before* execution and each proven by tests.

| Control | Mechanism | Proof (test) |
|---|---|---|
| Sandbox boundaries | `check_path` rejects absolute/traversal/outside-root/symlink/secret paths before disk access | `test_outside_root_symlink_blocked`, `test_secret_file_blocked` |
| Allowlisted commands | structured argv, `shell=False`, allowlist-first; dangerous/install/network/metachar blocked pre-spawn | `test_blocked_commands_never_execute` |
| Policy enforcement | 24-rule registry evaluates every important action; first match decides | `test_enforcement.py` |
| Human approvals | high-risk actions halt and store the exact payload until a human resolves them | `test_approve_resumes_exact_stored_file_write` |
| Real quarantine | a quarantined agent's file/command/task actions are refused pre-execution | `test_quarantined_agent_file_write_blocked_before_execution` |
| Deterministic validators | secrets / syntax / command results / data-flow / business risk, evidence-based | `test_validators.py` |
| Secret redaction | command output, validator evidence, and BYOK hints are redacted everywhere | `test_secret_exposure_fail_redacts_secret_everywhere`, `test_configured_key_never_leaks_into_events_or_errors` |
| No host-path leakage | only logical workspace paths leave the server | `test_no_host_path_leaks_in_preview`, `test_no_host_paths_in_approval_events` |
| Safe local preview | read-only, sandbox-bounded, static-extension allowlist, GET-only, sandboxed iframe | `test_preview.py` |
| Replay/audit history | every decision emits an event so the full history is reconstructable | replay folds the activity run |

### Honest limitations

- AgentLab **reduces** risk but **cannot guarantee perfect correctness.**
- Validators are **evidence-based, not omniscient** — they confirm a property,
  not truth, and do not browse the web.
- **LLM verifiers can be wrong**; safety-critical decisions are deterministic and
  an LLM is never the sole authority for blocking/allowing.
- **Sandbox isolation depends on deployment mode.** v1 is application-level (path
  + command safety in-process), **not** OS/container/VM isolation; local
  development isolation is weaker than production.
- **BYOK keys must be handled carefully** — see
  [BYOK_AND_SECRETS.md](BYOK_AND_SECRETS.md).
- **External research validation may be incomplete.**
- **Human approval is required for high-risk actions** by design.
- Event payloads redact secrets, but you must still **protect the server's own
  logs and the local database** from unauthorized access or tampering.

---

## Security engineering checklist

These are the properties AgentLab can demonstrate, each tied to a test
(`make test`):

- [x] No raw API keys in events/errors — `test_configured_key_never_leaks_into_events_or_errors`, `test_no_raw_key_in_provider_list`
- [x] No raw secrets in events/replay — `test_secrets_redacted_in_approval`, `test_secret_like_output_is_redacted`
- [x] No host paths in API responses — `test_no_host_path_leaks_in_preview`, `test_no_host_paths_in_validation_events`, `test_no_secrets_or_host_paths_in_quarantine_events`
- [x] Preview blocks traversal (`../../`) and `.env` — `test_absolute_path_blocked`, `test_secret_file_blocked`, `test_outside_root_symlink_blocked`
- [x] Command runner blocks `rm -rf` / `curl` / `wget` / `npm install` / shell metacharacters — `test_blocked_commands_never_execute`
- [x] Scrubbed command environment (host env/secrets never reach the child) — `test_host_environment_is_scrubbed`
- [x] Approval-required action does not execute before approval — `test_deny_file_write_leaves_disk_unchanged`
- [x] Quarantined agent cannot write files / run commands — `test_quarantined_agent_file_write_blocked_before_execution`, `test_quarantined_agent_command_blocked_before_execution`
- [x] Validators do not store raw secrets — `test_secret_exposure_fail_redacts_secret_everywhere`
- [x] Demos/tests need no real keys — `test_default_demo_works_without_any_keys`
- [x] Docs state local sandboxing is not production-grade isolation — this doc + [SANDBOX_SAFETY.md](SANDBOX_SAFETY.md)

This follows the spirit of the **NIST SSDF** (secure practices integrated into the
development lifecycle, not bolted on) and **OWASP** logging/secrets guidance.

---

## Responsible disclosure

AgentLab is a local-first project. If you find a security issue, please **do not
open a public issue with exploit details**. Instead, report it privately to the
maintainer (the git commit author / repository owner) with a description, repro
steps, and impact. We aim to acknowledge reports promptly and fix verified issues
before any public disclosure.

---

## Acceptable use

- Use AgentLab to build, observe, debug, validate, and govern **your own**
  software projects.
- Do **not** use it to process real customer/regulated data, run real payment
  flows, or attempt to bypass its sandbox/enforcement controls.
- The Bottle Shop demo is **mock-only**: no Stripe/PayPal, no real checkout, no
  real customer information.
- Respect provider terms when using BYOK keys.
