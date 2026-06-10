/**
 * Captures the README screenshots against a running AgentLab stack and
 * verifies the WebSocket live stream along the way.
 *
 * Usage:
 *   docker compose up -d && docker compose --profile demo run --rm seed
 *   npm run screenshots                 # defaults to http://localhost:3000
 *   BASE_URL=http://localhost:5173 npm run screenshots
 *
 * Requires: npm i -D playwright && npx playwright install chromium
 */
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000";
const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../../../docs/screenshots");

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const runs = await fetch(`${BASE_URL}/api/projects/demo-project/runs`).then((r) => r.json());
  const retryRun = runs.find((r) => r.name?.startsWith("retry"));
  if (!retryRun) throw new Error("No 'retry' demo run found — seed the demo first.");

  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1600, height: 920 },
    deviceScaleFactor: 2,
  });
  const shot = (name) => page.screenshot({ path: resolve(OUT_DIR, name) });

  // 1. Dashboard
  await page.goto(`${BASE_URL}/dashboard`);
  await page.getByText("Recent runs", { exact: false }).waitFor();
  await page.waitForTimeout(400);
  await shot("dashboard.png");
  console.log("✓ dashboard.png");

  // 2. Run topology with the security agent inspected
  await page.goto(`${BASE_URL}/runs/${retryRun.id}`);
  await page.waitForSelector(".react-flow__node", { state: "visible" });
  await page.waitForTimeout(1400); // layout + fitView animation
  // WebSocket check: the sidebar pill flips to "Live stream" only when
  // WS /ws/projects/... is connected (through nginx in Docker).
  await page.getByText("Live stream").waitFor({ timeout: 5000 });
  console.log("✓ WebSocket live stream connected");
  await page.click('.react-flow__node[data-id="security"]');
  await page.getByText("Recent activity").waitFor();
  await page.waitForTimeout(250);
  await shot("topology-retry.png");
  console.log("✓ topology-retry.png");

  // 3. Message inspector: channel chip -> message -> event detail
  // Edge chips can overlap at fit-to-view zoom; dispatch the click directly.
  const chip = page.locator(".react-flow button", { hasText: "2 msgs" }).first();
  await chip.dispatchEvent("click");
  await page.getByText("Messages on this channel").waitFor();
  await page.locator("button", { hasText: "msg-" }).first().click();
  await page.getByText("Payload").waitFor();
  await page.waitForTimeout(250);
  await shot("inspector-message.png");
  console.log("✓ inspector-message.png");

  // 4. Metrics tab
  await page.getByRole("button", { name: "metrics" }).click();
  await page.waitForSelector(".recharts-responsive-container");
  await page.waitForTimeout(600);
  await shot("metrics.png");
  console.log("✓ metrics.png");

  // 5. Replay debugger on the failed run, jumped to the error
  const failureRun = runs.find((r) => r.name?.startsWith("failure"));
  if (failureRun) {
    await page.goto(`${BASE_URL}/runs/${failureRun.id}`);
    await page.getByRole("button", { name: "replay" }).click();
    await page.getByText("following playhead").waitFor();
    await page.getByRole("button", { name: "Tool" }).click();
    await page.waitForTimeout(400);
    await page.getByRole("button", { name: "Error" }).click();
    await page.waitForTimeout(900); // fold + fitView
    await shot("replay-debugger.png");
    console.log("✓ replay-debugger.png");
  }

  // 6. Fault Injection Lab
  await page.goto(`${BASE_URL}/lab`);
  await page.getByText("All faults are simulations").waitFor();
  await page.waitForTimeout(800); // selectors + agent strip populate
  await shot("lab-mode.png");
  console.log("✓ lab-mode.png");

  // 7. Security Lab (malicious-agent attacks)
  await page.getByRole("button", { name: "Security Lab" }).click();
  await page.getByText("Safe cyber range").waitFor();
  await page.waitForTimeout(500);
  await shot("security-lab.png");
  console.log("✓ security-lab.png");

  // 8. Malicious Agent Demo replay, paused on the attack
  const maliciousRun = runs.find((r) => r.name?.startsWith("Malicious Agent Demo"));
  if (maliciousRun) {
    await page.goto(`${BASE_URL}/runs/${maliciousRun.id}`);
    await page.getByRole("button", { name: "replay" }).click();
    await page.getByText("following playhead").waitFor();
    await page.getByRole("button", { name: "Attack" }).click(); // jump to first attack
    await page.waitForTimeout(900); // fold + fitView
    await shot("malicious-replay.png");
    console.log("✓ malicious-replay.png");
  }

  await browser.close();
  console.log(`\nSaved to ${OUT_DIR}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
