import { expect, test, type Page } from "@playwright/test";

const NVDA_RUN_ID = "w5_demo_nvda_20260630";
const QQQ_RUN_ID = "w5_demo_qqq_20260630";

async function assertNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
}

async function submitDemoTicker(page: Page, ticker: "NVDA" | "QQQ") {
  await page.goto("/research");
  await page.getByLabel("Ticker").fill(ticker);
  await page.getByLabel("Analysis date").fill("2026-06-30");
  for (const analyst of ["Market", "Sentiment", "News", "Fundamentals"]) {
    await expect(page.getByLabel(analyst)).toBeChecked();
  }

  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/research") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Start research" }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const body = (await response.json()) as Record<string, unknown>;
  expect(body.status).toBe("completed");
  expect(body.cache_disposition).toBe("reused_completed");
  return body;
}

test("Research page is backed by the isolated completed cache", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/research$/);
  await expect(page.getByText("API ready")).toBeVisible();
  await expect(page.getByText("Real execution disabled")).toBeVisible();
  await expect(page.getByRole("button", { name: /NVDA.*completed/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /QQQ.*completed/ })).toBeVisible();
  await expect(page.getByText("404")).toHaveCount(0);
});

test("NVDA completed reuse exposes research, graph, conflict, and evidence", async ({ page }) => {
  const submission = await submitDemoTicker(page, "NVDA");
  expect(submission.run_id).toBe(NVDA_RUN_ID);
  await expect(page).toHaveURL(`/runs/${NVDA_RUN_ID}/research`);
  await expect(page.locator('[role="status"][data-status="completed"]')).toContainText(
    "Completed"
  );
  await expect(page.getByRole("heading", { name: "Research summary" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analyst findings" })).toBeVisible();
  await expect(page.locator(".analyst-output-card").first()).toBeVisible();
  await expect(page.locator("body")).not.toContainText("raw_output");
  await expect(page.locator("body")).not.toContainText("API key");
  await expect(page.locator("body")).not.toContainText("provider config");

  await page.getByRole("link", { name: "Structure Graph" }).click();
  await expect(page.getByRole("heading", { name: /Structure graph — NVDA/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dominant alphas" })).toBeVisible();
  await expect(page.getByText("A101", { exact: true }).first()).toBeVisible();
  const valuationNode = page.getByRole("button", { name: /Valuation Risk.*conflict-related/ });
  await valuationNode.focus();
  await valuationNode.press("Enter");
  await expect(valuationNode).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("A304", { exact: true })).toBeVisible();
  await assertNoHorizontalOverflow(page);

  const conflictsResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith(`/api/research/${NVDA_RUN_ID}/conflicts`)
  );
  await page.getByRole("link", { name: "Conflict Radar" }).click();
  const conflictsResponse = await conflictsResponsePromise;
  const conflicts = (await conflictsResponse.json()) as {
    main_conflict: {
      conflict_id: string;
      bull_alpha_id: string;
      bear_alpha_id: string;
    };
  };
  expect(conflicts.main_conflict.conflict_id).toBe("A101__A304");
  expect(conflicts.main_conflict.bull_alpha_id).toBe("A101");
  expect(conflicts.main_conflict.bear_alpha_id).toBe("A304");
  await expect(page.getByRole("heading", { name: "A101 vs A304" }).first()).toBeVisible();
  await expect(page.getByText("Bull side", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Bear side", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence traceability" })).toBeVisible();
  await expect(page.locator(".evidence-list-item").first()).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/guaranteed returns?/i);
});

test("QQQ uses backend arbitration and retains both approved conflicts", async ({ page }) => {
  const submission = await submitDemoTicker(page, "QQQ");
  expect(submission.run_id).toBe(QQQ_RUN_ID);
  await expect(page).toHaveURL(`/runs/${QQQ_RUN_ID}/research`);

  await page.getByRole("link", { name: "Structure Graph" }).click();
  await expect(page.getByRole("heading", { name: /Structure graph — QQQ/ })).toBeVisible();
  await expect(page.getByText("A003", { exact: true }).first()).toBeVisible();

  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith(`/api/research/${QQQ_RUN_ID}/conflicts`)
  );
  await page.getByRole("link", { name: "Conflict Radar" }).click();
  const response = await responsePromise;
  const payload = (await response.json()) as {
    conflicts: Array<{ conflict_id: string; alpha_a: string; alpha_b: string }>;
    main_conflict: { conflict_id: string; alpha_a: string; alpha_b: string };
  };
  expect(payload.conflicts.map((item) => item.conflict_id)).toEqual(
    expect.arrayContaining(["A001__A501", "A003__A501"])
  );
  expect(payload.main_conflict).toEqual(payload.conflicts[0]);
  await expect(
    page.getByRole("heading", {
      name: `${payload.main_conflict.alpha_a} vs ${payload.main_conflict.alpha_b}`,
    }).first()
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "All admitted conflicts" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "A001 vs A501" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "A003 vs A501" }).first()).toBeVisible();
});

