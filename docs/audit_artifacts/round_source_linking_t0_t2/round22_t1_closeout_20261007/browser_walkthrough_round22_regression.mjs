// Round 22 -- regression walkthrough of the Structure and Research pages of the final offline execution after the closeout changes
// (headless Google Chrome via Playwright). READ-ONLY: every non-GET request is aborted and counted; only the viewer API :8001 and web :5176
// are used. It proves the pages still show the Round-21 positive sample and that a market-data claim now shows whether its indicator inputs
// were saved (for this real run: NOT saved -- nothing is backfilled).
//
// usage: node browser_walkthrough_round22_regression.mjs
import { chromium } from "/Users/xiangmao/COMQUTOR-Alpha-/frontend/node_modules/playwright/index.mjs";
import fs from "node:fs";
import path from "node:path";

const WEB = "http://127.0.0.1:5176";
const EXEC = "dependency-20261007T220450Z-33128621";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const OUT = path.join(HERE, "browser_walkthrough_round22_regression");
fs.mkdirSync(OUT, { recursive: true });
const log = { executed_at: new Date().toISOString(), execution: EXEC, blocked_non_get_requests: [], console_errors: [], failed_requests: [], steps: {} };
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } });
await context.route("**/*", (route) => {
  const m = route.request().method();
  if (!["GET", "HEAD", "OPTIONS"].includes(m)) { log.blocked_non_get_requests.push(`${m} ${route.request().url()}`); return route.abort(); }
  return route.continue();
});
const page = await context.newPage();
page.on("console", (msg) => { if (msg.type() === "error") log.console_errors.push(msg.text().slice(0, 300)); });
page.on("pageerror", (e) => log.console_errors.push("pageerror: " + String(e).slice(0, 300)));
page.on("response", (r) => { if (r.status() >= 400) log.failed_requests.push(`${r.status()} ${r.url().slice(0, 160)}`); });
const norm = (t) => String(t ?? "").replace(/\s+/g, " ").trim();
const has = (text, ...needles) => Object.fromEntries(needles.map((n) => [n, norm(text).includes(n)]));
const step = async (name, fn) => { try { log.steps[name] = await fn(); } catch (e) { log.steps[name] = { error: String(e).slice(0, 700) }; } };

await step("structure_page_claim_31", async () => {
  await page.goto(`${WEB}/runs/${EXEC}/structure`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("article.alpha-card", { timeout: 60000 });
  const card = page.locator("article.alpha-card", { has: page.locator("p.alpha-card-id", { hasText: /^A301$/ }) });
  await card.locator("details.alpha-card-evidence summary").click();
  const item = card.locator("li.alpha-card-evidence-item").first();
  await item.locator("button.evidence-basis-button").click();
  const trace = item.locator(".evidence-trace");
  await trace.waitFor({ timeout: 30000 });
  await page.waitForTimeout(400);
  const text = norm(await trace.innerText());
  await item.screenshot({ path: path.join(OUT, "01_structure_claim_31_basis.png") });
  return {
    observed: has(text, "Verified: the saved source content supports this claim", "Source the verification used", "$11,536M", "excerpt and data_snapshot.periods for Total Revenue",
      "Used as the basis of 1 other claim(s)", "IN_OFFICIAL_POOL"),
    shows_no_historical_use_section_for_a_claim_in_no_conflict: !text.includes("Historical use in this run"),
    shows_no_legacy_note: !text.includes("saved before source linking existed"),
  };
});

await step("research_page_market_claim_indicator_inputs", async () => {
  await page.goto(`${WEB}/runs/${EXEC}/research`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("section.key-conclusions-panel", { timeout: 60000 });
  const panel = page.locator("section.key-conclusions-panel");
  for (const g of await panel.locator("details.key-conclusions-group").all()) await g.locator("summary").click();
  const row = panel.locator("tr.key-conclusion-row", { hasText: "The MACD histogram peaked at 15.05" }).first();
  await row.locator("button", { hasText: "Why these statuses?" }).click();
  const detail = row.locator("xpath=following-sibling::tr[1]").locator(".evidence-trace");
  await detail.waitFor({ timeout: 30000 });
  await page.waitForTimeout(400);
  const text = norm(await detail.innerText());
  await detail.screenshot({ path: path.join(OUT, "02_research_market_claim_indicator_inputs.png") });
  return {
    observed: has(text, "Partly supported: part of the claim is not backed by the source",
      "Indicator inputs: not saved in this run (stockstats, stockstats==0.6.8; window parameters only: 1255 rows (2021-10-06 → 2026-10-06)). Nothing is backfilled.",
      "Numbers not found in the saved data", "15.05"),
  };
});

fs.writeFileSync(path.join(HERE, "browser_walkthrough_round22_regression_result.json"), JSON.stringify(log, null, 1));
console.log(JSON.stringify({ blocked_non_get_requests: log.blocked_non_get_requests, console_errors: log.console_errors.slice(0, 5), failed_requests: log.failed_requests.slice(0, 5),
  step_errors: Object.entries(log.steps).filter(([, v]) => v && v.error).map(([k, v]) => [k, v.error]),
  missing: Object.entries(log.steps).flatMap(([k, v]) => Object.entries(v.observed ?? {}).filter(([, ok]) => !ok).map(([n]) => `${k}: ${n}`)) }, null, 1));
await browser.close();
