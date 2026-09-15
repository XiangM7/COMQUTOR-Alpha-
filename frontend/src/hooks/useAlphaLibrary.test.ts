import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/errors";
import type { AlphaLibraryResponse } from "../api/types";
import { resetAlphaLibraryCacheForTests, useAlphaLibrary } from "./useAlphaLibrary";

function libraryResponse(overrides: Partial<AlphaLibraryResponse> = {}): AlphaLibraryResponse {
  return {
    schema_version: "week1.alpha_library.v1",
    alpha_count: 1,
    alphas: [
      {
        alpha_id: "A101",
        name_en: "AI Expansion",
        name_cn: "AI 扩张",
        layer: "Theme",
        status: "active",
        core_thesis: "AI infrastructure demand drives growth.",
        keywords: [],
        trigger_signals: [],
        confirmation_signals: [],
        beneficiary_assets: [],
        risk_assets: [],
        conflict_alphas: [],
        invalidation_conditions: ["AI capex cuts"],
        agent_sources: [],
      },
    ],
    ...overrides,
  };
}

describe("useAlphaLibrary", () => {
  beforeEach(() => {
    resetAlphaLibraryCacheForTests();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the Alpha Library and exposes it once resolved", async () => {
    vi.spyOn(client, "getAlphaLibrary").mockResolvedValue(libraryResponse());

    const { result } = renderHook(() => useAlphaLibrary());
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.library?.alphas[0]?.alpha_id).toBe("A101");
    expect(result.current.error).toBeNull();
  });

  // John Follow-Up Requirement A, section 18 item 5: mounting many
  // AlphaCard-equivalent consumers (e.g. one per Alpha on the Structure
  // Graph page) must never issue one Alpha-Library request per consumer.
  it("issues exactly one network request no matter how many components use the hook at once", async () => {
    const spy = vi.spyOn(client, "getAlphaLibrary").mockResolvedValue(libraryResponse());

    const hooks = [
      renderHook(() => useAlphaLibrary()),
      renderHook(() => useAlphaLibrary()),
      renderHook(() => useAlphaLibrary()),
      renderHook(() => useAlphaLibrary()),
      renderHook(() => useAlphaLibrary()),
    ];

    await waitFor(() => hooks.forEach(({ result }) => expect(result.current.isLoading).toBe(false)));

    expect(spy).toHaveBeenCalledTimes(1);
    hooks.forEach(({ result }) => {
      expect(result.current.library?.alphas[0]?.alpha_id).toBe("A101");
    });
  });

  it("surfaces a network error without caching the failure permanently", async () => {
    const spy = vi
      .spyOn(client, "getAlphaLibrary")
      .mockRejectedValueOnce(ApiError.network())
      .mockResolvedValueOnce(libraryResponse());

    const { result, unmount } = renderHook(() => useAlphaLibrary());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).not.toBeNull();
    expect(result.current.library).toBeNull();
    unmount();

    // A later mount (e.g. a fresh page navigation) gets a real retry, not a
    // permanently poisoned cache entry.
    const second = renderHook(() => useAlphaLibrary());
    await waitFor(() => expect(second.result.current.isLoading).toBe(false));
    expect(second.result.current.library?.alphas[0]?.alpha_id).toBe("A101");
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
