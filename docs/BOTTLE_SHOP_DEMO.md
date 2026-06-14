# Bottle Shop — End-to-End Runtime Demo (v2.0)

A one-click, deterministic demo that proves AgentLab is **not** "AI builds an
app" but "AI builds an app inside a controlled runtime where you can see,
understand, debug, validate, replay, approve, and govern what happened."

It builds a small, dependency-free storefront for the *fictional* **Tidewater
Bottle Co.** inside a real workspace sandbox — and every step flows through an
existing AgentLab system and emits the normal events.

## What it proves

The demo exercises, end to end, the systems shipped in v1.0–v1.9:

| System | What the demo does |
| --- | --- |
| Runtime Workspace (v1.0) | Creates `Tidewater Bottle Shop (demo)` with a clear goal, tagged `metadata.demo = "bottle_shop"` |
| Sandboxed File Runtime (v1.2) | Initializes a real sandbox; all files live under it |
| Workspace Agents (v1.1) | Six agents — Planner, Researcher, Backend Coder, UI Agent, Verifier, Safety Reviewer |
| Orchestration Engine (v1.4) | A five-task workflow, auto-assigned to agents and walked to completion |
| Enforcement Gateway (v1.5) | Every file write and command is proposed → evaluated → executed |
| Safe Command Runner (v1.3) | Runs `ls` and `python3 --version` through the allowlist |
| Deterministic Validators (v1.8) | Runs code-syntax, secret-exposure, command-result, data-flow, and business-risk |
| Human Approval System (v1.6) | One payment-path write is **held for your approval** |
| Project Debugging UI (v1.9) | Summarizes health, next action, issues, and the project map |
| Replay / Activity | The whole build is reconstructable event-by-event |

## How to run it

- **UI:** Runtime → "Create Bottle Shop Demo" card → **Create Bottle Shop Demo**.
  You land on the new workspace.
- **API:** `POST /api/runtime/demo/bottle-shop` (behind `X-API-Key` when keys
  are configured). The response includes `workspace_id`, `workflow_id`, the
  validator result ids, and the `pending_approval_id`.

It is deterministic and repeatable — the same goal, agents, file contents, and
governance halt every run.

## What to inspect

Open the new workspace and start at the **Project debugging** panel — it reads
`Needs approval` with `Verification failed` and `Risky change` chips, lists the
two issues in plain English, and recommends "Review 1 pending approval".

Then drill into the panels:

- **Files** — the generated site: `README.md`, `index.html`, `styles.css`,
  `app.js`, `products.json`, `tests/bottle_shop.test.js`, `docs/demo-notes.md`.
- **Commands** — `ls` and `python3 --version`, both governed and audited.
- **Workflows** — five tasks, all completed, with plain-English results.
- **Validators** — four pass; **business_risk** flags the payment/checkout
  feature with a suggested action.
- **Enforcement** — the allow decisions for each write, plus the approval-
  required decision for the payment file.
- **Approvals** — the **pending** `file.write: src/payment/checkout.js`.
- **Website preview** (v2.1) — click **Open Website Preview** to render the
  generated Tidewater Bottle Co. storefront inside AgentLab: hero, the
  product grid, a working cart, and the mock checkout. The preview is
  read-only and served only from the workspace sandbox (see
  [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) for the safety model).
- **Replay** — step through everything that happened.

## The governance moment

The Backend Coder agent attempts to wire real payment code
(`src/payment/checkout.js`). Because the path is payment-sensitive, the
enforcement gateway **holds it for human approval** — the file is *not*
written. In the Approvals panel you can:

- **Approve** → the exact stored write resumes through the v1.2 file service
  (the file appears in Files, and health clears).
- **Deny** → it stays blocked and the file is never written.

This is the whole point of the demo: a risky action paused, explained, and put
in your hands — fully replayable.

## Safety & scope

The demo writes **no secrets**, makes **no network calls**, uses **no external
CDN**, installs **no packages**, runs **no server**, handles **no real
payments**, and stores **no customer data**. The storefront's checkout is a
mock that prints a message. Tests assert that no host filesystem path and no
secret-shaped token ever appears in the API response, events, debug summary, or
validator evidence.

## Intentionally **not** included

No autonomous coding agent, browser automation, live web research, package
installation, cloud deploy, payment integration, real checkout, user accounts,
database-backed commerce, or any new runtime engine. The demo is an isolated
seed (`apps/api/app/runtime/demo_bottle_shop.py`) that orchestrates existing
services — it adds no behavior to the generic runtime.
