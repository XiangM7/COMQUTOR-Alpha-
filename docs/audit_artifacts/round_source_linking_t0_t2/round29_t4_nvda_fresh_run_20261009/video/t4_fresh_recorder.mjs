// T4 NVDA Fresh Run video (round 29): walks the EXISTING web UI over the owner-started Fresh Run; it never starts research.
// Derived from round27_t4_phase_a_20261008/05_demo/t4_demo_recorder.mjs (same safety guards, same overlay, same screencast).
//
//   node t4_demo_recorder.mjs --base http://127.0.0.1:5177 --api http://127.0.0.1:8002 --out <dir> --label FROZEN [--runs <json>]
//
// Safety (enforced, not just intended):
//   * every non-GET request to the API origin is ABORTED and logged (POST /api/research, review submissions, replay) -- the
//     recorder cannot submit research even by accident; the log must be empty at the end (exit 3 otherwise);
//   * every request to a non-loopback host is aborted and logged;
//   * the recorder never types into the Ticker box and never clicks "Start research".
// Uses the system Chrome (playwright-core + executablePath). Video: Chrome's own DevTools screencast frames (Playwright's
// recordVideo needs a separately downloaded ffmpeg build, and this round makes no external downloads), assembled with the
// local /opt/homebrew/bin/ffmpeg into an H.264 MP4 using each frame's own timestamp. Per-scene screenshots and scenes.json
// land in --out as well.
// The overlay at the bottom of every frame is a RECORDING ANNOTATION (label, scene, run_id, code identity), not product UI.
import { execFileSync } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../../../..");
const { chromium } = await import(path.join(repo, "frontend/node_modules/playwright-core/index.mjs"));

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, a) => (v.startsWith("--") ? [...acc, [v.slice(2), a[i + 1]]] : acc), []));
const BASE = args.base ?? "http://127.0.0.1:5177";
const API = args.api ?? "http://127.0.0.1:8002";
const OUT = path.resolve(args.out ?? path.join(here, "recording"));
const LABEL = args.label ?? "FROZEN";
const RUNS = args.runs ? JSON.parse(args.runs) : { fresh: "fa642639-8d93-4f9a-9de1-2c4d789eade8" };
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await fs.rm(OUT, { recursive: true, force: true });
await fs.mkdir(path.join(OUT, "screens"), { recursive: true });
await fs.mkdir(path.join(OUT, "exports"), { recursive: true });
await fs.mkdir(path.join(OUT, ".frames"), { recursive: true });

