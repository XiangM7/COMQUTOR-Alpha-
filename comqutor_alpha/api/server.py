"""Local/internal ASGI entrypoint for the COMQUTOR Alpha API (W5.1A).

Importing this module never starts a server -- ``uvicorn`` is only imported
inside :func:`main`, and :func:`main` is only invoked via the
``comqutor-api`` console script (``if __name__ == "__main__"`` guard is not
even needed here, since nothing at module scope calls it).

Deliberately minimal: no CORS, no authentication, no health/readiness
endpoint, no Docker service wiring -- those remain out of scope for this
task (see docs referenced in the W5.1A task description). Default bind is
``127.0.0.1`` (never ``0.0.0.0``) -- a local/internal deployment boundary,
adjustable only via explicit server-side environment variables, never from
an HTTP request.
"""

from __future__ import annotations

import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class ServerConfigurationError(Exception):
    """Safe server-configuration error: carries a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _resolve_host() -> str:
    host = os.environ.get("COMQUTOR_API_HOST", "").strip()
    return host or DEFAULT_HOST


def _resolve_port() -> int:
    raw_port = os.environ.get("COMQUTOR_API_PORT", "").strip()
    if not raw_port:
        return DEFAULT_PORT
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ServerConfigurationError("INVALID_COMQUTOR_API_PORT") from exc
    if not (1 <= port <= 65535):
        raise ServerConfigurationError("INVALID_COMQUTOR_API_PORT")
    return port


def main() -> None:
    """Console-script entrypoint (``comqutor-api``). Requires the ``api``
    optional dependency group (``pip install "tradingagents[api]"``)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "The 'api' optional dependency group is not installed. "
            "Run: pip install \"tradingagents[api]\""
        ) from exc

    from comqutor_alpha.api.main import app

    if app is None:
        raise SystemExit(
            "The 'api' optional dependency group is not installed. "
            "Run: pip install \"tradingagents[api]\""
        )

    try:
        host = _resolve_host()
        port = _resolve_port()
    except ServerConfigurationError:
        raise SystemExit("COMQUTOR_API_PORT must be an integer between 1 and 65535.") from None

    # No secrets are ever part of host/port -- safe to log as-is.
    print(f"Starting COMQUTOR Alpha API on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
