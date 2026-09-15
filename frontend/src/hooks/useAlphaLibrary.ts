import { useEffect, useState } from "react";
import { getAlphaLibrary } from "../api/client";
import { ApiError } from "../api/errors";
import type { AlphaLibraryResponse } from "../api/types";

export interface UseAlphaLibraryResult {
  library: AlphaLibraryResponse | null;
  isLoading: boolean;
  error: ApiError | null;
}

// The Alpha taxonomy is static and ticker-independent for the lifetime of
// the running server -- one module-level cached fetch is shared by every
// component instance (AlphaCard is rendered many times per page), so
// mounting N AlphaCards never issues N Alpha Library requests. Deliberately
// not per-run, unlike useResearchGraph/useResearchRun.
let cachedPromise: Promise<AlphaLibraryResponse> | null = null;

/** Test-only: clears the module-level cache so each test can control its
 * own getAlphaLibrary mock/call count. Never called from application code
 * -- the whole point of the cache is that it survives across component
 * mounts for the life of the page. */
export function resetAlphaLibraryCacheForTests(): void {
  cachedPromise = null;
}

function fetchAlphaLibraryOnce(): Promise<AlphaLibraryResponse> {
  if (!cachedPromise) {
    cachedPromise = getAlphaLibrary().catch((error: unknown) => {
      // Do not cache a failure -- a transient network error should not
      // permanently prevent every AlphaCard on the page from ever trying
      // again on a later mount (e.g. a fresh page navigation).
      cachedPromise = null;
      throw error;
    });
  }
  return cachedPromise;
}

/**
 * Loads GET /api/alpha-library once and shares the result across every
 * caller. Used to attach each Alpha's taxonomy-defined invalidation
 * conditions to AlphaCard without a per-card, per-Alpha API request.
 */
export function useAlphaLibrary(): UseAlphaLibraryResult {
  const [library, setLibrary] = useState<AlphaLibraryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    fetchAlphaLibraryOnce()
      .then((result) => {
        if (cancelled) return;
        setLibrary(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(cause instanceof ApiError ? cause : ApiError.network());
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { library, isLoading, error };
}
