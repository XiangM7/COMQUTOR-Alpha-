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
import type {
  AgentOutputsResult,
  CanonicalResearchResult,
  ConflictsResult,
  HealthResponse,
  ReadinessResponse,
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

export async function replayAllSavedOutputs(options: RequestOptions = {}): Promise<ReplayAllResult> {
  const body = await performRequest("/api/replay-all", { method: "POST", signal: options.signal });
  return adaptOrThrow(adaptReplayAllResult(body));
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