const blocked = [];
const apiGets = [];
const scenes = [];
const notes = [];
const browser = await chromium.launch({ headless: true, executablePath: CHROME });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  acceptDownloads: true,
});
await context.route("**/*", (route) => {
  const req = route.request();
  const url = new URL(req.url());
  const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
  if (!loopback) {
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

const ready = await (await fetch(`${API}/ready`)).json();
const ci = ready.code_identity ?? {};
const code = ci.git_head ? `${ci.git_head.slice(0, 7)}${ci.uncommitted_changes ? `+uncommitted(${ci.tracked_diff_sha256.slice(0, 8)}/${ci.untracked_runtime_source_sha256.slice(0, 8)})` : ""}` : "unknown";
const db = ready.database_backend ? `${ready.database_backend.dialect} ${ready.database_backend.database}` : "unknown";

await context.addInitScript(() => {
  window.__t4Caption = (lines) => {
    let el = document.getElementById("__t4_overlay");
    if (!el) {
      el = document.createElement("div");
      el.id = "__t4_overlay";
      el.setAttribute("aria-hidden", "true");
      el.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:2147483647;background:rgba(17,24,39,.92);color:#f9fafb;" +
        "font:12px/1.45 ui-monospace,Menlo,monospace;padding:6px 14px;pointer-events:none;white-space:pre-wrap";
      document.documentElement.appendChild(el);
    }
    el.textContent = lines.join("\n");
  };
});
const page = await context.newPage();
const t0 = Date.now();
const frames = [];
const cdp = await context.newCDPSession(page);
cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const file = path.join(OUT, ".frames", `${String(frames.length).padStart(6, "0")}.jpg`);
  frames.push({ file, t: metadata.timestamp });
  await fs.writeFile(file, Buffer.from(data, "base64"));
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: 1440, maxHeight: 900, everyNthFrame: 1 });

async function caption(scene, runId, text) {
  const lines = [
    `${LABEL} · NVDA Fresh Run started by the owner on the web page — this recording only reads it (no request is submitted)`,
    `scene ${scene}: ${text}`,
    `run_id ${runId ?? "—"} · code ${code} · ${db}`,
  ];
  await page.evaluate((l) => window.__t4Caption?.(l), lines).catch(() => {});
}

async function scene(id, runId, text, fn) {
  const started = Date.now() - t0;
  let ok = true;
  let error = null;
  try {
    await caption(id, runId, text);
    await fn();
    await caption(id, runId, text);
    await sleep(1200);
  } catch (e) {
    ok = false;
    error = String(e).slice(0, 300);
    notes.push(`scene ${id} incomplete: ${error}`);
  }
  const shot = `screens/${id}.png`;
  await page.screenshot({ path: path.join(OUT, shot) }).catch(() => {});
  scenes.push({ id, run_id: runId ?? null, caption: text, url: page.url(), started_ms: started, ended_ms: Date.now() - t0, ok, error, screenshot: shot });
}

async function goto(p, waitMs = 2500) {
  await page.goto(BASE + p);
  await sleep(waitMs);
}

async function waitResearchLoaded() {
  await page.getByRole("heading", { name: /Research summary|This research run failed/ }).first().waitFor({ timeout: 90000 });
  await sleep(800);
}

const scroll = async (locator) => { await locator.scrollIntoViewIfNeeded(); await sleep(900); };

// 1. the instance the owner used
await scene("01_instance", null, "Research page of the T4 instance the owner used: database, profile and code identity in the status line (form not touched)", async () => {
  await goto("/research", 3000);
  await page.getByRole("status").first().waitFor();
});

// 2. history: reopen the Fresh Run from Recent runs (read from PostgreSQL)
await scene("02_history_reopen", RUNS.fresh, "History: Recent runs (PostgreSQL) -> reopen the NVDA Fresh Run started by the owner", async () => {
  await page.getByRole("button", { name: "Recent runs" }).click();
  await sleep(1800);
  await page.locator(`a[href*="${RUNS.fresh}"]`).first().click();
  await waitResearchLoaded();
});

await scene("03_research_summary", RUNS.fresh, "Research summary: partial — 2 of 870 Alpha calls failed (1 timeout, 1 unknown); no conclusion is overstated", async () => {
  await scroll(page.getByRole("heading", { name: "Research summary" }));
  await sleep(1500);
});

// 3. key conclusion -> saved source fragment
await scene("04_key_conclusion_source", RUNS.fresh, "Key conclusion (verified) -> four separate checks -> the saved market-snapshot fragment it rests on", async () => {
  const region = page.getByRole("region", { name: "Key conclusions verification status" });
  await scroll(region);
  const group = region.locator("details", { hasText: "Synthesis of the Risk Debate" }).first();
  await group.locator("summary").click();
  await sleep(1000);
  const row = group.locator("tr", { hasText: "The technical structure is unambiguously bullish" }).first();
  await scroll(row);
  await row.getByRole("button", { name: "Why these statuses?" }).click();
  await sleep(1500);
  const material = page.getByText("Source material and where the claim sits in it").first();
  await material.waitFor({ timeout: 30000 });
  await material.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.mouse.wheel(0, -120);
  await sleep(3000);
});

// 4. calculation basis on a partially supported conclusion
await scene("05_calculation_basis", RUNS.fresh, "Partially supported conclusion (revenue trajectory) -> saved rows, matched numbers, what was / was not reproduced", async () => {
  const region = page.getByRole("region", { name: "Key conclusions verification status" });
  const group = region.locator("details", { hasText: "Synthesis of the Risk Debate" }).first();
  const row = group.locator("tr", { hasText: "revenue compounding" }).first();
  await scroll(row);
  await row.getByRole("button", { name: "Why these statuses?" }).click();
  await sleep(2500);
  const detail = row.locator("xpath=following-sibling::tr[1]");
  const target = detail.getByText(/Saved rows|Calculations reproduced|How it was verified/).first();
  if (await target.count()) {
    await target.evaluate((el) => el.scrollIntoView({ block: "start" }));
  } else {
    await detail.evaluate((el) => el.scrollIntoView({ block: "start" }));
  }
  await sleep(3500);
});

// 5. structure graph
await scene("06_structure_graph", RUNS.fresh, "Structure Graph of the Fresh Run: factor nodes with scores; node detail", async () => {
  await page.getByRole("link", { name: "Structure Graph" }).first().click();
  await page.getByRole("heading", { name: /Structure graph — / }).waitFor({ timeout: 60000 });
  await sleep(1500);
  const node = page.locator(".structure-graph-node, [role=button][aria-label*='Score']").first();
  if (await node.count()) {
    await node.click();
  } else {
    await page.getByRole("button", { name: /Score/ }).first().click();
  }
  await sleep(2000);
});

// 6. conflict radar
await scene("07_conflict_radar", RUNS.fresh, "Conflict Radar: no admitted main conflict (8 candidate / rejected pairs with reasons) — not a failure", async () => {
  await page.getByRole("link", { name: "Conflict Radar" }).first().click();
  await page.getByRole("heading", { name: /Conflict radar — / }).waitFor({ timeout: 60000 });
  await sleep(1500);
  const pairs = page.getByRole("heading", { name: "Candidate and rejected pairs" });
  if (await pairs.count()) await scroll(pairs);
  await sleep(1500);
});

// 7. export
let exportFile = null;
await scene("08_export", RUNS.fresh, "Export research: the Fresh Run's ZIP bundle (checked against the run directory after recording)", async () => {
  await goto(`/runs/${RUNS.fresh}/research`, 1000);
  await waitResearchLoaded();
  const button = page.getByRole("button", { name: "Export research" });
  await scroll(button);
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), button.click()]);
  exportFile = path.join(OUT, "exports", download.suggestedFilename());
  await download.saveAs(exportFile);
  await sleep(1500);
});

