# AgentLab — Demo Walkthrough (Runtime v1)

A 5-minute tour of AgentLab using the built-in Bottle Shop demo. By the end
you'll have watched AI-style agents build a small website inside a governed
runtime, held a risky change for approval, validated the outputs, and
previewed the rendered site — all replayable.

## What AgentLab is

AgentLab is the **visual runtime, debugger, and safety control plane for
AI-built software**. It is *not* "AI builds an app." It is "AI builds an app
inside a controlled runtime where you can see, replay, debug, validate,
approve, quarantine, and govern what the AI is doing."

Claude / Codex / Cursor / Replit can *generate* code. AgentLab helps you
**understand, govern, and debug** what AI-built software is actually doing —
turning invisible agent work into visual, replayable, enforceable system
behavior.

## Run it locally

```bash
# API (terminal 1) — defaults to a local SQLite DB, no keys needed
cd apps/api && uvicorn app.main:app --reload --port 8000

# Web (terminal 2)
cd apps/web && npm install && npm run dev   # http://localhost:5173
```

Open <http://localhost:5173>. You land on the **home page** explaining
AgentLab in a few seconds, with two CTAs.

## Create the demo

Click **Try Bottle Shop Demo** (on the home page, or "Create Bottle Shop
Demo" on the Runtime page). AgentLab deterministically:

1. creates a workspace with the goal *"Build a simple bottle-selling website
   with product cards, cart behavior, and a mock checkout."*
2. adds five agents (Planner, UI, Backend/Data, Verifier, Safety Reviewer),
3. plans a five-task workflow and completes it,
4. initializes a sandbox and writes the site files through the real file
   service,
5. runs two safe commands (`ls`, `python3 --version`) through the command
   runner,
6. runs the deterministic validators, and
7. proposes a payment-file write that the enforcement gateway **holds for
   human approval**.

Each demo run creates a fresh workspace; nothing is hardcoded into the
generic runtime — the seed just orchestrates the existing services.

## Which panels to inspect

Start at the **Project Debugging** panel (the beginner-first Workspace Home):
it summarizes health (*Needs approval · Verification failed · Risky change*),
the recommended next action, recent changes, and the open issues — in plain
English, with links into the detail panels.

Then drill in:

| Panel | What it shows |
|---|---|
| **Files** | The generated site: `index.html`, `styles.css`, `app.js`, `products.json`, a test file, and docs. |
| **Commands** | The two governed, audited safe commands. |
| **Workflows** | Five tasks, assigned to agents, completed with plain-English results. |
| **Validators** | Four passing checks; **business_risk** flags the payment feature. |
| **Enforcement** | The allow decisions per write, plus the approval-required decision for the payment file. |
| **Approvals** | The **pending** `file.write: src/payment/checkout.js`. |
| **Website preview** | The rendered storefront (see below). |
| **Replay** | Step through the whole build, event by event. |

## The governance moment

Open the **Approvals** panel. The payment-file write is pending because it
touches a sensitive path. **Approve** it to resume the *exact* stored write
through the real file service (the v1.2/v1.3 safety re-runs); **deny** it to
keep it blocked. Either way the decision is recorded and replayable. This is
the heart of the demo: a risky action paused for a human, not silently
applied.

## Preview the website

On the workspace page, open the **Website preview** panel and click
**Open Website Preview**. AgentLab renders the generated Tidewater Bottle Co.
storefront — hero, product grid, working cart, mock checkout — right inside
the app.

The preview is **safe by construction**:

- it is **read-only** and serves *only* files that already exist inside this
  workspace's sandbox;
- every path goes through the same v1.2 path-safety checks as the Files panel
  — traversal, absolute paths, outside-root/symlink escapes, and secret-named
  files (`.env`, keys) are rejected before any disk access;
- only an allowlist of static web extensions is served (no arbitrary files);
- no host filesystem path is ever exposed;
- the page renders in a `sandbox="allow-scripts"` iframe, so its scripts run
  isolated in an opaque origin and cannot reach the parent app.

It is a **preview surface, not a host** — no dev server, no build, no
install, no deploy.

## What is intentionally not included

No autonomous coding agent, browser automation, live web research, package
installation, deployment/hosting, payment integration, real checkout, user
accounts, or a database-backed store. The demo's agents don't literally write
the code — a deterministic seed writes fixed file contents through the real
services and records results on the agents' behalf, so the demo is repeatable
and safe. The generated storefront is a static mock (its checkout prints a
message; no real payments, no network calls, no CDN, no secrets, no customer
data).

## Known limitations

- The demo is a **scripted seed**, not an autonomous build — it proves the
  control plane, not an AI that writes arbitrary code.
- The website preview is a local read-only preview, not hosting; the
  previewed page's cross-origin `fetch('products.json')` falls back to the
  in-file product data (the storefront still renders and the cart works).
- AgentLab is **local-first / single-node**: SQLite by default, in-process
  WebSocket fan-out, env-only BYOK keys, no multi-user auth.
