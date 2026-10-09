// Round 22 -- browser walkthrough of the Conflict page of the HISTORICAL AMD run d5b60b8a-... (the run of John's original 34 evidence items).
// Headless Google Chrome driven by Playwright, READ-ONLY: every request that is not GET/HEAD/OPTIONS is aborted at the browser context (and
// logged); the script never clicks a run / start / review-save control. It talks only to the read-only viewer (API :8001 with no real-execution
// flag, web :5176) -- never to the always-on service on :8000 or the dev server on :5175.
//
// What it proves, from what the page ACTUALLY rendered (every statement is read back from the DOM):
//   * the conflict header (admitted, level, score) equals the run's own saved conflicts.json -- nothing is re-evaluated;
//   * each of the 34 evidence items (bull 15 / bear 17 / counter 2) offers "View basis";
//   * for the items opened: "Historical use in this run (as saved)" states the saved admission, level and score; "Current basis" says
//     not linked / not verified with the neutral legacy reason; no wording calls the judgment wrong or baseless;
//   * the historical run's files are byte-identical before and after (sha256 of every file).
//
// usage: node browser_walkthrough_round22_conflict.mjs
import { chromium } from "/Users/xiangmao/COMQUTOR-Alpha-/frontend/node_modules/playwright/index.mjs";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const WEB = "http://127.0.0.1:5176";
const API = "http://127.0.0.1:8001";
const RUN = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const OUT = path.join(HERE, "browser_walkthrough_round22_conflict");
const RUN_DIR = path.join("/Users/xiangmao/COMQUTOR-Alpha-/outputs/runs", RUN);
fs.mkdirSync(OUT, { recursive: true });

const hashTree = (dir) => {
  const out = {};
  const walk = (d) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) walk(full);
      else out[path.relative(dir, full)] = crypto.createHash("sha256").update(fs.readFileSync(full)).digest("hex");
    }
  };
  walk(dir);
  return out;
};
const before = hashTree(RUN_DIR);
const saved = JSON.parse(fs.readFileSync(path.join(RUN_DIR, "conflicts.json"), "utf8"));
const savedMain = saved.main_conflict;

const log = {
  executed_at: new Date().toISOString(), browser: "Google Chrome (system install), headless, via Playwright channel=chrome", web: WEB, api: API, run: RUN,
  safety: "all non-GET requests aborted at the browser context; no run / start / review-save control was clicked",
  blocked_non_get_requests: [], console_errors: [], failed_requests: [], steps: {},
};
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } });
await context.route("**/*", (route) => {
  const m = route.request().method();
  if (!["GET", "HEAD", "OPTIONS"].includes(m)) { log.blocked_non_get_requests.push(`${m} ${route.request().url()}`); return route.abort(); }
  return route.continue();
});
// The conflicts route is DB-only and the isolated database holds NO conflict rows for this historical run (verified below: the
// real API answers CONFLICTS_NOT_READY). So the page's conflicts payload is served from the run's OWN saved conflicts.json, mapped to
// the API shape exactly as the route would return it (same fields; ``status`` added; ``schema_version`` = the saved source schema). The
// claim-level evidence-trace calls are NOT intercepted: they hit the real read-only API, which reads the run's saved files.
const realConflictsReply = await (await fetch(`${API}/api/research/${RUN}/conflicts`)).json();
log.real_api_conflicts_reply_for_this_run = { status: realConflictsReply.status, error_code: realConflictsReply.error_code };
const apiShaped = {
  activation_formula_version: saved.activation_formula_version, arbitration: saved.arbitration, conflicts: saved.conflicts, formula_version: saved.formula_version,
  main_conflict: saved.main_conflict, run_id: saved.run_id, schema_version: saved.source_schema_version, status: "ok", ticker: saved.ticker,
};
log.conflict_page_data_source = "GET /api/research/<run>/conflicts intercepted in the browser and answered from the run's own saved conflicts.json (API shape); evidence-trace calls are real";
await context.route(`**/api/research/${RUN}/conflicts`, (route) => {
  if (route.request().method() !== "GET") { log.blocked_non_get_requests.push(`${route.request().method()} ${route.request().url()}`); return route.abort(); }
  return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(apiShaped) });
});
const page = await context.newPage();
page.on("console", (msg) => { if (msg.type() === "error") log.console_errors.push(msg.text().slice(0, 300)); });
page.on("pageerror", (e) => log.console_errors.push("pageerror: " + String(e).slice(0, 300)));
page.on("response", (r) => { if (r.status() >= 400) log.failed_requests.push(`${r.status()} ${r.url().slice(0, 160)}`); });
const norm = (t) => String(t ?? "").replace(/\s+/g, " ").trim();
const has = (text, ...needles) => Object.fromEntries(needles.map((n) => [n, norm(text).includes(n)]));
const FORBIDDEN = /\b(wrong|incorrect|erroneous|invalid|fabricat\w*|baseless|without basis|no basis)\b/i;
const step = async (name, fn) => { try { log.steps[name] = await fn(); } catch (e) { log.steps[name] = { error: String(e).slice(0, 700) }; } };

