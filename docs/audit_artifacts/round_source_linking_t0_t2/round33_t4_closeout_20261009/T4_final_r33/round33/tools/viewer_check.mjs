// T4 round 33 (2026-10-09): read-only check of the final viewing entry (web 5179 -> API 8005, final code) on the saved second
// NVDA Fresh run. No video (the Round 32 final video is kept). Derived from round32 07_demo/t4_final_demo_recorder.mjs.
//
//   node tools/viewer_check.mjs --base http://127.0.0.1:5179 --api http://127.0.0.1:8005 --out 02_viewer/check
//
// Safety (enforced): every non-GET request to the API origin and every non-loopback request is ABORTED and logged (exit 3 if
// any); the script never types into the Ticker box and never clicks "Start research".
// Checks: /ready code identity; API stage_disclosure (saved to a file, compared afterwards with Round 32's saved copy);
// History -> reopen the run (twice) and a full page reload, each time reading the "Processing completeness" panel;
// Export research download (sha256 compared afterwards with the Round 30 / 32 value).
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../../../..");
const { chromium } = await import(path.join(repo, "frontend/node_modules/playwright-core/index.mjs"));
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, a) => (v.startsWith("--") ? [...acc, [v.slice(2), a[i + 1]]] : acc), []));
const BASE = args.base ?? "http://127.0.0.1:5179";
const API = args.api ?? "http://127.0.0.1:8005";
const OUT = path.resolve(args.out);
const RUN = "12591384-0b26-470d-a99d-a49c00be440b";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await fs.mkdir(path.join(OUT, "screens"), { recursive: true });
await fs.mkdir(path.join(OUT, "exports"), { recursive: true });

const ready = await (await fetch(`${API}/ready`)).json();
const detail = await (await fetch(`${API}/api/research/${RUN}`)).json();
await fs.writeFile(path.join(OUT, "api_stage_disclosure.json"), JSON.stringify(detail.stage_disclosure ?? null, null, 1) + "\n");

const blocked = [];
const apiGets = [];
const steps = [];
const browser = await chromium.launch({ headless: true, executablePath: CHROME });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
await context.route("**/*", (route) => {
  const req = route.request();
  const url = new URL(req.url());
  if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
    blocked.push({ reason: "non_loopback", method: req.method(), url: req.url() });
    return route.abort();
  }
  if (req.url().startsWith(API) && req.method() !== "GET") {
    blocked.push({ reason: "non_get_to_api", method: req.method(), url: req.url() });
    return route.abort();
  }
  if (req.url().startsWith(API)) apiGets.push(req.url().slice(API.length));
  return route.continue();
});
const page = await context.newPage();

async function waitResearchLoaded() {
  await page.getByRole("heading", { name: /Research summary|This research run failed/ }).first().waitFor({ timeout: 120000 });
  await sleep(1200);
}

async function readDisclosure(name) {
  const panel = page.getByTestId("stage-disclosure");
  await panel.waitFor({ timeout: 60000 });
  await panel.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await sleep(800);
  const text = await panel.innerText();
  await page.screenshot({ path: path.join(OUT, "screens", `${name}.png`) });
  return text;
}

async function step(name, fn) {
  try {
    const value = await fn();
    steps.push({ name, ok: true, url: page.url(), value: value ?? null });
  } catch (e) {
    steps.push({ name, ok: false, url: page.url(), error: String(e).slice(0, 300) });
    await page.screenshot({ path: path.join(OUT, "screens", `${name}_error.png`) }).catch(() => {});
  }
}

async function reopenFromHistory() {
  await page.goto(BASE + "/research");
  await sleep(2500);
  await page.getByRole("button", { name: "Recent runs" }).click();
  await sleep(1800);
  await page.locator(`a[href*="${RUN}"]`).first().click();
  await waitResearchLoaded();
}

await step("1_history_reopen", async () => {
  await reopenFromHistory();
  return { disclosure_text: await readDisclosure("1_history_reopen_disclosure") };
});
await step("2_history_reopen_again", async () => {
  await page.goto(BASE + "/");
  await sleep(1500);
  await reopenFromHistory();
  return { disclosure_text: await readDisclosure("2_history_reopen_again_disclosure") };
});
await step("3_full_page_reload", async () => {
  await page.reload();
  await waitResearchLoaded();
  return { disclosure_text: await readDisclosure("3_reload_disclosure") };
});
let exportFile = null;
await step("4_export", async () => {
  const button = page.getByRole("button", { name: "Export research" });
  await button.scrollIntoViewIfNeeded();
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), button.click()]);
  exportFile = path.join(OUT, "exports", download.suggestedFilename());
  await download.saveAs(exportFile);
  await page.screenshot({ path: path.join(OUT, "screens", "4_export.png") });
  return { file: path.basename(exportFile) };
});

await context.close();
await browser.close();
const result = {
  checked_at: new Date().toISOString(), base: BASE, api: API, run_id: RUN, browser: "system Google Chrome (playwright-core), headless",
  ready: { status: ready.status, real_execution: ready.real_execution, database_backend: ready.database_backend,
           week2_semantic_enabled: ready.week2_semantic?.enabled, code_identity: ready.code_identity },
  api_detail: { status: detail.status, stage_disclosure_present: "stage_disclosure" in detail },
  steps,
  export_file: exportFile ? path.relative(OUT, exportFile) : null,
  export_sha256: exportFile ? createHash("sha256").update(await fs.readFile(exportFile)).digest("hex") : null,
  safety: { blocked_requests: blocked, non_get_api_requests_blocked: blocked.filter((b) => b.reason === "non_get_to_api").length,
            start_research_clicked: false, api_gets: apiGets },
};
await fs.writeFile(path.join(OUT, "viewer_check_result.json"), JSON.stringify(result, null, 1) + "\n");
console.log(JSON.stringify({ steps: steps.map((s) => `${s.name}:${s.ok ? "ok" : "FAILED"}`), export_sha256: result.export_sha256,
  blocked: blocked.length, code: `${ready.code_identity?.tracked_diff_sha256?.slice(0, 8)}/${ready.code_identity?.untracked_runtime_source_sha256?.slice(0, 8)}` }, null, 1));
process.exit(blocked.length ? 3 : steps.every((s) => s.ok) ? 0 : 1);
