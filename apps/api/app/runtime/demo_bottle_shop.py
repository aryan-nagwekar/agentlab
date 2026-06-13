"""Bottle-Selling Website end-to-end demo (v2.0).

This is NOT a new runtime engine. It is an isolated, deterministic seed that
proves the existing AgentLab runtime can guide, govern, debug, validate, and
replay the construction of a small real project — a dependency-free
"Tidewater Bottle Co." storefront built inside a workspace sandbox.

Every step reuses an existing service and emits the normal events, so the
Files / Commands / Workflows / Enforcement / Approvals / Validators / v1.9
Project Debugging panels and Replay all light up for free:

  workspace + sandbox (v1.0/v1.2) → agents (v1.1) → workflow + tasks (v1.4)
  → file writes through the enforcement gateway (v1.5) → safe commands (v1.3)
  → deterministic validators (v1.8) → one approval-required governance halt
  that the user resolves in the UI (v1.6) → v1.9 health summary.

Nothing here installs packages, runs a server, deploys, makes network calls,
handles real payments, or stores secrets/customer data. The only governance
"failure" is intentional and benign: a payment-path file write is held for
human approval, and the business-risk validator flags the checkout feature.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .. import models as core_models
from . import approvals, commands, enforcement, orchestration, sandbox, service, validators
from .models import Workspace
from .sandbox import SandboxBlocked
from .schemas import AgentDefinitionIn

DEMO_KIND = "bottle_shop"
DEMO_GOAL = (
    "Build a simple bottle-selling website with product cards, cart behavior, "
    "and a mock checkout."
)

# --- The website (dependency-free, fictional brand, no secrets/network/CDN) ---

_README = """\
# Tidewater Bottle Co. — Demo Storefront

A tiny, dependency-free storefront for a *fictional* reusable-bottle brand,
built by AgentLab's runtime as an end-to-end demo.

## What it is
- Static HTML/CSS/JS — no build step, no packages, no network calls.
- Product data lives in `products.json` (with an in-file fallback in `app.js`
  so it works when opened directly).
- Add-to-cart + cart count + a mock checkout summary. **No real payments.**

## View it
Open `index.html` directly, or serve the folder:

    python3 -m http.server 8080

Then visit http://localhost:8080.

## Files
- `index.html` — semantic, accessible markup (hero, product grid, cart, mock checkout)
- `styles.css` — responsive styling
- `app.js` — cart logic + product rendering
- `products.json` — product data (id, name, price_cents, image_alt, blurb)
- `tests/bottle_shop.test.js` — illustrative dependency-free assertions
- `docs/demo-notes.md` — what AgentLab exercised while building this
"""

_PRODUCTS_JSON = """\
{
  "products": [
    {"id": "tide-500", "name": "Tidewater 500ml", "price_cents": 2400,
     "image_alt": "Matte teal 500ml insulated bottle", "blurb": "Everyday carry, keeps drinks cold 24h."},
    {"id": "harbor-750", "name": "Harbor 750ml", "price_cents": 2900,
     "image_alt": "Brushed steel 750ml bottle with loop cap", "blurb": "For longer days; leak-proof loop cap."},
    {"id": "cove-350", "name": "Cove 350ml", "price_cents": 1900,
     "image_alt": "Compact sand-colored 350ml bottle", "blurb": "Pocketable size for short trips."},
    {"id": "reef-1l", "name": "Reef 1L", "price_cents": 3400,
     "image_alt": "Deep blue 1 litre wide-mouth bottle", "blurb": "Wide mouth, fits ice cubes easily."}
  ]
}
"""

_INDEX_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tidewater Bottle Co.</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <header class="hero">
    <h1>Tidewater Bottle Co.</h1>
    <p>Reusable bottles for everyday adventures. Mock store — no real checkout.</p>
    <button id="cart-toggle" aria-label="View cart" aria-expanded="false">
      Cart (<span id="cart-count">0</span>)
    </button>
  </header>

  <main>
    <section aria-labelledby="products-heading">
      <h2 id="products-heading">Our bottles</h2>
      <ul id="product-grid" class="grid"></ul>
    </section>

    <section id="cart" aria-labelledby="cart-heading" hidden>
      <h2 id="cart-heading">Your cart</h2>
      <ul id="cart-items"></ul>
      <p class="cart-total">Total: <strong id="cart-total">$0.00</strong></p>
      <button id="checkout" type="button">Mock checkout</button>
      <p id="checkout-message" role="status"></p>
    </section>
  </main>

  <footer><p>Demo storefront built and governed inside AgentLab.</p></footer>
  <script src="app.js"></script>
</body>
</html>
"""

