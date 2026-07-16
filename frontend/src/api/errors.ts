/**
 * Stable, safe error surface for the COMQUTOR API client.
 *
 * The backend's own error contract (see comqutor_alpha/api/routes_research.py,
 * routes_system.py) already guarantees every failure response carries a
 * stable `error_code` and a safe, human-readable `message` -- never a raw
 * exception, a traceback, or an HTML error page. This module's job is only
 * to preserve that contract on the way into the UI, and to give the UI one
 * consistent shape to render regardless of *why* a request failed (HTTP
 * error body, non-JSON response, network failure, or an aborted request).
 */

export type ApiErrorKind = "http" | "network" | "aborted" | "invalid_response";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly errorCode: string | null;

  constructor(options: {
    kind: ApiErrorKind;
    message: string;
    status?: number | null;
    errorCode?: string | null;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.kind = options.kind;
    this.status = options.status ?? null;
    this.errorCode = options.errorCode ?? null;
  }

  static network(message = "Could not reach the COMQUTOR API."): ApiError {
    return new ApiError({ kind: "network", message });
  }

  static aborted(): ApiError {
    return new ApiError({ kind: "aborted", message: "Request was cancelled." });
  }

  static invalidResponse(message = "The server returned an unexpected response."): ApiError {
    return new ApiError({ kind: "invalid_response", message });
  }

  static http(status: number, errorCode: string | null, message: string): ApiError {
    return new ApiError({ kind: "http", status, errorCode, message });
  }

  get isAborted(): boolean {
    return this.kind === "aborted";
  }

  get isNetwork(): boolean {
    return this.kind === "network";
  }
}

/** Safe, user-facing copy for every stable error_code this frontend is
 * required to handle explicitly (see task section three). Anything not
 * listed here falls back to a generic, still-safe message -- never the raw
 * backend message is *assumed* unsafe, but we do not depend on it either:
 * these are the actionable, reviewed strings. */
const KNOWN_ERROR_CODE_MESSAGES: Record<string, string> = {
  REAL_RUN_DISABLED:
    "Real TradingAgents execution is disabled on this server. Use an existing completed run, or ask an operator to enable it.",
  REAL_RUN_CONFIG_INVALID:
    "Real TradingAgents execution is enabled but not configured correctly on the server. Contact an operator.",
  REAL_FORCE_REFRESH_DISABLED:
    "Force refresh for real research runs is disabled on this server.",
  RUN_ID_CONFLICT: "That run_id is already in use for a different request.",
  INVALID_FORCE_REFRESH: "force_refresh cannot be combined with an existing run_id.",
  RESEARCH_QUEUE_FULL: "The research job queue is full right now. Please try again shortly.",
  JOB_MANAGER_UNAVAILABLE: "The background research service is not available right now.",
  OFFLINE_DISABLED: "Offline research submissions are disabled on this server.",
  INVALID_ANALYST_SELECTION: "One or more selected analysts are not supported for this request.",
  INTERNAL_ERROR: "The research request failed unexpectedly. Please try again.",
  INVALID_TICKER: "Please enter a valid ticker symbol.",
  RUN_NOT_FOUND: "That research run could not be found.",
  RUN_STATUS_NOT_FOUND: "That research run could not be found.",
  CACHED_RUN_UNAVAILABLE: "The cached result for this run is no longer available.",
  GRAPH_NOT_READY: "The structure graph has not been generated for this run yet.",
  GRAPH_NOT_FOUND: "That research run could not be found.",
  GRAPH_UNAVAILABLE: "Graph storage is temporarily unavailable.",
  GRAPH_CORRUPTED: "The persisted structure graph is incomplete.",
  GRAPH_SCHEMA_MISMATCH: "The persisted structure graph uses an unsupported schema version.",
  CONFLICTS_NOT_READY: "Conflict analysis has not been generated for this research run yet.",
  CONFLICTS_UNAVAILABLE: "Conflict storage is temporarily unavailable.",
  CONFLICTS_CORRUPTED: "The persisted conflict result is incomplete.",
  AGENT_OUTPUTS_NOT_READY: "Structured agent outputs have not been generated for this run yet.",
  AGENT_OUTPUTS_UNAVAILABLE: "Agent output storage is temporarily unavailable.",
  AGENT_OUTPUTS_CORRUPTED: "The persisted agent outputs are incomplete.",
  INVALID_RUN_ID: "That run identifier is not valid.",
};

/** Safe, user-facing text for any ApiError -- never a traceback, never a raw
 * JSON dump. Prefers a known error_code's reviewed copy; falls back to the
 * backend's own safe `message` (already a stable, safe string by contract);
 * falls back further to a generic sentence for network/abort/invalid-shape
 * failures. */
export function describeApiError(error: ApiError): string {
  const knownMessage = error.errorCode ? KNOWN_ERROR_CODE_MESSAGES[error.errorCode] : undefined;
  if (knownMessage) {
    return knownMessage;
  }
  if (error.kind === "http" && error.message) {
    return error.message;
  }
  if (error.kind === "network") {
    return "Could not reach the COMQUTOR API. Check your connection and try again.";
  }
  if (error.kind === "aborted") {
    return "Request was cancelled.";
  }
  return "The server returned an unexpected response.";
}
