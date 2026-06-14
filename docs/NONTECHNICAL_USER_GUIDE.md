# AgentLab — Nontechnical User Guide

A plain-English tour. You don't need to read code or stack traces to understand
what AgentLab is showing you.

## What AgentLab is

AI tools can *generate* software fast — but you often can't tell what changed,
why something broke, which agent caused it, or whether a change is safe to keep.
**AgentLab is the place where AI builds software while you watch, understand, and
stay in control.** It records every action, holds risky ones for your approval,
checks outputs, and lets you replay the whole thing.

It is **not** "AI builds an app." It is "AI builds an app inside a controlled
runtime where you can see, understand, debug, validate, and govern what the AI is
doing."

## The home page

When you open AgentLab you land on a homepage that explains it in a few seconds,
with two buttons: **Try Bottle Shop Demo** and **Open Runtime**. The fastest way
to understand AgentLab is to click the demo.

## Create the Bottle Shop demo

Click **Try Bottle Shop Demo**. AgentLab builds a small bottle-selling website
inside a safe workspace: it sets up agents, plans the work, writes the website
files, runs a couple of safe checks, validates the outputs, and **pauses on one
risky change** (a payment file) to ask for your approval. Every run is the same —
it's a guided, repeatable demo.

## Reading Project Debugging

The **Project Debugging** panel at the top of the workspace is your home base. It
tells you, in plain language:

- **Project health** — e.g. *Needs approval*, *Verification failed*, *Risky
  change*, or *Safe to continue*.
- **What to do next** — e.g. "Review 1 pending approval".
- **What changed recently** — files written, commands run, decisions made.
- **What needs attention** — the open issues, each with a plain-English reason.

You don't have to understand the details to know the state of the project.

## Preview the generated website

On the workspace page, open the **Website preview** panel and click **Open
Website Preview**. You'll see the actual rendered storefront — hero, products,
cart, and a mock checkout — inside AgentLab. It's read-only and safe.

## Approve or deny risky actions

Open the **Approvals** panel. The payment change is waiting because it touches
something sensitive. You decide:

- **Approve** — the exact change is applied (and re-checked for safety).
- **Deny** — the change stays blocked and never happens.

This is the heart of AgentLab: risky things pause for a human instead of being
applied silently.

## Replay what happened

Anywhere you see **Replay this** or **Open activity run**, you can step through
everything that happened — every file, command, decision, and approval — like
rewinding a recording. If something looks wrong, replay shows you exactly when
and why.

## What the limitations mean (in plain English)

- AgentLab **reduces risk; it does not guarantee perfect software.** It catches
  many problems, not all of them.
- Its **validators check evidence, not truth** — they can confirm a file parses
  or a claim cites its sources, but they can't know everything.
- The demo is a **guided, repeatable script**, not a fully autonomous engineer
  writing arbitrary code.
- The **website preview is a local preview, not a published website** — nothing
  is deployed to the internet.
- **High-risk actions need your approval** — that's by design.
- For real production use, software still needs stronger isolation than this
  local demo mode provides.

## Where to go next

- [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) — the same tour, with more detail.
- [BOTTLE_SHOP_DEMO.md](BOTTLE_SHOP_DEMO.md) — what the demo proves.