_STYLES_CSS = """\
:root { --ink: #16242b; --sea: #2b7a78; --sand: #f7f3ec; --line: #d8d2c6; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; color: var(--ink); background: var(--sand); }
.hero { padding: 2rem 1.25rem; background: var(--sea); color: #fff; display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; }
.hero h1 { margin: 0; font-size: 1.6rem; }
.hero p { margin: 0; flex: 1 1 240px; opacity: .9; }
button { font: inherit; cursor: pointer; border: 1px solid var(--ink); background: #fff; color: var(--ink); border-radius: 8px; padding: .5rem .9rem; }
button:focus-visible { outline: 3px solid #ffd166; outline-offset: 2px; }
main { max-width: 880px; margin: 0 auto; padding: 1.25rem; }
.grid { list-style: none; padding: 0; margin: 0; display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
.card { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; gap: .4rem; }
.card .swatch { height: 90px; border-radius: 8px; background: var(--sea); opacity: .85; }
.card h3 { margin: .2rem 0 0; font-size: 1rem; }
.card .price { font-weight: 700; }
.card .blurb { font-size: .85rem; opacity: .8; flex: 1; }
#cart { margin-top: 1.5rem; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 1rem; }
#cart-items { list-style: none; padding: 0; }
.cart-total { font-size: 1.1rem; }
"""

_APP_JS = """\
// Tidewater Bottle Co. — dependency-free cart logic. No network required:
// products load from products.json when served, with an in-file fallback.
const FALLBACK_PRODUCTS = [
  { id: "tide-500", name: "Tidewater 500ml", price_cents: 2400, image_alt: "Matte teal 500ml insulated bottle", blurb: "Everyday carry, keeps drinks cold 24h." },
  { id: "harbor-750", name: "Harbor 750ml", price_cents: 2900, image_alt: "Brushed steel 750ml bottle with loop cap", blurb: "For longer days; leak-proof loop cap." },
  { id: "cove-350", name: "Cove 350ml", price_cents: 1900, image_alt: "Compact sand-colored 350ml bottle", blurb: "Pocketable size for short trips." },
  { id: "reef-1l", name: "Reef 1L", price_cents: 3400, image_alt: "Deep blue 1 litre wide-mouth bottle", blurb: "Wide mouth, fits ice cubes easily." },
];

const cart = new Map();
const money = (cents) => `$${(cents / 100).toFixed(2)}`;

async function loadProducts() {
  try {
    const res = await fetch("products.json");
    if (res.ok) return (await res.json()).products;
  } catch (_e) { /* opened from file:// — use the fallback */ }
  return FALLBACK_PRODUCTS;
}

function renderProducts(products) {
  const grid = document.getElementById("product-grid");
  grid.innerHTML = "";
  for (const p of products) {
    const li = document.createElement("li");
    li.className = "card";
    li.innerHTML =
      `<div class="swatch" role="img" aria-label="${p.image_alt}"></div>` +
      `<h3>${p.name}</h3><span class="price">${money(p.price_cents)}</span>` +
      `<p class="blurb">${p.blurb}</p>`;
    const add = document.createElement("button");
    add.type = "button";
    add.textContent = "Add to cart";
    add.addEventListener("click", () => addToCart(p));
    li.appendChild(add);
    grid.appendChild(li);
  }
}

function addToCart(product) {
  const line = cart.get(product.id) || { product, qty: 0 };
  line.qty += 1;
  cart.set(product.id, line);
  renderCart();
}

function renderCart() {
  const count = [...cart.values()].reduce((n, l) => n + l.qty, 0);
  document.getElementById("cart-count").textContent = String(count);
  const items = document.getElementById("cart-items");
  items.innerHTML = "";
  let total = 0;
  for (const { product, qty } of cart.values()) {
    total += product.price_cents * qty;
    const li = document.createElement("li");
    li.textContent = `${product.name} × ${qty} — ${money(product.price_cents * qty)}`;
    items.appendChild(li);
  }
  document.getElementById("cart-total").textContent = money(total);
}

document.getElementById("cart-toggle").addEventListener("click", (e) => {
  const cartEl = document.getElementById("cart");
  const open = cartEl.hasAttribute("hidden");
  if (open) cartEl.removeAttribute("hidden"); else cartEl.setAttribute("hidden", "");
  e.currentTarget.setAttribute("aria-expanded", String(open));
});

document.getElementById("checkout").addEventListener("click", () => {
  const count = [...cart.values()].reduce((n, l) => n + l.qty, 0);
  document.getElementById("checkout-message").textContent =
    count === 0 ? "Your cart is empty." : `Mock checkout complete — ${count} bottle(s). No payment was taken.`;
});

loadProducts().then(renderProducts);
"""

