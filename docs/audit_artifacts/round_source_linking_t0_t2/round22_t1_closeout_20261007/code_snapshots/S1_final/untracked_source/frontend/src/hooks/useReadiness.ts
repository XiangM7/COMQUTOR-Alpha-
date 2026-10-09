import { createContext, useContext, useEffect, useState } from "react";
import { getReadiness } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { ReadinessResponse } from "../api/types";

export interface ReadinessState {
  readiness: ReadinessResponse | null;
  errorMessage: string | null;
}

/** Without a provider the state is simply "not checked yet" -- nothing is
 * ever blocked on a readiness result that was never requested. */
export const ReadinessContext = createContext<ReadinessState>({ readiness: null, errorMessage: null });

/** Current server readiness, shared by the navigation bar's status and the
 * Research page's submit guard so /ready is requested once per page load. */
export function useReadiness(): ReadinessState {
  return useContext(ReadinessContext);
}

/** Fetches /ready once. Used by ReadinessProvider only. */
export function useReadinessLoader(): ReadinessState {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getReadiness({ signal: controller.signal })
      .then(({ result }) => {
        if (!controller.signal.aborted) setReadiness(result);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (!apiError.isAborted) setErrorMessage(describeApiError(apiError));
      });
    return () => controller.abort();
  }, []);

  return { readiness, errorMessage };
}
