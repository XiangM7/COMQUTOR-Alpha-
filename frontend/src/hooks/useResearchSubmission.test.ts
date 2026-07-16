import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/errors";
import { useResearchSubmission } from "./useResearchSubmission";

describe("useResearchSubmission", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits and returns the HTTP status + result on success", async () => {
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 202,
      result: { run_id: "run-1", ticker: "NVDA", status: "queued", cache_disposition: "created" },
    });

    const { result } = renderHook(() => useResearchSubmission());
    let outcome;
    await act(async () => {
      outcome = await result.current.submit({ ticker: "NVDA" });
    });

    expect(outcome).toEqual({
      httpStatus: 202,
      result: { run_id: "run-1", ticker: "NVDA", status: "queued", cache_disposition: "created" },
    });
    expect(result.current.errorMessage).toBeNull();
  });

  it("surfaces a safe error message on failure and never a raw exception", async () => {
    vi.spyOn(client, "submitResearch").mockRejectedValue(ApiError.network());

    const { result } = renderHook(() => useResearchSubmission());
    await act(async () => {
      await result.current.submit({ ticker: "NVDA" });
    });

    expect(result.current.errorMessage).toMatch(/could not reach/i);
  });

  it("prevents a second concurrent submission while one is in flight", async () => {
    let resolveFirst: (() => void) | undefined;
    const submitSpy = vi.spyOn(client, "submitResearch").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = () =>
            resolve({ status: 202, result: { run_id: "run-1", ticker: "NVDA", status: "queued" } });
        })
    );

    const { result } = renderHook(() => useResearchSubmission());

    let firstPromise: Promise<unknown> | undefined;
    let secondOutcome: unknown;
    act(() => {
      firstPromise = result.current.submit({ ticker: "NVDA" });
    });
    await act(async () => {
      secondOutcome = await result.current.submit({ ticker: "NVDA" });
    });

    expect(secondOutcome).toBeNull(); // second call is ignored while first is in flight
    expect(submitSpy).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst?.();
      await firstPromise;
    });
  });
});