_TEST_JS = """\
// Illustrative dependency-free assertions for the cart math. Not executed by
// the demo (AgentLab does not install packages or run a JS test harness); it
// documents the intended behavior and is here to be inspected.
function money(cents) { return `$${(cents / 100).toFixed(2)}`; }
function cartTotal(lines) { return lines.reduce((n, l) => n + l.price_cents * l.qty, 0); }

const tests = [
  () => money(2400) === "$24.00" || fail("money(2400)"),
  () => cartTotal([{ price_cents: 2400, qty: 2 }, { price_cents: 1900, qty: 1 }]) === 6700 || fail("cartTotal"),
  () => cartTotal([]) === 0 || fail("empty cart"),
];
function fail(name) { throw new Error("FAILED: " + name); }
tests.forEach((t) => t());
console.log("bottle_shop: all assertions passed");
"""

_DEMO_NOTES = """\
# What AgentLab exercised building this

This storefront was assembled by a deterministic AgentLab runtime demo. While
building it, the platform exercised — and recorded as replayable events:

- A **Runtime Workspace** + a real **sandbox** the files live in.
- Six **workspace agents** (Planner, Researcher, Backend Coder, UI Agent,
  Verifier, Safety Reviewer).
- A **workflow** with five tasks, assigned to agents and walked to completion.
- File writes routed through the **enforcement gateway** (each allowed before
  it executed).
- Safe **commands** through the allowlisted command runner.
- Deterministic **validators** (code syntax, secret exposure, command result,
  data flow, business risk).
- One **governance halt**: an attempt to write payment-path code was held for
  **human approval** — open the Approvals panel to approve or deny it.

Open the **Project debugging** panel for the at-a-glance health summary, then
**Replay** to step through everything that happened.
"""

# path → contents. Order matters only for readability; writes are independent.
WEBSITE_FILES: dict[str, str] = {
    "README.md": _README,
    "products.json": _PRODUCTS_JSON,
    "index.html": _INDEX_HTML,
    "styles.css": _STYLES_CSS,
    "app.js": _APP_JS,
    "tests/bottle_shop.test.js": _TEST_JS,
    "docs/demo-notes.md": _DEMO_NOTES,
}

# Six agents. The first five roles match the deterministic planner's step
# keywords (plan / research / backend / ui / verif) so every task is assigned;
# the Safety Reviewer rounds out the governance story.
_AGENTS: list[dict[str, Any]] = [
    {"name": "Planner", "role": "Planner",
     "description": "Breaks the goal into a build plan and task structure."},
    {"name": "Researcher", "role": "Researcher",
     "description": "Gathers product/catalog data the build depends on."},
    {"name": "Backend Coder", "role": "Backend Coder",
     "description": "Builds data and core logic; payment-adjacent changes need approval."},
    {"name": "UI Agent", "role": "UI Engineer",
     "description": "Builds the storefront pages, styles, and cart interactions."},
    {"name": "Verifier", "role": "Verifier",
     "description": "Validates outputs against the goal and flags gaps."},
    {"name": "Safety Reviewer", "role": "Safety Reviewer",
     "description": "Summarizes risk and recommends approval decisions."},
]

# Plain-English result text recorded as each task completes (in DAG order).
_TASK_RESULTS: dict[str, str] = {
    "Draft the project plan": "Planned a static storefront: hero, product grid, cart, mock checkout.",
    "Research the domain": "Defined four bottle products with prices and accessible alt text in products.json.",
    "Build the backend": "Created products.json data and the cart/total logic in app.js.",
    "Build the user interface": "Built index.html (semantic, accessible) and responsive styles.css.",
    "Review and verify the work": "Reviewed files; flagged the payment feature for approval and validation.",
}


def _write_file(
    session: Session, workspace: Workspace, root: str, path: str, content: str
) -> list[core_models.Event]:
    """Write one website file through the enforcement gateway, exactly like the
    Files panel does (propose → allow → execute → file event)."""
    _result, events = enforcement.guarded_execute(
        session,
        workspace,
        root,
        action_type="file.write",
        target=path,
        legacy_audit=enforcement.file_legacy_audit(session, workspace, "write", path),
        approval_payload={"path": path, "content": content},
        execute=lambda: sandbox.write_file(session, workspace, root, path, content),
    )
    return events


def _run_command(
    session: Session, workspace: Workspace, root: str, command: str, args: list[str]
) -> list[core_models.Event]:
    _result, events = enforcement.guarded_execute(
        session,
        workspace,
        root,
        action_type="command.run",
        target=" ".join([command, *args]),
        metadata={"command": command, "args": args},
        legacy_audit=enforcement.command_legacy_audit(session, workspace, command, args),
        execute=lambda: commands.run_command(
            session, workspace, root, command=command, args=args, timeout_seconds=30
        ),
    )
    return events