test("direct URLs and refresh restore every NVDA run page", async ({ page }) => {
  const cases = [
    [`/runs/${NVDA_RUN_ID}/research`, "Research summary"],
    [`/runs/${NVDA_RUN_ID}/structure`, "Dominant alphas"],
    [`/runs/${NVDA_RUN_ID}/conflicts`, "Evidence traceability"],
  ] as const;

  for (const [url, heading] of cases) {
    await page.goto(url);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
});

test("a live 202 submission shows real processing progress and forwards to results", async ({ page }) => {
  // The demo server keeps real execution disabled, so the live-submission
  // flow is exercised through route interception: a 202 accepted response,
  // a status sequence driven by (mock) backend telemetry, and the terminal
  // completed status. The frontend must render exactly what the backend
  // reports -- it never invents progress of its own.
  const runId = "e2e_live_processing_run";
  let statusCalls = 0;

  await page.route("**/api/research", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        ticker: "MSTR",
        status: "queued",
        run_status: "queued",
        stage: "accepted",
        cache_disposition: "created",
      }),
    });
  });
  await page.route(`**/api/research/${runId}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        ticker: "MSTR",
        status: "completed",
        artifacts: {
          metadata: true,
          raw_agent_outputs: true,
          structured_agent_outputs: true,
          final_report: false,
          alpha_matches: true,
          extracted_structures: true,
          structured_output_error_logs: false,
          week2_llm_error_logs: false,
          week2_pipeline_error_logs: false,
        },
        agent_output_count: 0,
        structured_output_count: 0,
        structure_graph_status: "ready",
        dominant_alphas: [],
        main_conflict: null,
        conflict_status: "ready",
        summary: "No dominant Alpha structure or admitted conflict was identified for this research run.",
      }),
    })
  );
  await page.route(`**/api/research/${runId}/agent-outputs`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        ticker: "MSTR",
        status: "ok",
        schema_version: "week1a.structured_agent_outputs.v2",
        count: 0,
        structured_agent_outputs: [],
      }),
    })
  );
  await page.route(`**/api/research/${runId}/status`, (route) => {
    statusCalls += 1;
    const base = {
      run_id: runId,
      ticker: "MSTR",
      analysis_date: "2026-06-30",
      selected_analysts: ["market", "sentiment", "news", "fundamentals"],
      stage: "research_pipeline",
      error_code: null,
      message: "Research run is in progress.",
      created_at: null,
      started_at: null,
      completed_at: null,
      updated_at: null,
      profile_id: "comqutor_anthropic_medium_sonnet46_v1",
      profile_display_name: "COMQUTOR Anthropic Medium v1",
      completed_units: 4,
      total_units: 15,
      progress_message: "Running the News Analyst.",
      elapsed_seconds: 98,
      eta_status: "estimating",
      estimated_remaining_seconds_min: null,
      estimated_remaining_seconds_max: null,
      eta_sample_count: 0,
    };
    const body =
      statusCalls < 3
        ? { ...base, status: "running", progress_percent: 43, current_stage: "news_analysis" }
        : {
            ...base,
            status: "completed",
            stage: "completed",
            progress_percent: 100,
            current_stage: "completed",
            eta_status: "complete",
            progress_message: "Research run completed.",
          };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  await page.goto("/research");
  await page.getByLabel("Ticker").fill("MSTR");
  await page.getByRole("button", { name: "Start research" }).click();

  await expect(page).toHaveURL(`/runs/${runId}/processing`);
  await expect(page.getByRole("heading", { name: "Analyzing MSTR" })).toBeVisible();
  const bar = page.getByRole("progressbar");
  await expect(bar).toHaveAttribute("aria-valuenow", "43");
  await expect(page.getByText("Research profile: COMQUTOR Anthropic Medium v1")).toBeVisible();
  await expect(page.getByText("Estimating completion time…")).toBeVisible();
  await expect(page.getByText("Current step: Running the News Analyst.")).toBeVisible();
  await assertNoHorizontalOverflow(page);

  // Terminal status arrives via polling -> the page announces completion
  // and forwards to the results automatically.
  await expect(page).toHaveURL(`/runs/${runId}/research`, { timeout: 20_000 });
  await expect(page.getByRole("heading", { name: "Research summary" })).toBeVisible();
});

test("a 404 readiness endpoint is reported as an incompatible API", async ({ page }) => {
  await page.route("**/ready", (route) =>
    route.fulfill({
      status: 404,
      contentType: "text/html",
      body: "<html><body>Not Found</body></html>",
    })
  );
  await page.goto("/research");
  await expect(
    page.getByText("Connected service is not a compatible COMQUTOR API.", { exact: false })
  ).toBeVisible();
  await expect(
    page.getByText("Check VITE_COMQUTOR_API_BASE_URL and restart the frontend.", {
      exact: false,
    })
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText("<html>");
  await expect(page.locator("body")).not.toContainText("unexpected response");
});

test("research, graph, and conflict layouts fit all required viewports", async ({ page }) => {
  const viewports = [
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
    { width: 768, height: 900 },
  ];
  const paths = [
    "/research",
    `/runs/${NVDA_RUN_ID}/structure`,
    `/runs/${NVDA_RUN_ID}/conflicts`,
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    for (const path of paths) {
      await page.goto(path);
      await expect(page.getByRole("main")).toBeVisible();
      await assertNoHorizontalOverflow(page);
      if (path === "/research") {
        await expect(page.getByRole("heading", { name: "Research a ticker" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Start research" })).toBeVisible();
      } else {
        await expect(page.getByRole("navigation", { name: "Research run sections" })).toBeVisible();
      }
      if (path.endsWith("/structure")) {
        await expect(page.getByRole("img", { name: /Structure graph with/ })).toBeVisible();
      }
    }
  }
});
