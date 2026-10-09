"""Transport-level request/response auditing for real Week2 LLM Provider
calls (2026-10-06, Phase C controlled single-request verification round).

``Week2LLMGateway._request_control_snapshot`` (week2_llm.py) already
captures a sanitized summary of a call's request shape -- but it does so
by calling the model's own ``_get_request_payload`` a SECOND time, with
the same input, immediately before/alongside the real ``.invoke()`` call.
That is a reconstruction via the same method and the same input, not
literal proof that the saved content equals what the network actually
sent: a prior round's own attempt_log never saved the literal request
body at all, and a later review explicitly required that any new audit
mechanism prove wire-identity, not just repeat the existing before-the-
call approximation.

``AuditingTransport`` closes that gap by wrapping the httpx transport
underneath the OpenAI-compatible client stack -- the lowest layer this
project's client construction (``tradingagents.llm_clients.openai_client.
_PASSTHROUGH_KWARGS`` already forwards ``http_client``) exposes a
pluggable seam at. Saving happens on the literal ``httpx.Request``/
``httpx.Response`` objects the transport itself handles, so the saved
bytes and the bytes the network sees (or, in a test, the bytes a fixed-
response ``httpx.MockTransport`` receives) are provably the same object,
not a second, separately-constructed copy.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

_REDACTED_HEADER_NAMES = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie"}


class AuditingTransportError(RuntimeError):
    """Raised when a request audit record fails to persist. The request is
    NEVER forwarded to the wrapped transport when this is raised -- the
    exception propagates out of ``handle_request`` instead, so no bytes
    reach the network (or the test's mock transport) for this attempt."""


def sanitize_headers(headers: httpx.Headers) -> dict[str, str]:
    """Strips auth/credential headers. Never includes their real values --
    the comparison is on header NAME only, so this cannot accidentally
    leak a differently-cased or aliased credential header."""
    return {
        key: ("REDACTED" if key.lower() in _REDACTED_HEADER_NAMES else value)
        for key, value in headers.items()
    }


class AuditingTransport(httpx.BaseTransport):
    """Wraps another httpx transport -- the real network transport in
    production, or a fixed-response ``httpx.MockTransport`` in tests.

    ``save_request(request)`` is called with the literal, fully-read
    ``httpx.Request`` BEFORE it is forwarded to ``wrapped``. If it raises,
    ``wrapped.handle_request`` is never called -- the request is
    genuinely never sent.

    ``save_response(request, response)`` is called with the literal,
    fully-read ``httpx.Response`` AFTER ``wrapped`` returns it. If it
    raises, the response is still returned to this call's caller (the
    Provider already answered; that cannot be undone), but
    ``on_response_save_failed()`` is invoked so the owning Gateway can
    refuse every subsequent attempt.
    """

    def __init__(
        self,
        wrapped: httpx.BaseTransport,
        *,
        save_request: Callable[[httpx.Request], None],
        save_response: Callable[[httpx.Request, httpx.Response], None],
        on_response_save_failed: Callable[[], None],
    ) -> None:
        self._wrapped = wrapped
        self._save_request = save_request
        self._save_response = save_response
        self._on_response_save_failed = on_response_save_failed

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()
        try:
            self._save_request(request)
        except Exception as exc:
            # Normalized to AuditingTransportError regardless of what the
            # underlying save function actually raised (disk full, invalid
            # artifact path, a test's injected RuntimeError, ...) -- the
            # Gateway's own exception-chain scan only needs to recognize
            # ONE type to reliably detect "this request was never sent",
            # whatever the original cause was. Never reached: the line
            # below (self._wrapped.handle_request) is never called when
            # this raises, so the request genuinely never goes out.
            if isinstance(exc, AuditingTransportError):
                raise
            raise AuditingTransportError(f"request audit save failed: {exc}") from exc

        response = self._wrapped.handle_request(request)
        response.read()
        try:
            self._save_response(request, response)
        except Exception:
            self._on_response_save_failed()
        return response

    def close(self) -> None:
        close = getattr(self._wrapped, "close", None)
        if callable(close):
            close()
