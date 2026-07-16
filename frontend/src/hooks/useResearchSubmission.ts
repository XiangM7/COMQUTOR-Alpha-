import { useCallback, useRef, useState } from "react";
import { submitResearch } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { ResearchSubmissionRequest, ResearchSubmissionResult } from "../api/types";

export interface SubmissionOutcome {
  httpStatus: number;
  result: ResearchSubmissionResult;
}

export interface UseResearchSubmissionResult {
  isSubmitting: boolean;
  errorMessage: string | null;
  submit: (request: ResearchSubmissionRequest) => Promise<SubmissionOutcome | null>;
  reset: () => void;
}

/**
 * Wraps POST /api/research. Never sends provider/model/config/API key/
 * allow_real_tradingagents_run/offline_raw_agent_outputs -- the request
 * shape is exactly ResearchSubmissionRequest, constructed by the caller
 * (ResearchForm) from user input only.
 *
 * Disables re-submission while a request is in flight (guards against a
 * double-click creating two claims); the caller decides what to do with a
 * successful outcome (HTTP 200 vs 202 vs an error) -- this hook only
 * performs the request and surfaces a safe error message on failure.
 */
export function useResearchSubmission(): UseResearchSubmissionResult {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const submittingRef = useRef(false);

  const submit = useCallback(
    async (request: ResearchSubmissionRequest): Promise<SubmissionOutcome | null> => {
      if (submittingRef.current) return null;
      submittingRef.current = true;
      setIsSubmitting(true);
      setErrorMessage(null);
      try {
        const { status, result } = await submitResearch(request);
        return { httpStatus: status, result };
      } catch (cause) {
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        setErrorMessage(describeApiError(apiError));
        return null;
      } finally {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    },
    []
  );

  const reset = useCallback(() => {
    setErrorMessage(null);
  }, []);

  return { isSubmitting, errorMessage, submit, reset };
}