def seed(
    session: Session, workspaces_root: str, *, project_id: str = "demo-project"
) -> tuple[dict[str, Any], list[core_models.Event]]:
    """Create and build the Bottle Shop demo. Returns (summary, events).
    Deterministic: same goal, agents, files, and governance halt every run."""
    events: list[core_models.Event] = []

    # 1) Workspace + sandbox.
    workspace, ev = service.create_workspace(
        session, name="Tidewater Bottle Shop (demo)", goal=DEMO_GOAL,
        project_id=project_id, metadata={"demo": DEMO_KIND},
    )
    events += ev
    _status, ev = sandbox.init_sandbox(session, workspace, workspaces_root)
    events += ev
    workspace.status = "active"

    # 2) Agents — built through the same AgentDefinitionIn defaults the
    #    Agents panel uses, so they are ordinary v1.1 agent definitions.
    agent_ids: dict[str, str] = {}
    for spec in _AGENTS:
        fields = AgentDefinitionIn(**spec).model_dump()
        agent, ev = service.create_agent(session, workspace, **fields)
        agent_ids[spec["name"]] = agent.id
        events += ev

    # 3) Workflow + plan (five tasks auto-assigned to the matching agents).
    workflow, ev = orchestration.create_workflow(session, workspace, DEMO_GOAL, "demo")
    events += ev
    _plan, _tasks, ev = orchestration.create_plan(session, workspace, workflow)
    events += ev

    # 4) Start, then write the website files through the enforcement gateway.
    _wf, ev = orchestration.transition_workflow(session, workspace, workflow, "start")
    events += ev
    for path, content in WEBSITE_FILES.items():
        events += _write_file(session, workspace, workspaces_root, path, content)

    # 5) Walk the workflow to completion, recording a plain-English result per
    #    task in dependency order.
    for _ in range(8):
        running = [t for t in orchestration.list_tasks(session, workflow.id) if t.status == "running"]
        if not running:
            break
        for task in running:
            _r, ev = orchestration.record_result(
                session, workspace, workflow, task,
                output=_TASK_RESULTS.get(task.title, "Completed."), artifacts=[],
            )
            events += ev

    # 6) Safe commands through the runner (deterministic, always present).
    events += _run_command(session, workspace, workspaces_root, "ls", [])
    events += _run_command(session, workspace, workspaces_root, "python3", ["--version"])

    # 7) Deterministic validators on the real artifacts.
    validator_ids: list[str] = []
    runs = [
        ("code_syntax", "products.json", {}),
        ("secret_exposure", "app.js", {}),
        ("command_result", "", {}),
        ("data_flow", "cart ↔ products.json", {
            "consumer": {"label": "cart", "fields": {"id": "string", "name": "string", "price_cents": "number"}},
            "producer": {"label": "products.json", "fields": {"id": "string", "name": "string", "price_cents": "number", "image_alt": "string", "blurb": "string"}},
        }),
        ("business_risk", "mock checkout / payment wiring", {
            "target": "payment checkout flow", "description": "wire the mock checkout to a payment provider"}),
    ]
    for vtype, ref, payload in runs:
        result, ev = validators.run_validator(
            session, workspace, workspaces_root,
            validator_type=vtype, target_ref=ref, payload=payload,
        )
        validator_ids.append(result.id)
        events += ev

    # 8) Governance halt: the Backend Coder attempts to wire real payment code.
    #    The enforcement gateway holds it for human approval (v1.6) — the file
    #    is NOT written, and a pending approval is left for the user to resolve.
    pending_approval_id: str | None = None
    try:
        events += _write_file_as_agent(
            session, workspace, workspaces_root,
            path="src/payment/checkout.js",
            content="// TODO: wire Tidewater checkout to a real payment provider\n",
            agent_id=agent_ids["Backend Coder"],
        )
    except SandboxBlocked as halt:
        events += halt.events
        pending = approvals.list_approvals(session, workspace.id, status="pending")
        pending_approval_id = pending[0].id if pending else None

    summary = {
        "workspace_id": workspace.id,
        "workflow_id": workflow.id,
        "agent_count": len(agent_ids),
        "file_count": len(WEBSITE_FILES),
        "command_count": 2,
        "validator_result_ids": validator_ids,
        "pending_approval_id": pending_approval_id,
        "goal": DEMO_GOAL,
    }
    return summary, events


def _write_file_as_agent(
    session: Session, workspace: Workspace, root: str, *, path: str, content: str, agent_id: str
) -> list[core_models.Event]:
    """A file write attributed to an agent actor — used for the governance
    halt so the payment-path write is held for approval."""
    _result, events = enforcement.guarded_execute(
        session,
        workspace,
        root,
        action_type="file.write",
        target=path,
        actor_type="agent",
        agent_id=agent_id,
        legacy_audit=enforcement.file_legacy_audit(session, workspace, "write", path),
        approval_payload={"path": path, "content": content},
        execute=lambda: sandbox.write_file(session, workspace, root, path, content),
    )
    return events