await caption("end", null, "end of walkthrough");
await sleep(1500);
await cdp.send("Page.stopScreencast").catch(() => {});
await sleep(500);
await page.close();
await context.close();
await browser.close();
// frame i is shown until frame i+1 arrived (screencast frames come only when the page changes)
const list = frames.map((f, i) => `file '${f.file}'\nduration ${Math.max(0.04, ((frames[i + 1]?.t ?? f.t + 1.5) - f.t)).toFixed(3)}`);
if (frames.length) list.push(`file '${frames[frames.length - 1].file}'`);
const concat = path.join(OUT, ".frames", "concat.txt");
await fs.writeFile(concat, list.join("\n") + "\n");
const finalVideo = path.join(OUT, `t4_demo_${LABEL.toLowerCase()}.mp4`);
execFileSync("/opt/homebrew/bin/ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", concat,
  "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2,fps=25", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", finalVideo]);
await fs.rm(path.join(OUT, ".frames"), { recursive: true, force: true });

const result = {
  label: LABEL, base: BASE, api: API, recorded_at: new Date().toISOString(), browser: "system Google Chrome (playwright-core), headless",
  ready_at_start: { status: ready.status, real_execution: ready.real_execution, live_semantic_pipeline: ready.live_semantic_pipeline,
                    database_backend: ready.database_backend, week2_semantic: ready.week2_semantic, code_identity: ci },
  runs: RUNS, scenes, notes, export_file: exportFile ? path.relative(OUT, exportFile) : null, video: path.basename(finalVideo), screencast_frames: frames.length,
  safety: { blocked_requests: blocked, non_get_api_requests_blocked: blocked.filter((b) => b.reason === "non_get_to_api").length,
            research_submissions_attempted: blocked.filter((b) => b.reason === "non_get_to_api" && /\/api\/research$/.test(new URL(b.url).pathname)).length,
            api_get_requests: apiGets.length, api_get_paths: [...new Set(apiGets.map((u) => u.split("?")[0]))].sort() },
};
await fs.writeFile(path.join(OUT, "scenes.json"), JSON.stringify(result, null, 1));
console.log(JSON.stringify({ scenes: scenes.map((s) => `${s.id}:${s.ok ? "ok" : "INCOMPLETE"}`), blocked: blocked.length, export: result.export_file, video: result.video }, null, 1));
process.exit(result.safety.non_get_api_requests_blocked === 0 ? 0 : 3);
