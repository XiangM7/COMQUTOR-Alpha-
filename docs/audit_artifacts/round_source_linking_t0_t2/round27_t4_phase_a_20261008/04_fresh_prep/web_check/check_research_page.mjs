// T4 Phase A: confirm the web page the owner will use is connected to the prepared Fresh instance and shows its configuration.
// Opens http://127.0.0.1:5177/research ONLY: never types into the Ticker box, never clicks anything on the form. Every non-GET request to
// the API and every non-loopback request is aborted and logged (must be empty). Writes page_check.json + research_page.png here.
//
//   node check_research_page.mjs
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../../../../..");
const { chromium } = await import(path.join(repo, "frontend/node_modules/playwright-core/index.mjs"));
const BASE = "http://127.0.0.1:5177";
const API = "http://127.0.0.1:8002";
const blocked = [];
const apiGets = [];
const browser = await chromium.launch({ headless: true, executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.route("**/*", (route) => {
  const req = route.request();
  const host = new URL(req.url()).hostname;
  if (!["127.0.0.1", "localhost"].includes(host)) { blocked.push({ reason: "non_loopback", method: req.method(), url: req.url() }); return route.abort(); }
  if (req.url().startsWith(API) && req.method() !== "GET") { blocked.push({ reason: "non_get_to_api", method: req.method(), url: req.url() }); return route.abort(); }
  if (req.url().startsWith(API)) apiGets.push(req.url().slice(API.length));
  return route.continue();
});
const page = await context.newPage();
await page.goto(`${BASE}/research`);
await page.waitForTimeout(4000);
const status = (await page.getByRole("status").first().innerText()).trim();
const start = page.getByRole("button", { name: "Start research" });
const ticker = page.getByRole("textbox", { name: "Ticker" });
const result = {
  checked_at: new Date().toISOString(),
  url: `${BASE}/research`,
  api_base_seen_by_page: [...new Set(apiGets.map((u) => u.split("?")[0]))].sort(),
  status_line: status,
  start_research_button: { present: (await start.count()) === 1, disabled: await start.isDisabled() },
  ticker_box_value: await ticker.inputValue(),
  form_touched: false,
  blocked_requests: blocked,
};
await page.screenshot({ path: path.join(here, "research_page.png") });
await browser.close();
await fs.writeFile(path.join(here, "page_check.json"), JSON.stringify(result, null, 1) + "\n");
console.log(JSON.stringify(result, null, 1));
process.exit(blocked.length === 0 ? 0 : 3);
