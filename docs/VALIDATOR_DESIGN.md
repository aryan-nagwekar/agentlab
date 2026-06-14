# AgentLab Validator Design

Deterministic validators (v1.8, `app/runtime/validators.py`) let AgentLab stop
blindly trusting agent outputs. Every validator is a **pure, deterministic
function** — no LLM judgment, no web browsing, no live external fetch, no
arbitrary code execution.

## Result model

Running a validator produces a `ValidatorResult` (`runtime_validator_results`):
`validator_type`, `target_type`, `target_ref` (a safe logical reference, never a
host path), `passed`, `confidence`, bounded `evidence`, `failures`,
`suggested_action`, `risk_delta`/`trust_delta`, and a plain-English explanation.

Flow: `validator.started` → optional signal events → `validation.passed` /
`validation.failed` → `validator.completed`. Running with a `task_id` stamps the
task's `validation_status` metadata (no scheduler change).

## Evidence and redaction

Evidence is **bounded** (snippets ≤ 200 chars, ≤ 10 items) and **redacted**.
The secret-exposure validator detects api keys, private-key headers, and `.env`
assignments, but every captured snippet passes through the same redactor before
storage — a finding is reported as `API_KEY = "[redacted]"`, never the raw
secret. The raw secret never reaches the DB, events, API, or UI (a test plants a
key and greps all three for zero occurrences). No host path appears in any
result or event.

## Current validators

| Validator | Checks | Passes / fails on |
|---|---|---|
| `secret_exposure` | a workspace file or inline content | fails on secret-like patterns; evidence redacted |
| `code_syntax` | `.py` via `ast.parse`, `.json`/`package.json` via `json.loads` | no code runs; fails on syntax errors / missing `name`/`version` |
| `command_result` | the latest recorded v1.3 command event | exit 0 = pass; failed/timed-out = fail; *consumes* events, never re-runs |
| `research_claim` | a structured claim vs **provided** cited evidence | fails on missing `source_url`, missing required fields, or unsupported claim |
| `data_flow` | a consumer's expected fields vs a producer's actual fields | fails on missing/type-mismatched fields, with a plain-English explanation |
| `business_risk` | a change/claim's metadata | flags payment/auth/deploy/customer-data/unverified → requires approval/validation |

## What validators can prove — and what they cannot

**Can:** that a file contains a secret-like pattern; that Python/JSON parses;
that a recorded command exited 0; that a *provided* claim cites a URL and the
required fields and that the claim text appears in the supplied evidence; that
two *provided* field contracts match; that a change touches a business-critical
domain.

**Cannot (not omniscient):**
- They do **not** browse the web or fetch URLs — `research_claim` validates only
  the evidence you give it, so a fabricated-but-internally-consistent evidence
  blob can pass.
- `code_syntax` is a parser, **not** a type-checker, linter, or static analyzer
  — valid syntax is not correct logic.
- `command_result` trusts the recorded exit code; it does not re-run or sandbox-
  verify the command.
- `data_flow` compares the contracts you supply, not the real code/schema.
- A passing validator is **evidence of a specific property, not a correctness
  guarantee**.

## Integration

- **Enforcement (narrow):** the `block-failed-validation` rule (v1.5 registry,
  priority 16) blocks an action whose proposal metadata is tagged
  `validation_failed`. Validators do not auto-block unrelated future actions.
- **Trust/Risk:** results carry `risk_delta`/`trust_delta` as **scoring
  signals**; the deterministic v0.5 trust/risk fold is intentionally **not**
  modified to consume them (so the safety-critical scoring path stays a pure,
  reviewed function).

## Routes

`GET /api/runtime/validators` (registry) · `POST …/validators/run` (gated) ·
`GET …/validators/results[/{id}]`.
