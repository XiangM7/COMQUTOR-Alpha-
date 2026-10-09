// T4 round 32: the FINAL-version demo. Walks the EXISTING web UI, served by the FINAL code (isolated read-only instance on a
// restored copy of the T4 database), over the SAVED results of the second NVDA Fresh run plus the labelled SIMULATED failure
// and the SNDK historical run. It never starts research. Derived from round30_t4_nvda_fresh_run2_20261009/video/t4_fresh_recorder.mjs.
//
//   node t4_final_demo_recorder.mjs --base http://127.0.0.1:5179 --api http://127.0.0.1:8005 --out <dir>
//
// Safety (enforced, not just intended):
//   * every non-GET request to the API origin is ABORTED and logged -- the recorder cannot submit research even by accident;
//     the log must be empty at the end (exit 3 otherwise);
//   * every request to a non-loopback host is aborted and logged;
//   * the recorder never types into the Ticker box and never clicks "Start research".
// Video: Chrome DevTools screencast frames assembled with the local /opt/homebrew/bin/ffmpeg by their own timestamps.
// BURNED-IN CAPTIONS: the dark bar is a recording annotation drawn into the page (so it is in the video pixels): what is shown
// (FRESH saved run / SIMULATED / FROZEN historical), the full run_id, which code serves the page and which code produced the
// run. Headless Chrome's screencast frames are 87 px shorter than the viewport (measured: viewport 900 -> frame 813; viewport
// 813 -> frame 726), so the bar sits 87 px above the viewport bottom -- the lowest strip that reaches the video -- and it is
// re-drawn after every navigation from sessionStorage.
import { execFileSync } from "node:child_process";
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
const OUT = path.resolve(args.out ?? path.join(here, "recording_final"));
const RUNS = {
  fresh: "12591384-0b26-470d-a99d-a49c00be440b",
  simulated: "t4-simulated-interrupted-20261008",
  sndk: "dependency-20261008T213350Z-89497ab9",
};
const FRESH_CODE = "7a9aefa+uncommitted(1b53b921/38ef636f)";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const SCREENCAST_CROP_PX = 87;
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
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
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

await context.addInitScript((cropPx) => {
  const draw = (lines) => {
    let el = document.getElementById("__t4_overlay");
    if (!el) {
      el = document.createElement("div");
      el.id = "__t4_overlay";
      el.setAttribute("aria-hidden", "true");
      el.style.cssText = `position:fixed;left:0;right:0;bottom:${cropPx}px;z-index:2147483647;background:rgba(17,24,39,.94);color:#f9fafb;` +
        "font:12px/1.45 ui-monospace,Menlo,monospace;padding:6px 14px;pointer-events:none;white-space:pre-wrap";
      (document.body || document.documentElement).appendChild(el);
    }
    el.textContent = lines.join("\n");
  };
  window.__t4Caption = (lines) => {
    try { sessionStorage.setItem("__t4_caption", JSON.stringify(lines)); } catch { /* ignore */ }
    draw(lines);
  };
  const redraw = () => {
    try {
      const saved = sessionStorage.getItem("__t4_caption");
      if (saved) draw(JSON.parse(saved));
    } catch { /* ignore */ }
  };
  document.addEventListener("DOMContentLoaded", redraw);
  setInterval(redraw, 400);  // the app re-renders its root; keep the bar present
}, SCREENCAST_CROP_PX);

const page = await context.newPage();
const t0 = Date.now();
const frames = [];
const cdp = await context.newCDPSession(page);
cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
  const file = path.join(OUT, ".frames", `${String(frames.length).padStart(6, "0")}.jpg`);
  frames.push({ file, t: metadata.timestamp, h: metadata.deviceHeight, wall: Date.now() - t0 });
  await fs.writeFile(file, Buffer.from(data, "base64"));
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 85, maxWidth: 1440, maxHeight: 900, everyNthFrame: 1 });

const KIND = {
  instance: "FINAL CODE · read-only instance (real execution off) · nothing is submitted by this recording",
  fresh: `FRESH (saved real run) · NVDA Fresh Run #2, started by Xiang Mao on the web page; produced by code ${FRESH_CODE}`,
  simulated: "SIMULATED · TEST-INJECTED FAILURE (Round 27): the instance was restarted on purpose while this run was running",
  sndk: "FROZEN / HISTORICAL · SNDK saved run re-evaluated (Round 27) · no research started",
};

async function caption(scene, runId, kind, text) {
  const lines = [
    KIND[kind],
    `scene ${scene}: ${text}`,
    `run_id ${runId ?? "—"} · page served by FINAL code ${code} · ${db}`,
  ];
  await page.evaluate((l) => window.__t4Caption?.(l), lines).catch(() => {});
}

