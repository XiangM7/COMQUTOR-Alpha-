// Round 21 -- browser walkthrough of the offline `dependency-*` execution (headless Google Chrome driven by Playwright).
//
// Safety: every request that is not GET/HEAD/OPTIONS is aborted at the browser context (and logged), so no click can write
// anything. The script never clicks a run / "Start research" / review-save control; it only opens disclosures, the "View basis" /
// "Why these statuses?" toggles and the Export control. It talks only to the READ-ONLY viewer (API :8001 with no real-execution
// flag, web :5176) -- never to the always-on service on :8000 or the dev server on :5175.
// Everything reported comes from what the rendered page actually showed.
//
// usage: node browser_walkthrough_round21.mjs <execution_id>
import { chromium } from "/Users/xiangmao/COMQUTOR-Alpha-/frontend/node_modules/playwright/index.mjs";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const WEB = "http://127.0.0.1:5176";
const API = "http://127.0.0.1:8001";
const EXEC = process.argv[2];
const HERE = path.dirname(new URL(import.meta.url).pathname);
const OUT = path.join(HERE, "browser_walkthrough_round21");
fs.mkdirSync(OUT, { recursive: true });
const ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1:";
const FA = ROOT + "fundamental_agent:fundamentals_report:claim:";
const PM = ROOT + "portfolio_manager:final_trade_decision:claim:";

const log = {
  executed_at: new Date().toISOString(),
  browser: "Google Chrome (system install), headless, via Playwright channel=chrome",
  web: WEB, api: API, execution: EXEC,
  safety: "all non-GET requests aborted at the browser context; no run / start / review-save control was clicked",
  blocked_non_get_requests: [], console_errors: [], failed_requests: [], steps: {},
};
const step = async (name, fn) => {
  try { log.steps[name] = await fn(); } catch (e) { log.steps[name] = { error: String(e).slice(0, 600) }; }
};
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1200 }, acceptDownloads: true });
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
const apiJson = async (p) => (await fetch(API + p)).json();
const has = (text, ...needles) => Object.fromEntries(needles.map((n) => [n, text.includes(n)]));
const norm = (t) => String(t ?? "").replace(/\s+/g, " ").trim();
const missingOf = (obs) => Object.entries(obs ?? {}).filter(([, ok]) => !ok).map(([n]) => n);

// What the SAVED data (as the API serves it) says must be visible, derived from the API item itself -- so the check cannot
// pass by testing the strings the UI happens to render.
const expectedStrings = (item) => {
  const out = [];
  const ss = item.source_support, cs = ss.content_support;
  out.push(ss.label, ss.reason, item.alpha_match.label, item.stance.label, item.scoring.label, ss.status_code, item.alpha_match.status_code, item.stance.status_code, item.scoring.status_code);
  if (cs.used_location) out.push("Located at: " + cs.used_location);
  if (cs.supporting_quote_or_data) out.push(norm(cs.supporting_quote_or_data).slice(0, 60));
  if (cs.core_proposition) out.push(norm(cs.core_proposition).slice(0, 60));
  if (cs.rationale) out.push(norm(cs.rationale).slice(0, 60));
  if (cs.unsupported_remainder) out.push(norm(cs.unsupported_remainder).slice(0, 60));
  if (cs.fallback_reason) out.push(cs.fallback_reason);
  if (cs.method) out.push(cs.method);
  for (const src of item.sources) {
    out.push(src.resolved ? (src.title ?? src.source_id) : src.source_id);
    if (!src.resolved) continue;
    if (src.fragment_id) out.push(src.fragment_id);
    if (src.content_hash) out.push(src.content_hash.slice(0, 12));
    for (const row of src.material_rows ?? []) for (const cell of row.cells) if (cell.used && cell.token) out.push(cell.token);
  }
  for (const calc of item.calculation.derived_calculations) out.push(calc.formula, calc.stated_token);
  for (const t of item.calculation.numbers_not_found_in_saved_data) out.push(t);
  for (const t of item.calculation.unreproduced_percent_tokens) out.push(t);
  const dep = item.dependency;
  if (dep.depends_on) out.push("Derived from claim " + dep.depends_on.split(":claim:")[1]);
  for (const d of dep.depended_by) out.push("claim " + d.split(":claim:")[1]);
  return [...new Set(out.filter(Boolean).map(norm))];
};
const apiVsUi = async (claimId, uiText) => {
  const item = (await apiJson(`/api/research/${EXEC}/evidence-trace?claim_id=${encodeURIComponent(claimId)}`)).item;
  const expected = expectedStrings(item);
  const ui = norm(uiText);
  return { claim_id: claimId, strings_the_saved_data_requires_on_screen: expected.length, missing_on_screen: expected.filter((e) => !ui.includes(e)) };
};
const keyRows = async () => (await apiJson(`/api/research/${EXEC}/evidence-trace?scope=key`)).key_conclusions.groups.flatMap((g) => g.rows);

