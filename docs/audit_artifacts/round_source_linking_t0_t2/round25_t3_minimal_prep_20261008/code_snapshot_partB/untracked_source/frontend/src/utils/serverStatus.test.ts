import { describe, expect, it } from "vitest";
import type { ReadinessResponse } from "../api/types";
import { describeServerStatus } from "./serverStatus";

function readiness(overrides: Partial<ReadinessResponse> = {}): ReadinessResponse {
  return {
    status: "ready",
    database: "ready",
    job_manager: "ready",
    real_execution: "configured",
    live_semantic_pipeline: "ready",
    ...overrides,
  };
}

describe("describeServerStatus", () => {
  it("says it is checking before the first answer", () => {
    expect(describeServerStatus(null, null)).toEqual({ tone: "neutral", label: "Checking server status…" });
  });

  it("reports an unreachable or incompatible server as a warning", () => {
    expect(describeServerStatus(null, "Could not reach the COMQUTOR API.")).toEqual({
      tone: "warn",
      label: "Server status unavailable",
    });
  });

  it("reports a ready server with live research configured", () => {
    expect(describeServerStatus(readiness(), null)).toEqual({
      tone: "ok",
      label: "Server ready, live research configured",
    });
  });

  it("reports a ready server with live research disabled", () => {
    expect(describeServerStatus(readiness({ real_execution: "disabled", live_semantic_pipeline: "not_applicable" }), null)).toEqual({
      tone: "ok",
      label: "Server ready, live research disabled",
    });
  });

  it("warns about misconfigured live research", () => {
    expect(describeServerStatus(readiness({ real_execution: "misconfigured" }), null)).toEqual({
      tone: "warn",
      label: "Server ready, live research misconfigured",
    });
  });

  it("warns when the live semantic pipeline is not ready", () => {
    expect(describeServerStatus(readiness({ live_semantic_pipeline: "not_ready" }), null)).toEqual({
      tone: "warn",
      label: "Server ready, live semantic pipeline not ready",
    });
  });

  it("reports a server that is not ready", () => {
    expect(describeServerStatus(readiness({ status: "not_ready" }), null)).toEqual({
      tone: "warn",
      label: "Server not ready",
    });
  });
});