async function scene(id, runId, kind, text, fn) {
  const started = Date.now() - t0;
  let ok = true;
  let error = null;
  try {
    await caption(id, runId, kind, text);
    await fn();
    await caption(id, runId, kind, text);
    await sleep(1500);
  } catch (e) {
    ok = false;
    error = String(e).slice(0, 300);
    notes.push(`scene ${id} incomplete: ${error}`);
  }
  const shot = `screens/${id}.png`;
  await page.screenshot({ path: path.join(OUT, shot) }).catch(() => {});
  scenes.push({ id, run_id: runId ?? null, kind, caption: text, url: page.url(), started_ms: started, ended_ms: Date.now() - t0, ok, error, screenshot: shot });
}

async function goto(p, waitMs = 2500) {
  await page.goto(BASE + p);
  await sleep(waitMs);
}

async function waitResearchLoaded() {
  await page.getByRole("heading", { name: /Research summary|This research run failed/ }).first().waitFor({ timeout: 120000 });
  await sleep(900);
}

const scroll = async (locator) => { await locator.scrollIntoViewIfNeeded(); await sleep(900); };

async function openKeyConclusion(groupText, rowText) {
  const region = page.getByRole("region", { name: "Key conclusions verification status" });
  await scroll(region);
  const group = region.locator("details", { hasText: rowText }).first();
  if (!(await group.getAttribute("open").catch(() => null))) await group.locator("summary").first().click();
  await sleep(1000);
  const row = group.locator("tr", { hasText: rowText }).first();
  await scroll(row);
  await row.getByRole("button", { name: "Why these statuses?" }).click();
  await sleep(1800);
  return row;
}

await scene("01_instance", null, "instance", "Research page of the isolated FINAL-code instance: database and code identity in the status line (form not touched)", async () => {
  await goto("/research", 3000);
  await page.getByRole("status").first().waitFor();
});

await scene("02_history_reopen", RUNS.fresh, "fresh", "History: Recent runs (read from PostgreSQL) -> reopen the saved second NVDA Fresh Run", async () => {
  await page.getByRole("button", { name: "Recent runs" }).click();
  await sleep(1800);
  await page.locator(`a[href*="${RUNS.fresh}"]`).first().click();
  await waitResearchLoaded();
});

await scene("03_summary_and_disclosure", RUNS.fresh, "fresh", "Research summary: completed; Processing completeness lists the degraded sub-steps (enrichment fallback, verification not sent / not accepted, model structure extraction 0 edges)", async () => {
  await scroll(page.getByRole("heading", { name: "Research summary" }));
  const disclosure = page.getByTestId("stage-disclosure");
  await disclosure.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await sleep(4000);
});

await scene("04_key_conclusion_source", RUNS.fresh, "fresh", "Click a key conclusion (partial support) -> four separate checks -> the saved market-snapshot fragment it rests on", async () => {
  await openKeyConclusion("Synthesis of the Risk Debate", "The tactical setup is genuinely ambiguous");
  const material = page.getByText("Source material and where the claim sits in it").first();
  await material.waitFor({ timeout: 30000 });
  await material.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.mouse.wheel(0, -120);
  await sleep(3500);
});

await scene("05_calculation_basis", RUNS.fresh, "fresh", "Calculation basis (revenue +106% YoY): saved rows, matched numbers, what was / was not reproduced", async () => {
  const row = await openKeyConclusion("The Decisive Analytical Points", "growing revenue 106%");
  await sleep(1000);
  const detail = row.locator("xpath=following-sibling::tr[1]");
  const target = detail.getByText(/Saved rows|Calculations reproduced|How it was verified/).first();
  if (await target.count()) await target.evaluate((el) => el.scrollIntoView({ block: "start" }));
  else await detail.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await sleep(3500);
});

await scene("06_insufficient_evidence", RUNS.fresh, "fresh", "Insufficient evidence: the model judged the saved material insufficient for this conclusion -> not verified, not scored", async () => {
  const row = await openKeyConclusion("trader", "Position Sizing: Maintain existing core exposure");
  await row.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.mouse.wheel(0, -60);
  await sleep(3500);
});

await scene("07_structure_graph", RUNS.fresh, "fresh", "Structure Graph: factor nodes with scores; node detail (graph built; model structure extraction contributed 0 edges)", async () => {
  await page.getByRole("link", { name: "Structure Graph" }).first().click();
  await page.getByRole("heading", { name: /Structure graph — / }).waitFor({ timeout: 60000 });
  await sleep(1500);
  const node = page.locator(".structure-graph-node, [role=button][aria-label*='Score']").first();
  if (await node.count()) await node.click();
  else await page.getByRole("button", { name: /Score/ }).first().click();
  await sleep(2500);
});

await scene("08_conflict_radar", RUNS.fresh, "fresh", "Conflict Radar: NO main conflict -- candidate / rejected pairs with reasons (not a failure)", async () => {
  await page.getByRole("link", { name: "Conflict Radar" }).first().click();
  await page.getByRole("heading", { name: /Conflict radar — / }).waitFor({ timeout: 60000 });
  await sleep(1500);
  const pairs = page.getByRole("heading", { name: "Candidate and rejected pairs" });
  if (await pairs.count()) await scroll(pairs);
  await sleep(2000);
});

