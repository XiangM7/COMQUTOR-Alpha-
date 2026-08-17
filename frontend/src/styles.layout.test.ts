import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// vitest.config's `test.css: false` means jsdom never applies this
// stylesheet, so `getComputedStyle` cannot verify real layout here. These
// tests instead lock the actual CSS rule text -- a regression test for
// docs/audit_artifacts/live_run_5ffe121a_pipeline_failure_report.md's
// Alpha-card layout bug (narrow auto-fill columns, phantom empty tracks,
// four-column Candidate overlap, text overflowing the card border).
const css = readFileSync(path.resolve(process.cwd(), "src/styles.css"), "utf-8");

function ruleBody(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  const body = match?.[1];
  if (body == null) {
    throw new Error(`CSS rule not found: ${selector}`);
  }
  return body;
}

describe("Alpha card grid layout (styles.css)", () => {
  it("desktop grid is a fixed two-column layout, never auto-fill", () => {
    const body = ruleBody(".alpha-card-grid");
    expect(body).toMatch(/grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
    // The historical bug: auto-fill reserves phantom empty tracks with a
    // fixed px floor, leaving a lone card narrow and the row's right side
    // blank. Never allowed to come back.
    expect(body).not.toMatch(/auto-fill/);
    expect(body).not.toMatch(/auto-fit/);
  });

  it("narrow screens collapse the grid to one column", () => {
    const allNarrowBlocks = [...css.matchAll(/@media \(max-width:\s*640px\)\s*\{([\s\S]*?)\}\s*\n(?=\n|$)/g)].map(
      (m) => m[0]
    );
    const gridNarrowBlock = allNarrowBlocks.find((block) => block.includes(".alpha-card-grid"));
    if (gridNarrowBlock == null) {
      throw new Error("no @media (max-width: 640px) block overrides .alpha-card-grid");
    }
    expect(gridNarrowBlock).toMatch(/grid-template-columns:\s*1fr/);
  });

  it("cards and rows can shrink below their content's intrinsic width (min-width: 0)", () => {
    expect(ruleBody(".alpha-card")).toMatch(/min-width:\s*0/);
    expect(ruleBody(".alpha-card-row")).toMatch(/min-width:\s*0/);
  });

  it("long values wrap instead of overflowing the card border", () => {
    const rowDd = ruleBody(".alpha-card-row dd");
    expect(rowDd).toMatch(/overflow-wrap:\s*anywhere/);
    expect(rowDd).toMatch(/word-break:\s*break-word/);
    expect(ruleBody(".alpha-card-diagnostic-reasons li")).toMatch(/overflow-wrap:\s*anywhere/);
  });

  it("blocked/warning/detail rows and related-conflict lists take the full card width", () => {
    const selectorGroup =
      ".alpha-card-row-detail dd,\n.alpha-card-row-warning dd,\n.alpha-card-row-blocked dd,\n.alpha-card-related-conflicts";
    const body = ruleBody(selectorGroup);
    expect(body).toMatch(/width:\s*100%/);
  });
});

describe("Conflict card evidence UI layout (styles.css)", () => {
  it("Bull|Bear and Counter|Missing rows are two columns on desktop", () => {
    const body = ruleBody(".evidence-ui-row");
    expect(body).toMatch(/grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  });

  it("evidence UI rows collapse to one column on narrow screens", () => {
    const allNarrowBlocks = [...css.matchAll(/@media \(max-width:\s*640px\)\s*\{([\s\S]*?)\}\s*\n(?=\n|$)/g)].map(
      (m) => m[0]
    );
    const rowNarrowBlock = allNarrowBlocks.find((block) => block.includes(".evidence-ui-row"));
    if (rowNarrowBlock == null) {
      throw new Error("no @media (max-width: 640px) block overrides .evidence-ui-row");
    }
    expect(rowNarrowBlock).toMatch(/grid-template-columns:\s*1fr/);
  });

  it("evidence items shrink safely and wrap long text", () => {
    expect(ruleBody(".evidence-ui-item")).toMatch(/overflow-wrap:\s*anywhere/);
  });
});
