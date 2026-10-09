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

describe("Analyst findings card layout (styles.css)", () => {
  // Product Demo Hardening Phase 3B (F1): a claim_id like
  // "<run_id>:<agent>:<source>:claim:<n>" is a long, colon-delimited,
  // space-free string that never finds a natural break opportunity under
  // default word-break rules, and at a narrow viewport (confirmed at
  // 768px) pushed the whole page into horizontal overflow. Scoped to the
  // finding-card family only -- never the global `code` element -- so
  // unrelated short `code` text (Alpha IDs, ticker symbols) is unaffected.
  it("finding cards allow a long claim_id to wrap instead of overflowing the page", () => {
    expect(ruleBody(".analyst-output-card")).toMatch(/overflow-wrap:\s*anywhere/);
  });

  it("unclassified finding cards already had -- and still have -- the same protection", () => {
    expect(ruleBody(".unclassified-finding-card")).toMatch(/overflow-wrap:\s*anywhere/);
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

describe("Research landing page (styles.css)", () => {
  it("navigation is sticky and translucent over the scrolling page", () => {
    const body = ruleBody(".app-header");
    expect(body).toMatch(/position:\s*sticky/);
    expect(body).toMatch(/top:\s*0/);
    expect(body).toMatch(/backdrop-filter:\s*saturate\(180%\)\s*blur\(20px\)/);
  });

  it("the Recent runs menu floats over the page instead of pushing content down", () => {
    const body = ruleBody(".recent-runs-menu");
    expect(body).toMatch(/position:\s*absolute/);
    expect(body).toMatch(/z-index:\s*5/);
    expect(ruleBody(".research-actions")).toMatch(/position:\s*relative/);
  });

  it("a long run history scrolls inside the menu instead of growing it", () => {
    const body = ruleBody(".recent-runs-scroll");
    expect(body).toMatch(/max-height:\s*336px/);
    expect(body).toMatch(/overflow-y:\s*auto/);
  });

  it("the ticker input is large, bold and shown in capitals", () => {
    const body = ruleBody(".ticker-input");
    expect(body).toMatch(/font-size:\s*32px/);
    expect(body).toMatch(/text-transform:\s*uppercase/);
  });

  it("the only autoplay motion (evidence trace) and the menu respect prefers-reduced-motion", () => {
    const block = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.trace-node,[\s\S]*?\n\}/)?.[0];
    if (block == null) {
      throw new Error("no prefers-reduced-motion block covers .trace-node");
    }
    expect(block).toMatch(/\.recent-runs-menu/);
    expect(block).toMatch(/\.trace-link/);
    expect(block).toMatch(/animation:\s*none/);
  });

  it("trace connectors are hidden on narrow screens", () => {
    const block = [...css.matchAll(/@media \(max-width: 720px\)\s*\{[\s\S]*?\n\}/g)]
      .map((match) => match[0])
      .find((candidate) => candidate.includes(".trace-link"));
    if (block == null) {
      throw new Error("no @media (max-width: 720px) block for the landing page");
    }
    expect(block).toMatch(/\.trace-link\s*\{\s*display:\s*none/);
  });
});

describe("Processing page (styles.css)", () => {
  it("lays out two columns that wrap on narrow screens, the stages panel capped at 280px", () => {
    expect(ruleBody(".processing-layout")).toMatch(/flex-wrap:\s*wrap/);
    expect(ruleBody(".processing-main")).toMatch(/min-width:\s*0/);
    const panel = ruleBody(".stages-panel");
    expect(panel).toMatch(/max-width:\s*280px/);
    expect(panel).toMatch(/min-width:\s*0/);
  });

  it("gives the pipeline scene one fixed height so the page never jumps between scenes", () => {
    expect(ruleBody(".pipeline-stage")).toMatch(/height:\s*168px/);
    // The card is sized by that stage, not by its own minimum.
    expect(ruleBody(".pipeline-card")).not.toMatch(/min-height/);
  });

  it("animates the progress width smoothly while the band only marks the active stretch", () => {
    expect(ruleBody(".progress-fill")).toMatch(/transition:\s*width/);
    expect(ruleBody(".progress-band")).toMatch(/animation:\s*band-shimmer/);
  });

  it("lets the ticker be transformed, so it can fly in from the Research page", () => {
    expect(ruleBody(".processing-ticker")).toMatch(/display:\s*inline-block/);
  });

  it("keeps the Start button blue while a run is being started", () => {
    const body = ruleBody(".cta-button-busy:disabled");
    expect(body).toMatch(/background:\s*var\(--color-primary\)/);
    expect(body).not.toMatch(/not-allowed/);
  });

  it("never plays the entrance animation on the ticker or the progress track", () => {
    const rule = css.match(/\.processing-enter \.rise-1,[^{]*\{([^}]*)\}/);
    if (rule == null) {
      throw new Error("entrance animation rule not found");
    }
    expect(rule[0]).not.toMatch(/\.processing-ticker|\.progress-track|\.progress-fill/);
    expect(rule[1]).toMatch(/animation:\s*rise/);
  });

  it("grows the sheet out of the card from its top-left corner", () => {
    const sheet = ruleBody(".price-sheet");
    expect(sheet).toMatch(/transform-origin:\s*0 0/);
    expect(sheet).toMatch(/position:\s*fixed/);
    expect(ruleBody(".price-sheet-backdrop")).toMatch(/backdrop-filter:\s*blur\(14px\)/);
  });

  it("turns off the band, the pulses and the entrance when reduced motion is requested", () => {
    const block = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.processing-enter[\s\S]*?\n\}/)?.[0];
    if (block == null) {
      throw new Error("no prefers-reduced-motion block for the Processing page");
    }
    for (const selector of [".progress-band", ".scene-dot-pulse", ".scene-dot-offbeat", ".stage-dot-current", ".processing-enter .rise-3"]) {
      expect(block).toContain(selector);
    }
    expect(block).toMatch(/animation:\s*none/);
  });
});