await scene("09_simulated_failure", RUNS.simulated, "simulated", "SIMULATED (test-injected) failure: restart mid-run -> failed, SERVER_SHUTDOWN, nothing resumed", async () => {
  await goto(`/runs/${RUNS.simulated}/research`, 1000);
  await waitResearchLoaded();
  await sleep(3000);
});

await scene("10_sndk_no_main_conflict", RUNS.sndk, "sndk", "SNDK historical result: no main conflict (database row, saved conflicts.json and this page agree)", async () => {
  await goto(`/runs/${RUNS.sndk}/conflicts`, 1000);
  await page.getByRole("heading", { name: /Conflict radar — / }).waitFor({ timeout: 90000 });
  await sleep(3000);
});

let exportFile = null;
await scene("11_export", RUNS.fresh, "fresh", "Export research: the saved Fresh run's ZIP (compared with the run directory and the Round 30 hash after recording)", async () => {
  await goto(`/runs/${RUNS.fresh}/research`, 1000);
  await waitResearchLoaded();
  const button = page.getByRole("button", { name: "Export research" });
  await scroll(button);
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), button.click()]);
  exportFile = path.join(OUT, "exports", download.suggestedFilename());
  await download.saveAs(exportFile);
  await sleep(2000);
});

await caption("end", null, "instance", "end of walkthrough");
await sleep(1500);
await cdp.send("Page.stopScreencast").catch(() => {});
await sleep(500);
await page.close();
await context.close();
await browser.close();
const list = frames.map((f, i) => `file '${f.file}'\nduration ${Math.max(0.04, ((frames[i + 1]?.t ?? f.t + 1.5) - f.t)).toFixed(3)}`);
if (frames.length) list.push(`file '${frames[frames.length - 1].file}'`);
const concat = path.join(OUT, ".frames", "concat.txt");
await fs.writeFile(concat, list.join("\n") + "\n");
const finalVideo = path.join(OUT, "t4_demo_final.mp4");
execFileSync("/opt/homebrew/bin/ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", concat,
  "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2,fps=25", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", finalVideo]);
// scene -> video time: the video shows frame i from the sum of the previous frames' durations (same rule as the concat list
// above); a scene starts in the video at the first frame received at or after the scene's own start time
const videoTimes = [];
let acc = 0;
for (let i = 0; i < frames.length; i += 1) {
  videoTimes.push(acc);
  acc += Math.max(0.04, ((frames[i + 1]?.t ?? frames[i].t + 1.5) - frames[i].t));
}
for (const s of scenes) {
  const i0 = frames.findIndex((f) => f.wall >= s.started_ms);
  const i1 = frames.findIndex((f) => f.wall >= s.ended_ms);
  s.video_start_s = i0 >= 0 ? Number(videoTimes[i0].toFixed(2)) : null;
  s.video_end_s = i1 >= 0 ? Number(videoTimes[i1].toFixed(2)) : Number(acc.toFixed(2));
}
await fs.rm(path.join(OUT, ".frames"), { recursive: true, force: true });
const frameHeights = [...new Set(frames.map((f) => f.h))];

const result = {
  label: "FINAL", base: BASE, api: API, recorded_at: new Date().toISOString(), browser: "system Google Chrome (playwright-core), headless",
  ready_at_start: { status: ready.status, real_execution: ready.real_execution, live_semantic_pipeline: ready.live_semantic_pipeline,
                    database_backend: ready.database_backend, week2_semantic: ready.week2_semantic, code_identity: ci },
  runs: RUNS, fresh_run_code: FRESH_CODE, scenes, notes, export_file: exportFile ? path.relative(OUT, exportFile) : null,
  export_sha256: exportFile ? createHash("sha256").update(await fs.readFile(exportFile)).digest("hex") : null,
  video: path.basename(finalVideo), screencast_frames: frames.length, screencast_frame_heights: frameHeights, caption_bar_offset_px: SCREENCAST_CROP_PX,
  safety: { blocked_requests: blocked, non_get_api_requests_blocked: blocked.filter((b) => b.reason === "non_get_to_api").length,
            research_submissions_attempted: blocked.filter((b) => b.reason === "non_get_to_api" && /\/api\/research$/.test(new URL(b.url).pathname)).length,
            api_get_requests: apiGets.length, api_get_paths: [...new Set(apiGets.map((u) => u.split("?")[0]))].sort() },
};
await fs.writeFile(path.join(OUT, "scenes.json"), JSON.stringify(result, null, 1));
console.log(JSON.stringify({ scenes: scenes.map((s) => `${s.id}:${s.ok ? "ok" : "INCOMPLETE"}`), blocked: blocked.length, export: result.export_file,
                             export_sha256: result.export_sha256, frame_heights: frameHeights, video: result.video }, null, 1));
process.exit(result.safety.non_get_api_requests_blocked === 0 ? 0 : 3);
