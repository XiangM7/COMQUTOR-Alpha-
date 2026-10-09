// Round 19 -- browser walkthrough of an EXISTING run (headless Google Chrome driven by Playwright).
//
// Safety: every request that is not GET/HEAD/OPTIONS is aborted at the browser context (and logged), so no click can write anything.
// The script never clicks a run / "Start research" / review-save button; it only toggles disclosures and the Export / Recent-runs controls.
// Everything it reports comes from what the rendered page actually showed; anything it could not observe is reported as not observed.
//
// usage: node browser_walkthrough.mjs <execution_id>
import { chromium } from "/Users/xiangmao/COMQUTOR-Alpha-/frontend/node_modules/playwright/index.mjs";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const BASE = "http://127.0.0.1:5175";
const EXEC = process.argv[2];
const HERE = path.dirname(new URL(import.meta.url).pathname);
const OUT = path.join(HERE, "browser_walkthrough");
fs.mkdirSync(OUT, { recursive: true });
const A301_CLAIMS = [
  "Revenue grew from $7,685M (Q2'25)",
  "The Q1'26 flat-to-down print",
  "Gross profit nearly doubled YoY",
];

const log = {
  executed_at: new Date().toISOString(),
  browser: "Google Chrome (system install), headless, via Playwright channel=chrome",
  frontend: BASE, execution: EXEC,
  safety: "all non-GET requests aborted at the browser context; no run / start / review-save control was clicked",
  blocked_non_get_requests: [], console_errors: [], failed_requests: [], steps: {},
};
const step = async (name, fn) => {
  try { log.steps[name] = await fn(); } catch (e) { log.steps[name] = { error: String(e).slice(0, 400) }; }
};
const LOC = /src_[0-9a-f]{16}|frag(?:ment)?[_ -]?id|:frag:\d|data_snapshot|excerpt|Total Revenue|Gross Profit/i;
const VER = /SUPPORTS|CONDITIONAL|PENDING_REVIEW|content[- ]support|verified|LLM_CONTENT/i;

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
await context.route("**/*", (route) => {
  const m = route.request().method();
  if (!["GET", "HEAD", "OPTIONS"].includes(m)) { log.blocked_non_get_requests.push(`${m} ${route.request().url()}`); return route.abort(); }
  return route.continue();
});
const page = await context.newPage();
page.on("console", (msg) => { if (msg.type() === "error") log.console_errors.push(msg.text().slice(0, 300)); });
page.on("pageerror", (e) => log.console_errors.push("pageerror: " + String(e).slice(0, 300)));
page.on("response", (r) => { if (r.status() >= 400) log.failed_requests.push(`${r.status()} ${r.url().slice(0, 160)}`); });
const shot = async (name) => page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: true });

// ---------------------------------------------------------------- 1. Structure page: A301 card
await step("structure_page_A301", async () => {
  await page.goto(`${BASE}/runs/${EXEC}/structure`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("article.alpha-card", { timeout: 60000 });
  const h1 = await page.locator("h1").first().innerText();
  await shot("01_structure_page");
  const card = page.locator("article.alpha-card", { has: page.locator("p.alpha-card-id", { hasText: /^A301$/ }) });
  const found = await card.count();
  if (!found) return { h1, a301_card_found: false };
  const before = await card.innerText();
  const summaries = card.locator("summary");
  const labels = [];
  for (let i = 0; i < (await summaries.count()); i++) {
    const s = summaries.nth(i);
    labels.push((await s.innerText()).trim());
    await s.click(); // toggles a <details> disclosure only
  }
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: path.join(OUT, "02_A301_card_all_disclosures_open.png") });
  const after = await card.innerText();
  const evidence = card.locator("details.alpha-card-evidence");
  const evidenceText = (await evidence.count()) ? await evidence.innerText() : "";
  return {
    h1, a301_card_found: true, disclosures_clicked: labels,
    card_text_before_opening_disclosures: before,
    card_text_after_opening_all_disclosures: after,
    evidence_disclosure_text: evidenceText,
    observed: {
      activation_score_shown: /Activation score\s*21\.3/.test(after),
      evidence_items_listed: (evidenceText.match(/Relation:/g) || []).length,
      each_item_shows_match_relation_assertion: /Match [0-9.]+/.test(evidenceText) && /Relation:/.test(evidenceText) && /Assertion:/.test(evidenceText),
      all_three_claims_listed: A301_CLAIMS.every((c) => evidenceText.includes(c)),
      scoring_components_shown: ["Evidence quality", "Agent independence", "Local structure", "Ticker", "Recency", "Direction"].filter((k) => new RegExp(k, "i").test(after)),
      source_or_fragment_or_data_location_visible_in_card: LOC.test(evidenceText),
      verification_status_visible_in_evidence_list: VER.test(evidenceText),
    },
  };
});

