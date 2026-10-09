"""T4 round 28 termination probe ONLY -- imported automatically by every Python process started with this directory on
PYTHONPATH (the probe's API server and the job-manager worker it spawns). Never on PYTHONPATH anywhere else.

* replaces the bottom HTTP transport (``httpx.HTTPTransport``) with a fixed-response ``httpx.MockTransport``: the real
  clients, gateway, audit, scheduling, job manager and worker run unmodified;
* blocks every non-loopback socket connection and counts it (R28_PROBE_NET_LOG);
* appends one line per provider request to R28_PROBE_LOG (task, per-process index, time, claim ids);
* R28_PROBE_PLAN=calibrate answers everything at once; R28_PROBE_PLAN=hang answers alpha_classifier requests 1-2 at
  once and holds requests 3-4 open (an in-flight request when the job timeout terminates the worker);
  R28_PROBE_PLAN=hang_cs holds content_support_verification request 2 open.
"""
import json
import os
import socket
import threading
import time

_LOG = os.environ.get("R28_PROBE_LOG")
_NET_LOG = os.environ.get("R28_PROBE_NET_LOG")
_PLAN = os.environ.get("R28_PROBE_PLAN", "calibrate")
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0", None, ""}
_lock = threading.Lock()
_counts: dict = {}


def _append(path, record):
    if not path:
        return
    with _lock, open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


_orig_connect = socket.socket.connect


def _guarded_connect(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) and address else address
    if isinstance(host, str) and (host in _LOOPBACK or host.startswith("127.")) or self.family == getattr(socket, "AF_UNIX", None):
        return _orig_connect(self, address, *args, **kwargs)
    _append(_NET_LOG, {"blocked": str(host), "pid": os.getpid(), "at": time.time()})
    raise OSError(f"r28 probe: non-loopback connection blocked ({host})")


socket.socket.connect = _guarded_connect

try:
    import httpx

    _TASK_PREFIXES = None

    def _prefixes():
        global _TASK_PREFIXES
        if _TASK_PREFIXES is None:
            from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

            _TASK_PREFIXES = {t: Week2LLMGateway._provider_prompt_prefix(t) for t in (
                "claim_batch_enrichment", "alpha_classifier", "content_support_verification", "evidence_stance_classifier", "structure_extractor")}
        return _TASK_PREFIXES

    def _completion(content):
        return httpx.Response(200, json={"id": "probe", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                                         "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(content)}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                                                   "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 40}})

    def _answer(task, payload, index):
        if task == "alpha_classifier":
            return _completion({"decision": "select", "selected_alpha_id": "A304"} if index % 2 else {"decision": "none", "selected_alpha_id": None})
        if task == "claim_batch_enrichment":
            return _completion({"claims": [{"segment_id": s["segment_id"], "claim": s["claim"], "evidence": s["evidence"], "source_section": s["source_section"],
                                            "entities": [], "factors": [], "direction": "unknown", "confidence": 0.0} for s in payload.get("segments", [])]})
        if task == "content_support_verification":
            return _completion({"items": [{"claim_id": i["claim_id"], "core_proposition": "probe", "status": "SUPPORTS", "support_basis": "DIRECT_FACT",
                                           "used_source_id": i["allowed_candidates"][0]["source_id"], "used_location": "excerpt",
                                           "supporting_quote_or_data": (i["allowed_candidates"][0].get("excerpt") or "")[:30], "inference_facts": [],
                                           "inference_assumptions": [], "rationale": "probe", "supported_proposition": i["proposition"],
                                           "unsupported_remainder": "", "unsupported_remainder_materiality": "NONE"} for i in payload.get("items", [])]})
        if task == "evidence_stance_classifier":
            return _completion({"items": [{"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": "supports_alpha",
                                           "counter_alpha_id": None} for i in payload.get("items", [])]})
        if task == "structure_extractor":
            return _completion({"edges": []})
        return httpx.Response(400, json={"error": {"message": "probe: unrecognized task"}})

    def _handler(request):
        content = json.loads(request.content)["messages"][0]["content"]
        prefixes = _prefixes()
        task = next((t for t, p in prefixes.items() if content.startswith(p)), "UNKNOWN_TASK")
        payload = json.loads(content[len(prefixes[task]):]) if task != "UNKNOWN_TASK" else {}
        with _lock:
            _counts[task] = _counts.get(task, 0) + 1
            index = _counts[task]
        hold = (_PLAN == "hang" and task == "alpha_classifier" and index in (3, 4)) or (
            _PLAN == "hang_cs" and task == "content_support_verification" and index == 2)
        _append(_LOG, {"task": task, "index": index, "pid": os.getpid(), "at": time.time(), "claim": payload.get("claim"), "held_open": hold})
        if hold:
            time.sleep(3600)  # in flight until the worker process is terminated
        return _answer(task, payload, index)

    class _ProbeTransport(httpx.MockTransport):
        def __init__(self, *args, **kwargs):
            super().__init__(_handler)

    httpx.HTTPTransport = _ProbeTransport
except Exception as exc:  # pragma: no cover - visible in the probe log if it ever happens
    _append(_LOG, {"sitecustomize_error": repr(exc)})