// ------------------------------------------------------------------ 1. Structure page: A301 evidence -> View basis
await step("structure_page_A301_evidence_trace", async () => {
  await page.goto(`${WEB}/runs/${EXEC}/structure`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("article.alpha-card", { timeout: 60000 });
  await shot("01_structure_page");
  const card = page.locator("article.alpha-card", { has: page.locator("p.alpha-card-id", { hasText: /^A301$/ }) });
  if (!(await card.count())) return { a301_card_found: false };
  const evidence = card.locator("details.alpha-card-evidence");
  await evidence.locator("summary").click();
  const items = evidence.locator("li.alpha-card-evidence-item");
  const out = { a301_card_found: true, evidence_items: await items.count(), items: {} };
  const labels = { 0: "claim_31", 1: "claim_33", 2: "claim_36" };
  const claimIdOf = { claim_31: FA + "31", claim_33: FA + "33", claim_36: FA + "36" };
  const semantic = {
    claim_31: ["1 · Source support", "2 · Alpha match", "3 · Stance", "4 · Official scoring", "Verified: the saved source content supports this claim", "Source the verification used",
      "excerpt and data_snapshot.periods for Total Revenue", "2026-06-30=11536000000.0", "$11,536M", "$7,685M", "LLM_CONTENT_SUPPORT_VERIFIED", "DIRECT_FACT", "src_582ac24bf4319648:frag:0",
      "Revenue acceleration is dramatic", "Used as the basis of 1 other claim(s)", "claim 33", "no model judgment obtained", "REGISTRY_WRITE_TIME_UPPER_BOUND", "IN_OFFICIAL_POOL"],
    claim_33: ["Verified: the saved source content supports this claim", "Source the verification used", "$10,253M", "$10,270M", "Derived from claim 31", "Counted as one independent fact made up of 2 claim(s)",
      "LLM_CONTENT_SUPPORT_VERIFIED", "GROUNDED_INFERENCE", "IN_POOL_ZERO_WEIGHT", "NOT a model judgment", "no model judgment obtained"],
    claim_36: ["Verified: the saved source content supports this claim", "Source the verification used", "Gross Profit", "$6,203M", "$3,059M", "DERIVED_CALCULATION", "IN_POOL_ZERO_WEIGHT",
      "NOT a model judgment", "Counted as one independent fact made up of 1 claim(s)", "no model judgment obtained"],
  };
  for (let i = 0; i < Math.min(await items.count(), 3); i++) {
    const item = items.nth(i);
    const before = await item.innerText();
    await item.locator("button.evidence-basis-button").click();
    const trace = item.locator(".evidence-trace");
    await trace.waitFor({ timeout: 30000 });
    await page.waitForTimeout(400);
    const text = await trace.innerText();
    await item.scrollIntoViewIfNeeded();
    await item.screenshot({ path: path.join(OUT, `02_A301_${labels[i]}_basis_open.png`) });
    out.items[labels[i]] = {
      claim_line_before_opening: before.split("\n")[0],
      shows_only_internal_id_before_opening: !/Total Revenue|Gross Profit/.test(before),
      observed_after_opening: has(text, ...semantic[labels[i]]),
      missing_expected_strings: missingOf(has(text, ...semantic[labels[i]])),
      api_vs_ui: await apiVsUi(claimIdOf[labels[i]], text),
      trace_text: text,
    };
  }
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: path.join(OUT, "03_A301_card_with_all_three_basis_open.png") });
  const cardText = await card.innerText();
  out.card_counts_text = cardText.match(/\d+ independent[^\n]*|Independent evidence facts[^\n]*\n?[^\n]*/gi)?.slice(0, 4) ?? null;
  out.card_text_excerpt = cardText.slice(0, 1800);
  return out;
});

