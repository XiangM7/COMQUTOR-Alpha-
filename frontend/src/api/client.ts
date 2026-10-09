/**
 * Thin fetch() wrapper for the COMQUTOR Alpha API. Every function here:
 *  - resolves the base URL once, from VITE_COMQUTOR_API_BASE_URL (empty ->
 *    same-origin);
 *  - sets Accept: application/json (and Content-Type: application/json for
 *    POST);
 *  - accepts an optional AbortSignal;
 *  - never throws a raw fetch/parsing exception -- everything is mapped to
 *    ApiError;
 *  - hands the parsed JSON to the matching adapter in adapters.ts before
 *    returning it, so nothing downstream ever needs to trust an
 *    unvalidated shape.
 *
 * Never reads an API key, never sends provider/model/config fields, never
 * logs a full response body to the console.
 */

import {
  adaptAgentOutputsResponse,
  adaptAlphaLibraryResponse,
  adaptCanonicalResearchResponse,
  adaptConflictsResponse,
  adaptHealthResponse,
  adaptReadinessResponse,
  adaptReplayAllResult,
  adaptResearchSubmissionResult,
  adaptRunHistoryResponse,
  adaptRunStatusResult,
  adaptStructureGraphResponse,
  looksLikeErrorEnvelope,
  type AdaptResult,
} from "./adapters";
import { ApiError } from "./errors";
import {
  adaptEvidenceTraceItemResponse,
  adaptKeyConclusionsResponse,
  type EvidenceTraceItemResult,
  type KeyConclusionsResult,
} from "./evidenceTrace";
import type {
  AgentOutputsResult,
  AlphaLibraryResponse,
  CanonicalResearchResult,
  ConflictsResult,
  ContentSupportReviewLogResult,
  ContentSupportReviewSubmissionOutcome,
  ContentSupportReviewVerdict,
  HealthResponse,
  ReadinessResponse,
  ReevaluationExecutionsResult,
  ReplayAllResult,
  ResearchSubmissionRequest,
  ResearchSubmissionResult,
  RunHistoryResult,
  RunStatusResult,
  StructureGraphResult,
} from "./types";

/** Empty string (same-origin) when unset -- never a hardcoded production
 * domain, never read from anywhere other than this one build-time env var. */
export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_COMQUTOR_API_BASE_URL;
  return typeof raw === "string" ? raw.trim() : "";
}

function buildUrl(path: string, query?: Record<string, string | number | boolean | undefined>): string {
  const base = getApiBaseUrl();
  const url = new URL(path, base || window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  // When base is empty we want a origin-relative string (same-origin fetch
  // works fine with an absolute URL too, but keeping it relative avoids
  // subtly depending on window.location during tests).
  return base ? url.toString() : url.pathname + url.search;
}

interface RequestOptions {
  signal?: AbortSignal;
}

async function performRequest(
  path: string,
  init: RequestInit,
  query?: Record<string, string | number | boolean | undefined>
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw ApiError.aborted();
    }
    throw ApiError.network();
  }

  const contentType = response.headers.get("content-type") ?? "";
  let body: unknown = null;
  if (contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      throw ApiError.invalidResponse("The server's response could not be parsed.");
    }
  } else {
    // Never surface a raw HTML error page (or any other non-JSON body) to
    // the UI -- only the HTTP status is preserved.
    try {
      await response.text();
    } catch {
      // ignore -- we only needed to drain the body
    }
  }

  if (!response.ok) {
    if (response.status === 404 && path === "/api/research" && (init.method ?? "GET") === "GET") {
      throw ApiError.contractMismatch();
    }
    if (looksLikeErrorEnvelope(body)) {
      throw ApiError.http(
        response.status,
        body.error_code ?? null,
        body.message ?? `Request failed with status ${response.status}.`
      );
    }
    throw ApiError.http(response.status, null, `Request failed with status ${response.status}.`);
  }

  if (body === null) {
    throw ApiError.contractMismatch();
  }

  return body;
}

function adaptOrThrow<T>(adapted: AdaptResult<T>): T {
  if (!adapted.ok) {
    throw ApiError.contractMismatch();
  }
  return adapted.value;
}

export async function submitResearch(
  request: ResearchSubmissionRequest,
  options: RequestOptions = {}
): Promise<{ status: number; result: ResearchSubmissionResult }> {
  let response: Response;
  try {
    response = await fetch(buildUrl("/api/research"), {
      method: "POST",
      signal: options.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw ApiError.aborted();
    }
    throw ApiError.network();
  }

  let body: unknown;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch {
      throw ApiError.invalidResponse("The server's response could not be parsed.");
    }
  } else {
    throw ApiError.invalidResponse("The server did not return a JSON response.");
  }

  const adapted = adaptResearchSubmissionResult(body);
  const result = adaptOrThrow(adapted);
  return { status: response.status, result };
}

