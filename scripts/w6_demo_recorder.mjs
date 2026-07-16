import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "../frontend/node_modules/playwright/index.mjs";

const [, , baseUrl, outputPath] = process.argv;
if (!baseUrl || !outputPath) {
  throw new Error("Usage: node scripts/w6_demo_recorder.mjs BASE_URL OUTPUT_PATH");
}

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function submitTicker(page, ticker) {
  await page.goto(`${baseUrl}/research`);
  await page.getByLabel("Ticker").fill(ticker);
  await page.getByLabel("Analysis date (optional)").fill("2026-06-30");
  await sleep(700);
  await page.getByRole("button", { name: "Start research" }).click();
  await page.getByRole("heading", { name: "Research summary" }).waitFor();
  await sleep(1200);
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const absoluteOutput = path.resolve(repoRoot, outputPath);
const temporaryVideoDir = path.join(path.dirname(absoluteOutput), ".playwright-video");
await fs.mkdir(path.dirname(absoluteOutput), { recursive: true });
await fs.rm(temporaryVideoDir, { recursive: true, force: true });
await fs.rm(absoluteOutput, { force: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: temporaryVideoDir, size: { width: 1280, height: 720 } },
});
const page = await context.newPage();
const video = page.video();

try {
  await submitTicker(page, "NVDA");
  await page.getByRole("heading", { name: "Analyst findings" }).scrollIntoViewIfNeeded();
  await sleep(1200);

  await page.getByRole("link", { name: "Structure Graph" }).click();
  await page.getByRole("heading", { name: /Structure graph — NVDA/ }).waitFor();
  await sleep(1200);
  const valuationNode = page.getByRole("button", { name: /Valuation Risk.*conflict-related/ });
  await valuationNode.focus();
  await valuationNode.press("Enter");
  await sleep(1200);

  await page.getByRole("link", { name: "Conflict Radar" }).click();
  await page.getByRole("heading", { name: "A101 vs A304" }).first().waitFor();
  await sleep(1200);
  await page.getByRole("heading", { name: "Evidence traceability" }).scrollIntoViewIfNeeded();
  await sleep(1400);

  await submitTicker(page, "QQQ");
  await page.getByRole("link", { name: "Structure Graph" }).click();
  await page.getByRole("heading", { name: /Structure graph — QQQ/ }).waitFor();
  await sleep(1200);
  await page.getByRole("link", { name: "Conflict Radar" }).click();
  await page.getByRole("heading", { name: "All admitted conflicts" }).waitFor();
  await page.getByRole("heading", { name: "A001 vs A501" }).first().scrollIntoViewIfNeeded();
  await sleep(1400);
  await page.getByRole("heading", { name: "A003 vs A501" }).first().scrollIntoViewIfNeeded();
  await sleep(1600);
} finally {
  await context.close();
  if (video) {
    await video.saveAs(absoluteOutput);
  }
  await browser.close();
  await fs.rm(temporaryVideoDir, { recursive: true, force: true });
}

const stats = await fs.stat(absoluteOutput);
if (stats.size === 0) {
  throw new Error("Recorded video is empty");
}
console.log(`W6_DEMO_VIDEO=${absoluteOutput}`);
console.log(`W6_DEMO_VIDEO_BYTES=${stats.size}`);
