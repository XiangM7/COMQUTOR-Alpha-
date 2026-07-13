"""Controlled JSON-only LLM access for COMQUTOR Week 1-2 extraction tasks."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from threading import Lock
from typing import Any, TypeVar

from comqutor_alpha.storage.file_store import append_jsonl_record


ERROR_LOG_ARTIFACT_PATH = "error_logs/week2_llm_errors.jsonl"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_MAX_CALLS = 32
MAX_SERVER_RETRIES = 2
MAX_SERVER_CALLS = 100
MAX_PROMPT_PAYLOAD_CHARS = 60_000

T = TypeVar("T")

_TASK_INSTRUCTIONS = {
    "structured_claims": (
        "Extract independent investment claims from the supplied agent report. Return one JSON "
        "object with a claims array. Each item must contain claim, evidence, entities, factors, "
        "direction, confidence, and source_section. Evidence must be a verbatim excerpt from the "
        "report. Omit headings, tables, disclaimers, and decorative text."
    ),
    "alpha_classifier": (
        "Select at most one alpha from allowed_alpha_ids, or defer when the supplied admissible "
        "candidates cannot be distinguished. Return one JSON object with decision set to select "
        "or defer and selected_alpha_id set to an allowed ID or null. Do not create candidates, "
        "change admissibility, or provide a trading decision."
    ),
    "structure_extractor": (
        "Extract only evidence-backed relations between supplied allowed_factors. Return one JSON "
        "object with an edges array. Each edge must contain source_factor, target_factor, edge_type "
        "(causal, supportive, or conflicting), assertion_status (asserted, conditional, negated, "
        "mixed, or unknown), and confidence. Return an empty array when no relation is stated."
    ),
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def call_with_timeout(function: Callable[[], T], timeout_seconds: float) -> T:
    """Run a blocking provider call with a caller-side wall-clock deadline."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comqutor-week2-llm")
    future = executor.submit(function)
    try:
        return future.result(timeout=max(float(timeout_seconds), 0.01))
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError("Week 2 LLM call timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _strict_json_object(response: Any) -> dict[str, Any]:
    if isinstance(response, Mapping):
        return dict(response)
    content = response if isinstance(response, str) else getattr(response, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing JSON response content")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("JSON response must be an object")
    return parsed


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class Week2LLMGateway:
    """Strict JSON gateway with bounded retries, timeout, and per-run call budget."""

    def __init__(
        self,
        model: Any,
        *,
        run_id: str,
        output_root: Any,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_calls: int = DEFAULT_MAX_CALLS,
    ) -> None:
        self._model = model
        self.run_id = str(run_id)
        self.output_root = output_root
        self.timeout_seconds = max(float(timeout_seconds), 0.01)
        self.max_retries = min(max(int(max_retries), 0), MAX_SERVER_RETRIES)
        self.max_calls = min(max(int(max_calls), 1), MAX_SERVER_CALLS)
        self._call_count = 0
        self._budget_exhaustion_logged = False
        self._lock = Lock()

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    def _reserve_call(self) -> bool:
        with self._lock:
            if self._call_count >= self.max_calls:
                return False
            self._call_count += 1
            return True

    def _log(self, task: str, error_code: str, attempt: int) -> None:
        append_jsonl_record(
            self.run_id,
            ERROR_LOG_ARTIFACT_PATH,
            {
                "run_id": self.run_id,
                "task": task,
                "error_code": error_code,
                "attempt": attempt,
                "created_at": _now(),
            },
            output_root=self.output_root,
        )

    def _log_budget_exhausted_once(self, task: str, attempt: int) -> None:
        with self._lock:
            if self._budget_exhaustion_logged:
                return
            self._budget_exhaustion_logged = True
        self._log(task, "WEEK2_LLM_CALL_BUDGET_EXHAUSTED", attempt)

    def invoke_json(
        self,
        task: str,
        payload: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
    ) -> T | None:
        instruction = _TASK_INSTRUCTIONS.get(task)
        if instruction is None:
            raise ValueError(f"Unsupported Week 2 LLM task: {task}")

        serialized = json.dumps(dict(payload), ensure_ascii=False, default=str)
        if len(serialized) > MAX_PROMPT_PAYLOAD_CHARS:
            self._log(task, "WEEK2_LLM_INPUT_TOO_LARGE", 0)
            return None
        prompt = (
            "You are a constrained COMQUTOR extraction component. Return strict JSON only, with "
            "no markdown and no hidden reasoning. "
            f"{instruction}\nINPUT_JSON:\n{serialized}"
        )

        for attempt in range(1, self.max_retries + 2):
            if not self._reserve_call():
                self._log_budget_exhausted_once(task, attempt)
                return None
            try:
                response = call_with_timeout(
                    lambda: self._model.invoke(prompt),
                    self.timeout_seconds,
                )
                parsed = _strict_json_object(response)
                return validator(parsed)
            except TimeoutError:
                error_code = "WEEK2_LLM_TIMEOUT"
            except json.JSONDecodeError:
                error_code = "WEEK2_LLM_INVALID_JSON"
            except (TypeError, ValueError, KeyError):
                error_code = "WEEK2_LLM_VALIDATION_FAILED"
            except Exception:
                error_code = "WEEK2_LLM_PROVIDER_ERROR"
            self._log(task, error_code, attempt)
        return None


def _log_configuration_error(run_id: str, output_root: Any, error_code: str) -> None:
    append_jsonl_record(
        run_id,
        ERROR_LOG_ARTIFACT_PATH,
        {
            "run_id": run_id,
            "task": "gateway_initialization",
            "error_code": error_code,
            "attempt": 0,
            "created_at": _now(),
        },
        output_root=output_root,
    )


def build_server_week2_llm_gateway(run_id: str, output_root: Any) -> Week2LLMGateway | None:
    """Build the existing TradingAgents provider only after explicit server opt-in."""
    if not _enabled(os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED")):
        return None

    provider = (
        os.environ.get("COMQUTOR_WEEK2_LLM_PROVIDER")
        or os.environ.get("TRADINGAGENTS_LLM_PROVIDER")
        or ""
    ).strip()
    model_name = (
        os.environ.get("COMQUTOR_WEEK2_LLM_MODEL")
        or os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM")
        or ""
    ).strip()
    if not provider or not model_name:
        _log_configuration_error(run_id, output_root, "WEEK2_LLM_CONFIG_INCOMPLETE")
        return None

    timeout_seconds = _bounded_float(
        os.environ.get("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS"),
        DEFAULT_TIMEOUT_SECONDS,
        1.0,
        120.0,
    )
    max_retries = _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_LLM_MAX_RETRIES"),
        DEFAULT_MAX_RETRIES,
        0,
        MAX_SERVER_RETRIES,
    )
    max_calls = _bounded_int(
        os.environ.get("COMQUTOR_WEEK2_LLM_MAX_CALLS"),
        DEFAULT_MAX_CALLS,
        1,
        MAX_SERVER_CALLS,
    )
    base_url = (
        os.environ.get("COMQUTOR_WEEK2_LLM_BASE_URL")
        or os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL")
        or None
    )

    try:
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=provider,
            model=model_name,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )
        model = client.get_llm()
    except Exception:
        _log_configuration_error(run_id, output_root, "WEEK2_LLM_INITIALIZATION_FAILED")
        return None

    return Week2LLMGateway(
        model,
        run_id=run_id,
        output_root=output_root,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_calls=max_calls,
    )