export async function getResearchRun(
  runId: string,
  options: RequestOptions = {}
): Promise<CanonicalResearchResult> {
  const body = await performRequest(`/api/research/${encodeURIComponent(runId)}`, { signal: options.signal });
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptCanonicalResearchResponse(body));
}

export async function getResearchRunStatus(
  runId: string,
  options: RequestOptions = {}
): Promise<RunStatusResult> {
  const body = await performRequest(`/api/research/${encodeURIComponent(runId)}/status`, {
    signal: options.signal,
  });
  return adaptOrThrow(adaptRunStatusResult(body));
}

export async function getResearchGraph(
  runId: string,
  options: RequestOptions = {}
): Promise<StructureGraphResult> {
  const body = await performRequest(`/api/research/${encodeURIComponent(runId)}/graph`, {
    signal: options.signal,
  });
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptStructureGraphResponse(body));
}

export async function getResearchConflicts(
  runId: string,
  options: RequestOptions = {}
): Promise<ConflictsResult> {
  const body = await performRequest(`/api/research/${encodeURIComponent(runId)}/conflicts`, {
    signal: options.signal,
  });
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptConflictsResponse(body));
}

export async function getAgentOutputs(
  runId: string,
  options: RequestOptions = {}
): Promise<AgentOutputsResult> {
  const body = await performRequest(`/api/research/${encodeURIComponent(runId)}/agent-outputs`, {
    signal: options.signal,
  });
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptAgentOutputsResponse(body));
}

/** GET /api/research/{run_id}/evidence-trace?claim_id= -- one claim's source material, location, verification and
 * scoring as four separate statuses (T1 closure). Read-only; built server-side from the run's own saved artifacts. */
export async function getEvidenceTrace(
  runId: string,
  claimId: string,
  options: RequestOptions = {}
): Promise<EvidenceTraceItemResult> {
  const body = await performRequest(
    `/api/research/${encodeURIComponent(runId)}/evidence-trace`,
    { signal: options.signal },
    { claim_id: claimId }
  );
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptEvidenceTraceItemResponse(body));
}

/** GET /api/research/{run_id}/evidence-trace?scope=key -- the final-decision claims with their four statuses. */
export async function getKeyConclusions(
  runId: string,
  options: RequestOptions = {}
): Promise<KeyConclusionsResult> {
  const body = await performRequest(
    `/api/research/${encodeURIComponent(runId)}/evidence-trace`,
    { signal: options.signal },
    { scope: "key" }
  );
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptKeyConclusionsResponse(body));
}

/** POST /api/research/{run_id}/claims/{claim_id}/review -- minimal human
 * content-support review entrypoint (T1 verified-support eligibility gate,
 * 2026-09-28). Never fabricates a review: the server itself refuses an
 * empty reviewer/rationale (400 REVIEWER_REQUIRED/RATIONALE_REQUIRED) --
 * this function surfaces that failure body as-is rather than throwing, so
 * the caller can render it inline next to the form instead of a generic
 * error boundary. History protection: this NEVER mutates the original
 * run's own data -- it appends an independent review record and (by
 * default) triggers a NEW execution_id; see the response's own
 * `reevaluation` field. */
export async function submitContentSupportReview(
  runId: string,
  claimId: string,
  request: { status: ContentSupportReviewVerdict; reviewer: string; rationale: string; trigger_reevaluation?: boolean },
  options: RequestOptions = {}
): Promise<ContentSupportReviewSubmissionOutcome> {
  const body = await performRequest(
    `/api/research/${encodeURIComponent(runId)}/claims/${encodeURIComponent(claimId)}/review`,
    {
      method: "POST",
      signal: options.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  );
  if (!body || typeof body !== "object" || !("status" in body)) {
    throw ApiError.contractMismatch();
  }
  return body as ContentSupportReviewSubmissionOutcome;
}

/** GET /api/research/{run_id}/content-support-reviews -- the full,
 * append-only review log for this run (optionally filtered to one claim),
 * in submission order. Never an error for "nothing reviewed yet" -- an
 * empty list. */
export async function getContentSupportReviews(
  runId: string,
  params: { claimId?: string } = {},
  options: RequestOptions = {}
): Promise<ContentSupportReviewLogResult> {
  const body = await performRequest(
    `/api/research/${encodeURIComponent(runId)}/content-support-reviews`,
    { signal: options.signal },
    { claim_id: params.claimId }
  );
  if (!body || typeof body !== "object" || !("status" in body)) {
    throw ApiError.contractMismatch();
  }
  return body as ContentSupportReviewLogResult;
}

/** GET /api/research/{run_id}/reevaluations -- every re-evaluation
 * execution ever triggered for this run, oldest first. Each `execution_id`
 * is a normal, complete run_id, readable through every existing GET route
 * (e.g. link to `/runs/{execution_id}/research`). */
export async function getReevaluationExecutions(
  runId: string,
  options: RequestOptions = {}
): Promise<ReevaluationExecutionsResult> {
  const body = await performRequest(`/api/research/${encodeURIComponent(runId)}/reevaluations`, {
    signal: options.signal,
  });
  if (!body || typeof body !== "object" || !("status" in body)) {
    throw ApiError.contractMismatch();
  }
  return body as ReevaluationExecutionsResult;
}

export async function getResearchHistory(
  params: { limit?: number; cursor?: string; ticker?: string; status?: string } = {},
  options: RequestOptions = {}
): Promise<RunHistoryResult> {
  const body = await performRequest(
    "/api/research",
    { signal: options.signal },
    {
      limit: params.limit,
      cursor: params.cursor,
      ticker: params.ticker,
      status: params.status,
    }
  );
  if (looksLikeErrorEnvelope(body) && isFailureShape(body)) {
    return body;
  }
  return adaptOrThrow(adaptRunHistoryResponse(body));
}

/** Suggested filename embedded in the server's own Content-Disposition
 * header (e.g. `attachment; filename="NVDA_ded99ecd_research_export.zip"`).
 * Falls back to a safe generic name only if the header is ever missing or
 * unparseable -- never blocks the download on it. */
function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match?.[1] ?? fallback;
}

