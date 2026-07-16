import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getApiBaseUrl,
  getReadiness,
  getResearchHistory,
  getResearchRunStatus,
  submitResearch,
} from "./client";
import { ApiError, describeApiError } from "./errors";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function htmlResponse(status = 500): Response {
  return new Response("<html><body>Internal Server Error</body></html>", {
    status,
    headers: { "content-type": "text/html" },
  });
}

describe("api client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.stubEnv("VITE_COMQUTOR_API_BASE_URL", "");
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.unstubAllEnvs();
  });

  it("uses an empty base URL when VITE_COMQUTOR_API_BASE_URL is unset (same-origin)", () => {
    expect(getApiBaseUrl()).toBe("");
  });

  it("submitResearch returns HTTP 202 with queued status", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          run_id: "run-123",
          ticker: "NVDA",
          status: "queued",
          run_status: "queued",
          stage: "accepted",
          cache_disposition: "created",
        },
        202
      )
    );

    const { status, result } = await submitResearch({ ticker: "NVDA" });
    expect(status).toBe(202);
    expect(result.run_id).toBe("run-123");
    expect(result.cache_disposition).toBe("created");
  });

  it("submitResearch returns HTTP 200 for a completed-run reuse", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          run_id: "run-456",
          ticker: "NVDA",
          status: "completed",
          run_status: "completed",
          cache_disposition: "reused_completed",
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
          summary: "No dominant Alpha structure or admitted conflict was identified for this research run.",
        },
        200
      )
    );

    const { status, result } = await submitResearch({ ticker: "NVDA" });
    expect(status).toBe(200);
    expect(result.cache_disposition).toBe("reused_completed");
  });

  it("submitResearch surfaces a stable error_code from an HTTP error response", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          run_id: null,
          ticker: "NVDA",
          status: "failed",
          error_code: "REAL_RUN_DISABLED",
          message: "Real TradingAgents execution is disabled by default.",
          run_status: "failed",
        },
        503
      )
    );

    const { status, result } = await submitResearch({ ticker: "NVDA" });
    expect(status).toBe(503);
    expect(result.error_code).toBe("REAL_RUN_DISABLED");
  });

  it("getResearchRunStatus rejects a non-JSON (HTML) response with a safe ApiError, never the raw body", async () => {
    global.fetch = vi.fn().mockResolvedValue(htmlResponse(500));

    await expect(getResearchRunStatus("run-1")).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
    });
  });

  it("getResearchRunStatus rejects an aborted request as ApiError with kind 'aborted'", async () => {
    global.fetch = vi.fn().mockImplementation(() => {
      const abortError = new DOMException("aborted", "AbortError");
      return Promise.reject(abortError);
    });

    const controller = new AbortController();
    controller.abort();
    try {
      await getResearchRunStatus("run-1", { signal: controller.signal });
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).isAborted).toBe(true);
    }
  });

  it("getResearchRunStatus rejects a network failure as ApiError with kind 'network'", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    try {
      await getResearchRunStatus("run-1");
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).isNetwork).toBe(true);
    }
  });

  it("getResearchRunStatus rejects a structurally invalid response body (adapter rejection)", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ not_a_valid_shape: true }, 200));

    await expect(getResearchRunStatus("run-1")).rejects.toMatchObject({
      name: "ApiError",
      kind: "api_contract_mismatch",
    });
  });

  it("classifies a 404 readiness endpoint as an incompatible COMQUTOR API", async () => {
    global.fetch = vi.fn().mockResolvedValue(htmlResponse(404));

    await expect(getReadiness()).rejects.toMatchObject({
      name: "ApiError",
      kind: "api_contract_mismatch",
    });
  });

  it("classifies a 404 research history endpoint as an incompatible COMQUTOR API", async () => {
    global.fetch = vi.fn().mockResolvedValue(htmlResponse(404));

    try {
      await getResearchHistory();
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).kind).toBe("api_contract_mismatch");
      expect(describeApiError(error as ApiError)).toBe(
        "Connected service is not a compatible COMQUTOR API.\n" +
          "Check VITE_COMQUTOR_API_BASE_URL and restart the frontend."
      );
    }
  });

  it("getResearchRunStatus returns a validated ResearchRunRecord for a well-formed response", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({
        run_id: "run-1",
        ticker: "NVDA",
        analysis_date: "2026-06-30",
        selected_analysts: ["market", "news"],
        status: "completed",
        stage: "completed",
        error_code: null,
        message: "Research run completed.",
        created_at: "2026-06-30T00:00:00Z",
        started_at: "2026-06-30T00:00:01Z",
        completed_at: "2026-06-30T00:01:00Z",
        updated_at: "2026-06-30T00:01:00Z",
      })
    );

    const result = await getResearchRunStatus("run-1");
    expect(result).toMatchObject({ run_id: "run-1", status: "completed" });
  });
});