// ------------------------------------------------------------------ 2. Research page: key conclusions with four statuses
await step("research_page_key_conclusions", async () => {
  await page.goto(`${WEB}/runs/${EXEC}/research`, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForSelector("section.key-conclusions-panel table, section.key-conclusions-panel summary", { timeout: 60000 });
  const panel = page.locator("section.key-conclusions-panel");
  const groups = panel.locator("details.key-conclusions-group");
  const groupNames = [];
  for (let i = 0; i < (await groups.count()); i++) {
    const g = groups.nth(i);
    groupNames.push((await g.locator("summary").innerText()).trim());
    await g.locator("summary").click();
  }
  await page.waitForTimeout(500);
  await panel.scrollIntoViewIfNeeded();
  await shot("04_research_page_key_conclusions");
  const summaryLine = await panel.locator("p.key-conclusions-summary").innerText();
  const rows = panel.locator("tr.key-conclusion-row");
  const total = await rows.count();
  const cells = [];
  for (let i = 0; i < total; i++) {
    const tds = rows.nth(i).locator("td");
    cells.push({
      statement: (await tds.nth(0).innerText()).split("\n")[0].slice(0, 120),
      agent_wrote_verified_chip: (await tds.nth(0).innerText()).includes("Agent wrote “verified”"),
      source_support: (await tds.nth(1).locator(".evidence-trace-chip").innerText()).trim(),
      alpha_match: (await tds.nth(2).locator(".evidence-trace-chip").innerText()).trim(),
      stance: (await tds.nth(3).locator(".evidence-trace-chip").innerText()).trim(),
      scoring: (await tds.nth(4).locator(".evidence-trace-chip").innerText()).trim(),
    });
  }
  const counts = (key) => cells.reduce((m, c) => ((m[c[key]] = (m[c[key]] ?? 0) + 1), m), {});
  const keyView = await keyRows();
  const openRow = async (needle, shotName) => {
    const row = rows.filter({ hasText: needle }).first();
    if (!(await row.count())) return { row_found: false };
    // Playwright's hasText is case-insensitive: identify the very same (first) row in the API's key view the same way
    const apiRow = keyView.find((r) => norm(r.text).toLowerCase().includes(norm(needle).toLowerCase()));
    await row.locator("button", { hasText: "Why these statuses?" }).click();
    // the detail row inserted directly after THIS row (never "the last detail on the page", which may belong to an earlier row)
    const detail = row.locator("xpath=following-sibling::tr[1]").locator(".evidence-trace");
    await detail.waitFor({ timeout: 30000 });
    await page.waitForTimeout(400);
    await detail.scrollIntoViewIfNeeded();
    await detail.screenshot({ path: path.join(OUT, shotName + ".png") });
    const detailText = await detail.innerText();
    return { row_found: true, claim_id: apiRow?.claim_id ?? null, detail_text: detailText, api_vs_ui: apiRow ? await apiVsUi(apiRow.claim_id, detailText) : null };
  };
  const verifiedWording = await openRow("AMD's fundamental inflection is real and verified", "05_row_agent_wrote_verified");
  const relationUnresolved = await openRow("His second overreach is the PEG defense", "06_row_verified_source_relation_unresolved");
  const technical = await openRow("Upside to the Bollinger upper band", "07_row_technical_failure");
  const partial = await openRow("The MACD histogram peaked at 15.05", "08_row_partial_support");
  const calculation = await openRow("Revenue went from $7,685M to $11,536M", "09_row_calculation_reproduced_verification_incomplete");
  const unreproduced = await openRow("receivables grew +20.6% QoQ", "10_row_percentages_not_reproduced_numbers_not_found");
  return {
    groups: groupNames, rows_rendered: total, summary_line: summaryLine,
    status_counts_seen_in_the_rendered_table: { source_support: counts("source_support"), alpha_match: counts("alpha_match"), stance: counts("stance"), scoring: counts("scoring") },
    rows_where_the_agent_wrote_verified: cells.filter((c) => c.agent_wrote_verified_chip).map((c) => ({ statement: c.statement, system_source_support: c.source_support })),
    agent_wrote_verified_but_system_says: {
      detail: verifiedWording,
      observed: verifiedWording.detail_text ? has(verifiedWording.detail_text, "Agent wording", "not a system verification", "No source reference was linked", "NOT_LINKED") : null,
    },
    verified_source_with_unresolved_relation: {
      detail: relationUnresolved,
      observed: relationUnresolved.detail_text ? has(relationUnresolved.detail_text, "Verified: the saved source content supports this claim", "Relation to the Alpha is not established", "No model stance judgment was obtained", "RELATION_NOT_SUPPORTING") : null,
    },
    calculation_reproduced_but_verification_incomplete: {
      detail: calculation,
      observed: calculation.detail_text ? has(calculation.detail_text,
        "Verification not completed (technical failure)", "TECHNICAL_INCOMPLETE", "Linked source",
        "Calculations reproduced from the saved rows", "gross margin", "Gross Profit / Total Revenue @ 2025-06-30", "Gross Profit / Total Revenue @ 2026-06-30",
        "REPRODUCED", "Result 39.80%", "Result 53.77%", "Arithmetic reproduced from the saved rows only",
        "negative $134M", "-134.0M") : null,
      the_failed_verification_names_no_source_it_used: calculation.detail_text ? !calculation.detail_text.includes("Source the verification used") : null,
    },
    technical_failure: { detail: technical, observed: technical.detail_text ? has(technical.detail_text, "Verification not completed (technical failure)", "timed out and was not retried", "TECHNICAL_INCOMPLETE", "Technical failure", "timeout") : null,
      the_failed_verification_names_no_source_it_used: technical.detail_text ? !technical.detail_text.includes("Source the verification used") : null },
    partial_support: { detail: partial, observed: partial.detail_text ? has(partial.detail_text, "Partly supported", "Not backed by the source", "PARTIAL_SUPPORT", "Numbers not found in the saved data", "15.05", "this is not a verdict on the claim") : null },
    percentages_not_reproduced_and_numbers_not_found: {
      detail: unreproduced,
      // the first row (in report order) containing this sentence is a trader claim; the saved data requires exactly what is listed here
      observed: unreproduced.detail_text ? has(unreproduced.detail_text, "Verification not completed (technical failure)", "Percentages not reproduced from the saved rows", "+20.6%", "+12.5%",
        "Numbers not found in the saved data", "15.05", "44.5M", "is not thereby wrong", "this is not a verdict on the claim") : null,
    },
    api_vs_ui_every_opened_row: Object.fromEntries([["agent_wrote_verified", verifiedWording], ["relation_unresolved", relationUnresolved], ["technical_failure", technical], ["partial_support", partial], ["calculation_row", calculation], ["percentages_not_reproduced", unreproduced]]
      .map(([k, v]) => [k, v.api_vs_ui ? { claim_id: v.claim_id, required: v.api_vs_ui.strings_the_saved_data_requires_on_screen, missing_on_screen: v.api_vs_ui.missing_on_screen } : null])),
    all_rows: cells,
  };
});

// ------------------------------------------------------------------ 3. Export (GET): exported trace == what the API (and so the UI) served
await step("export_equals_api_and_ui", async () => {
  await page.goto(`${WEB}/runs/${EXEC}/research`, { waitUntil: "networkidle", timeout: 90000 });
  const button = page.locator("button", { hasText: /^Export research$/ });
  if (!(await button.count())) return { export_button_found: false };
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), button.first().click()]);
  const file = path.join(OUT, "exported_from_browser.zip");
  await download.saveAs(file);
  const listing = execFileSync("/usr/bin/unzip", ["-Z1", file]).toString().trim().split("\n");
  const read = (name) => JSON.parse(execFileSync("/usr/bin/unzip", ["-p", file, name], { maxBuffer: 1 << 28 }).toString());
  const exported = read("evidence_trace.json");
  const runDir = `/Users/xiangmao/COMQUTOR-Alpha-/outputs/runs/${EXEC}`;
  const onDisk = JSON.parse(fs.readFileSync(path.join(runDir, "evidence_trace.json"), "utf8"));
  const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const canon = (x) => (Array.isArray(x) ? x.map(canon) : x && typeof x === "object" ? Object.fromEntries(Object.keys(x).sort().filter((k) => x[k] !== undefined).map((k) => [k, canon(x[k])])) : x);
  const sameCanonical = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
  const claims = [FA + "31", FA + "33", FA + "36", PM + "10", PM + "3", PM + "4"];
  const perClaim = {};
  for (const claimId of claims) {
    const api = await apiJson(`/api/research/${EXEC}/evidence-trace?claim_id=${encodeURIComponent(claimId)}`);
    perClaim[claimId.split(":claim:")[0].split(":")[1] + "#" + claimId.split(":claim:")[1]] = {
      in_export: claimId in exported.items, export_item_equals_api_item: claimId in exported.items && sameJson(exported.items[claimId], api.item),
    };
  }
  const keyApi = await apiJson(`/api/research/${EXEC}/evidence-trace?scope=key`);
  const wholeApi = await apiJson(`/api/research/${EXEC}/evidence-trace`);
  const a301 = exported.alphas.find((a) => a.alpha_id === "A301");
  const sourceRegistryInZip = listing.includes("source_registry.json");
  return {
    zip_members: listing, zip_bytes: fs.statSync(file).size,
    exported_trace_equals_the_file_on_disk: sameJson(exported, onDisk),
    per_claim_export_equals_api: perClaim,
    exported_key_conclusions_equal_api_key_view: sameJson(exported.key_conclusions, keyApi.key_conclusions),
    exported_calculations_equal_api: sameJson(exported.calculations, wholeApi.calculations),
    exported_calculation_summary: { claims_with_reproduced_calculations: exported.calculations.claims_with_reproduced_calculations, reproduced_calculation_count: exported.calculations.reproduced_calculation_count,
      includes_portfolio_manager_claim_4: exported.calculations.calculations.some((c) => c.claim_id === PM + "4"), scope_note: exported.calculations.scope_note },
    api_whole_artifact_equals_exported_file_ignoring_key_order: sameCanonical({ ...wholeApi, status: undefined }, { ...onDisk, status: undefined }),
    exported_a301: { score: a301.activation_score, level: a301.level, claims_in_pool: a301.claims_in_pool, independent_facts: a301.independent_facts, distinct_agents: a301.distinct_agents, distinct_sources: a301.distinct_sources, fact_groups: a301.fact_groups.map((g) => g.member_claim_ids.map((c) => c.split(":claim:")[1])) },
    exported_item_count: exported.item_count, source_registry_also_in_zip: sourceRegistryInZip,
    exported_claim_31_text: { used_location: exported.items[FA + "31"].source_support.content_support.used_location, quote: exported.items[FA + "31"].source_support.content_support.supporting_quote_or_data },
  };
});

fs.writeFileSync(path.join(HERE, "browser_walkthrough_round21_result.json"), JSON.stringify(log, null, 1));
console.log(JSON.stringify({
  blocked_non_get_requests: log.blocked_non_get_requests, console_errors: log.console_errors.slice(0, 5), failed_requests: log.failed_requests.slice(0, 5),
  step_errors: Object.entries(log.steps).filter(([, v]) => v && v.error).map(([k, v]) => [k, v.error]),
}, null, 1));
await browser.close();