/** GET /api/research/{run_id}/export -- a ZIP bundle of this run's already-
 * persisted artifact set (John MVP Gap Closure, Gap B: Result Export).
 * Never recomputes research and never calls a Provider server-side; this
 * is a plain, read-only file download. Distinct from the QA-only
 * unclassified-findings download (`/artifacts/unclassified_findings.json`)
 * -- this is the main, user-facing research export. Throws ApiError on any
 * failure (missing run, run not yet finalized, network failure) so the
 * caller can render a visible failure state rather than appearing to
 * succeed. */
export async function exportResearchRun(
  runId: string,
  options: RequestOptions = {}
): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(buildUrl(`/api/research/${encodeURIComponent(runId)}/export`), {
      signal: options.signal,
      headers: { Accept: "application/zip, application/json" },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw ApiError.aborted();
    }
    throw ApiError.network();
  }

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      try {
        const body = await response.json();
        if (looksLikeErrorEnvelope(body)) {
          throw ApiError.http(
            response.status,
            body.error_code ?? null,
            body.message ?? `Export failed with status ${response.status}.`
          );
        }
      } catch (cause) {
        if (cause instanceof ApiError) throw cause;
        // fall through to the generic error below
      }
    }
    throw ApiError.http(response.status, null, `Export failed with status ${response.status}.`);
  }

  let blob: Blob;
  try {
    blob = await response.blob();
  } catch {
    throw ApiError.invalidResponse("The exported research package could not be read.");
  }
  if (blob.size === 0) {
    throw ApiError.invalidResponse("The exported research package was empty.");
  }

  const filename = filenameFromContentDisposition(
    response.headers.get("content-disposition"),
    `${runId}_research_export.zip`
  );
  return { blob, filename };
}

export async function replayAllSavedOutputs(options: RequestOptions = {}): Promise<ReplayAllResult> {
  const body = await performRequest("/api/replay-all", { method: "POST", signal: options.signal });
  return adaptOrThrow(adaptReplayAllResult(body));
}

/** GET /api/alpha-library -- the canonical Alpha taxonomy (name, thesis,
 * invalidation_conditions, etc.), ticker-independent and static for the
 * lifetime of the running server. Callers should fetch this once (see
 * hooks/useAlphaLibrary.ts) and map by alpha_id, never once per Alpha. */
export async function getAlphaLibrary(options: RequestOptions = {}): Promise<AlphaLibraryResponse> {
  const body = await performRequest("/api/alpha-library", { signal: options.signal });
  return adaptOrThrow(adaptAlphaLibraryResponse(body));
}

export async function getHealth(options: RequestOptions = {}): Promise<HealthResponse> {
  const body = await performRequest("/health", { signal: options.signal });
  return adaptOrThrow(adaptHealthResponse(body));
}

export async function getReadiness(options: RequestOptions = {}): Promise<{
  status: number;
  result: ReadinessResponse;
}> {
  // /ready returns HTTP 503 when not ready -- that is a normal, informative
  // response for this endpoint, not a transport failure, so this fetch
  // path (unlike performRequest) reads the body on both 200 and 503.
  let response: Response;
  try {
    response = await fetch(buildUrl("/ready"), {
      signal: options.signal,
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw ApiError.aborted();
    }
    throw ApiError.network();
  }
  if (response.status === 404) {
    throw ApiError.contractMismatch();
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw ApiError.contractMismatch();
  }
  const result = adaptOrThrow(adaptReadinessResponse(body));
  return { status: response.status, result };
}

function isFailureShape(body: { status: string }): body is { status: "failed" } & Record<string, unknown> {
  return body.status === "failed";
}