await step("conflict_page", async () => {
  await page.goto(`${WEB}/runs/${RUN}/conflicts`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("article.conflict-card", { timeout: 60000 });
  await page.screenshot({ path: path.join(OUT, "01_conflict_page.png"), fullPage: false });
  const main = page.locator("article.conflict-card-main").first();
  const headerText = norm(await main.innerText());
  const sections = {
    bull: await page.locator("section.evidence-ui-section h4", { hasText: /^Bull Evidence/ }).first().innerText(),
    bear: await page.locator("section.evidence-ui-section h4", { hasText: /^Bear Evidence/ }).first().innerText(),
    counter: await page.locator("section.counter-evidence-section h4").first().innerText(),
  };
  // every evidence list shows 5 by default: expand them all so all 34 items are on the page
  for (const toggle of await page.locator("button.evidence-ui-show-toggle").all()) {
    if ((await toggle.innerText()).startsWith("Show all")) await toggle.click();
  }
  await page.waitForTimeout(300);
  const buttons = await main.locator("button.evidence-basis-button").count();
  return {
    main_conflict_header_text_excerpt: headerText.slice(0, 260),
    saved_main_conflict: { id: savedMain.conflict_id, status: savedMain.admissibility.status, level: savedMain.conflict_level, score: savedMain.conflict_score },
    // the card says "Main conflict" (a main conflict is by construction an admitted one) with the saved level and the saved score to one decimal
    header_shows_saved_values: has(headerText, `${savedMain.alpha_a} vs ${savedMain.alpha_b}`, "Main conflict",
      `Conflict score: ${savedMain.conflict_score.toFixed(1)} (${savedMain.conflict_level[0].toUpperCase()}${savedMain.conflict_level.slice(1)})`),
    section_titles: sections,
    view_basis_buttons_in_main_conflict: buttons,
    one_per_saved_evidence_item_34: buttons === 34,
  };
});

// open one item per side and read back what the page said
const openItem = async (sideTitle, index, shot) => {
  const main = page.locator("article.conflict-card-main").first();
  const section = sideTitle === "counter"
    ? main.locator("section.counter-evidence-section")
    : main.locator("section.evidence-ui-section", { has: page.locator("h4", { hasText: new RegExp(`^${sideTitle === "bull" ? "Bull" : "Bear"} Evidence`) }) }).first();
  const item = section.locator("li.evidence-ui-item").nth(index);
  await item.scrollIntoViewIfNeeded();
  const claimText = norm(await item.locator("p.evidence-ui-item-text").innerText());
  await item.locator("button.evidence-basis-button").click();
  const trace = item.locator(".evidence-trace");
  await trace.waitFor({ timeout: 30000 });
  await page.waitForTimeout(400);
  const text = norm(await trace.innerText());
  await item.screenshot({ path: path.join(OUT, shot + ".png") });
  const note = "This run was saved before source linking existed, so its records carry no source-link fields and no source basis can be shown for this claim today. That describes what was saved; it is not a finding that the claim was wrong or that it had no basis when it was made.";
  const withoutNote = text.split(note).join("");
  return {
    claim_text_on_the_page: claimText.slice(0, 160),
    observed: has(text, "Historical use in this run (as saved)", `conflict ${savedMain.conflict_id}`, "— admitted", `level ${savedMain.conflict_level}`, `score ${savedMain.conflict_score.toFixed(2)}`,
      "unchanged by anything shown in the current basis", "Current basis", "NOT_LINKED", "No source linked; not verified", "This run was saved before source linking existed", "No source is linked to this claim."),
    forbidden_wording_outside_the_neutral_note: FORBIDDEN.test(withoutNote) ? withoutNote.match(FORBIDDEN)[0] : null,
    trace_text: text,
  };
};
await step("bull_item", () => openItem("bull", 0, "02_bull_item_view_basis"));
await step("bear_item", () => openItem("bear", 0, "03_bear_item_view_basis"));
await step("counter_item", () => openItem("counter", 0, "04_counter_item_view_basis"));

await step("other_conflicts_on_the_page", async () => {
  const cards = await page.locator("article.conflict-card").count();
  return { conflict_cards_on_the_page: cards, saved_admitted_conflicts: (saved.conflicts || []).map((c) => c.conflict_id) };
});

const after = hashTree(RUN_DIR);
log.historical_run_unchanged = JSON.stringify(before) === JSON.stringify(after);
log.historical_run_files_hashed = Object.keys(before).length;
fs.writeFileSync(path.join(HERE, "browser_walkthrough_round22_conflict_result.json"), JSON.stringify(log, null, 1));
console.log(JSON.stringify({
  blocked_non_get_requests: log.blocked_non_get_requests, console_errors: log.console_errors.slice(0, 5), failed_requests: log.failed_requests.slice(0, 5),
  step_errors: Object.entries(log.steps).filter(([, v]) => v && v.error).map(([k, v]) => [k, v.error]),
  historical_run_unchanged: log.historical_run_unchanged,
}, null, 1));
await browser.close();
