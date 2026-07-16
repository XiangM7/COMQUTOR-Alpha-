import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const BANNED_PHRASES = [
  "guaranteed return",
  "guaranteed profit",
  "risk-free",
  "sure win",
  "必涨",
  "稳赚",
  "保证收益",
  "零风险",
];

const SRC_ROOT = join(__dirname, "..");

function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist") continue;
    const fullPath = join(dir, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(tsx?|css)$/.test(entry) && !entry.endsWith(".test.ts") && !entry.endsWith(".test.tsx")) {
      files.push(fullPath);
    }
  }
  return files;
}

describe("product language", () => {
  it("never contains a return/profit guarantee in user-visible source text", () => {
    const files = collectSourceFiles(SRC_ROOT);
    const violations: string[] = [];
    for (const file of files) {
      const content = readFileSync(file, "utf-8").toLowerCase();
      for (const phrase of BANNED_PHRASES) {
        if (content.includes(phrase.toLowerCase())) {
          violations.push(`${file}: "${phrase}"`);
        }
      }
    }
    expect(violations).toEqual([]);
  });
});
