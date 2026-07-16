import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/errors";
import type { ResearchRunRecord } from "../api/types";
import { useRunPolling } from "./useRunPolling";

function statusRecord(
  status: ResearchRunRecord["status"],
  overrides: Partial<ResearchRunRecord> = {}
): ResearchRunRecord {
  return {
    run_id: "run-1",
    ticker: "NVDA",
    analysis_date: null,
    selected_analysts: [],
    status,
    stage: null,
    error_code: null,
    message: "",
    created_at: null,
    started_at: null,
    completed_at: null,
    updated_at: null,
    ...overrides,
  };
}

/** Flushes pending microtasks (a mocked promise's resolution plus its
 * `.then()` continuation) without relying on real or fake timers. */
async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useRunPolling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("polls queued -> running -> completed and then stops", async () => {
    vi.useFakeTimers();
    const spy = vi
      .spyOn(client, "getResearchRunStatus")
      .mockResolvedValueOnce(statusRecord("queued"))
      .mockResolvedValueOnce(statusRecord("running"))
      .mockResolvedValueOnce(statusRecord("completed"));

    const { result } = renderHook(() => useRunPolling("run-1"));

    await flushMicrotasks();
    expect(result.current.status?.status).toBe("queued");
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.status?.status).toBe("running");
    expect(spy).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.status?.status).toBe("completed");
    expect(spy).toHaveBeenCalledTimes(3);
    expect(result.current.isPolling).toBe(false);

    // No further polling after terminal.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it("stops polling once a run reaches failed", async () => {
    vi.useFakeTimers();
    const spy = vi
      .spyOn(client, "getResearchRunStatus")
      .mockResolvedValueOnce(statusRecord("queued"))
      .mockResolvedValueOnce({
        run_id: "run-1",
        status: "failed",
        error_code: "INTERNAL_ERROR",
        message: "boom",
      });

    const { result } = renderHook(() => useRunPolling("run-1"));
    await flushMicrotasks();
    expect(result.current.status?.status).toBe("queued");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.status?.status).toBe("failed");
    expect(result.current.isPolling).toBe(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("stops polling once a run reaches partial (also terminal)", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(statusRecord("partial"));

    const { result } = renderHook(() => useRunPolling("run-1"));
    await waitFor(() => expect(result.current.status?.status).toBe("partial"));
    expect(result.current.isPolling).toBe(false);
  });

  it("cancels the in-flight request and timer on unmount", async () => {
    const abortSpy = vi.fn();
    vi.spyOn(client, "getResearchRunStatus").mockImplementation((_runId, options) => {
      options?.signal?.addEventListener("abort", abortSpy);
      return new Promise(() => {
        // never resolves -- simulates an in-flight request at unmount time
      });
    });

    const { unmount } = renderHook(() => useRunPolling("run-1"));
    await flushMicrotasks();
    unmount();
    expect(abortSpy).toHaveBeenCalled();
  });

  it("cancels the previous run_id's polling loop when run_id changes", async () => {
    const spy = vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(statusRecord("queued"));

    const { rerender } = renderHook(({ runId }) => useRunPolling(runId), {
      initialProps: { runId: "run-1" },
    });
    await waitFor(() => expect(spy).toHaveBeenCalledWith("run-1", expect.anything()));

    rerender({ runId: "run-2" });
    await waitFor(() => expect(spy).toHaveBeenCalledWith("run-2", expect.anything()));
  });

  it("never creates more than one active timer (advancing time triggers exactly one fetch per tick)", async () => {
    vi.useFakeTimers();
    const spy = vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(statusRecord("queued"));

    renderHook(() => useRunPolling("run-1"));
    await flushMicrotasks();
    expect(spy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("retries on network failure without marking the run failed, and exposes a retryable error", async () => {
    vi.useFakeTimers();
    const spy = vi
      .spyOn(client, "getResearchRunStatus")
      .mockRejectedValueOnce(ApiError.network())
      .mockResolvedValueOnce(statusRecord("running"));

    const { result } = renderHook(() => useRunPolling("run-1"));
    await flushMicrotasks();
    expect(result.current.error).not.toBeNull();
    expect(result.current.status).toBeNull(); // never synthesized a "failed" status

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.status?.status).toBe("running");
    expect(result.current.error).toBeNull();
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("manual refresh triggers an immediate re-fetch", async () => {
    const spy = vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(statusRecord("queued"));

    const { result } = renderHook(() => useRunPolling("run-1"));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));

    act(() => {
      result.current.refresh();
    });
    await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThan(1));
  });
});