// ---------------------------------------------------------------- 2. Research page: findings, sources, verification, Export
await step("research_page", async () => {
  await page.goto(`${BASE}/runs/${EXEC}/research`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("h2:has-text('Analyst findings')", { timeout: 60000 });
  await shot("03_research_page_initial");
  const more = page.locator("button", { hasText: /^More \(/ });
  const nMore = await more.count();
  for (let i = 0; i < nMore; i++) await more.nth(0).click().catch(() => {});
  await page.waitForTimeout(500);
  await shot("04_research_page_findings_expanded");
  const body = await page.locator("body").innerText();
  const cards = page.locator("li.analyst-output-card");
  const n = await cards.count();
  const texts = [];
  for (let i = 0; i < n; i++) texts.push(await cards.nth(i).innerText());
  const withSource = texts.filter((t) => LOC.test(t));
  // open the content-support panel of the first card that offers one (toggle only; the Save control is never touched)
  let panelText = null;
  const toggle = page.locator("li.analyst-output-card button[aria-expanded]").first();
  if (await toggle.count()) {
    await toggle.scrollIntoViewIfNeeded();
    await toggle.click();
    await page.waitForTimeout(800);
    panelText = await toggle.locator("xpath=ancestor::li[contains(@class,'analyst-output-card')]").first().innerText();
    await toggle.locator("xpath=ancestor::li[contains(@class,'analyst-output-card')]").first().screenshot({ path: path.join(OUT, "05_finding_card_with_content_support_panel.png") });
  }
  const sections = await page.locator("h2, h3").allInnerTexts();
  return {
    finding_cards_rendered: n, more_buttons_clicked: nMore, section_headings: sections.slice(0, 40),
    the_three_A301_claims_found_on_page: A301_CLAIMS.map((c) => ({ claim_starts_with: c, found: body.includes(c) })),
    cards_that_show_a_source_or_fragment_or_data_location: withSource.length,
    sample_card_with_source: withSource[0] ?? null,
    sample_content_support_panel_text: panelText,
    data_quality_text: (await page.locator("h2:has-text('Data Quality')").count()) ? await page.locator("section:has(h2:has-text('Data Quality'))").first().innerText() : null,
    research_summary_text: (await page.locator("section:has(h2:has-text('Research summary'))").count()) ? (await page.locator("section:has(h2:has-text('Research summary'))").first().innerText()).slice(0, 1500) : null,
  };
});

// ---------------------------------------------------------------- 3. Export (GET) and compare with the files on disk
await step("export_download", async () => {
  const button = page.locator("button", { hasText: /^Export research$/ });
  if (!(await button.count())) return { export_button_found: false };
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), button.first().click()]);
  const file = path.join(OUT, "exported_from_browser.zip");
  await download.saveAs(file);
  const bytes = fs.readFileSync(file);
  const listing = execFileSync("/usr/bin/unzip", ["-Z1", file]).toString().trim().split("\n");
  const runDir = `/Users/xiangmao/COMQUTOR-Alpha-/outputs/runs/${EXEC}`;
  let mismatched = [];
  for (const name of listing) {
    const inZip = execFileSync("/usr/bin/unzip", ["-p", file, name], { maxBuffer: 1 << 28 });
    const onDisk = fs.readFileSync(path.join(runDir, name));
    if (!inZip.equals(onDisk)) mismatched.push(name);
  }
  return { export_button_found: true, suggested_filename: download.suggestedFilename(), bytes: bytes.length, sha256: crypto.createHash("sha256").update(bytes).digest("hex"), members: listing.length, members_differing_from_execution_files: mismatched };
});

// ---------------------------------------------------------------- 4. Conflict radar
await step("conflicts_page", async () => {
  await page.goto(`${BASE}/runs/${EXEC}/conflicts`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("h1, h2", { timeout: 60000 });
  await page.waitForTimeout(800);
  await shot("06_conflict_radar");
  const text = await page.locator("main, body").first().innerText();
  return { text: text.slice(0, 4000), mentions_no_admitted_or_insufficient: /no (admitted|main) conflict|insufficient|not enough|No conflicts/i.test(text) };
});

// ---------------------------------------------------------------- 5. History (Recent runs disclosure on the research entry page; the form's run control is never clicked)
await step("history_recent_runs", async () => {
  await page.goto(`${BASE}/research`, { waitUntil: "networkidle", timeout: 90000 });
  const toggle = page.locator("button", { hasText: /Recent runs/ }).first();
  if (!(await toggle.count())) return { recent_runs_control_found: false };
  await toggle.click();
  await page.waitForTimeout(1200);
  await shot("07_recent_runs_menu");
  const panel = page.locator("[id^='recent-runs'], [role='menu'], [role='dialog']").first();
  const text = (await panel.count()) ? await panel.innerText() : await page.locator("body").innerText();
  return { recent_runs_control_found: true, lists_requalification: text.includes(EXEC.slice(0, 20)) || /requal/i.test(text), lists_recovery: /recovery/i.test(text), text: text.slice(0, 1500) };
});

log.finished_at = new Date().toISOString();
fs.writeFileSync(path.join(HERE, "browser_walkthrough_result.json"), JSON.stringify(log, null, 1));
await browser.close();
console.log(JSON.stringify({
  steps: Object.fromEntries(Object.entries(log.steps).map(([k, v]) => [k, v.error ? { error: v.error } : (v.observed ?? Object.fromEntries(Object.entries(v).filter(([kk, vv]) => typeof vv !== "string" && !Array.isArray(vv) || kk === "section_headings").slice(0, 8))) ])),
  blocked_non_get_requests: log.blocked_non_get_requests, console_errors: log.console_errors.slice(0, 5), failed_requests: log.failed_requests.slice(0, 8),
}, null, 1));
