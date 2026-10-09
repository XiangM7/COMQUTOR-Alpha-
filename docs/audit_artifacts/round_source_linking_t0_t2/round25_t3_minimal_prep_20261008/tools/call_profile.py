"""Read-only: per task, what each saved run actually sent/received (prompt, model, request controls, attempts, finish reasons, latency, usage)."""
import collections
import json
import sys
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())


def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return round(vals[f] + (vals[c] - vals[f]) * (k - f), 1)


def profile(path):
    out = {}
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    by = collections.defaultdict(list)
    for r in rows:
        by[r.get("task")].append(r)
    for task, rs in by.items():
        attempts = [a for r in rs for a in (r.get("request_attempts") or [])]
        lat_call = [r["latency_ms"] for r in rs if isinstance(r.get("latency_ms"), (int,float)) and r.get("execution_mode")=="live" and not (r.get("cache") or {}).get("hit")]
        out[task] = {
            "calls": len(rs),
            "prompt_versions": dict(collections.Counter(r.get("prompt_version") for r in rs)),
            "prompt_sha256": dict(collections.Counter(r.get("prompt_sha256") for r in rs)),
            "provider_model": dict(collections.Counter(f"{r.get('provider')}/{r.get('model')}" for r in rs)),
            "execution_mode": dict(collections.Counter(r.get("execution_mode") for r in rs)),
            "cache_hit": dict(collections.Counter(bool((r.get("cache") or {}).get("hit")) for r in rs)),
            "request_control": dict(collections.Counter(json.dumps({k:v for k,v in (r.get("request_control") or {}).items() if k!="schema_version"}, sort_keys=True) for r in rs)),
            "provider_status": dict(collections.Counter(r.get("provider_status") for r in rs)),
            "validation_status": dict(collections.Counter(r.get("validation_status") for r in rs)),
            "retry_count": dict(collections.Counter(r.get("retry_count") for r in rs)),
            "fallback_used": dict(collections.Counter(r.get("fallback_used") for r in rs)),
            "attempts_total": len(attempts),
            "attempt_finish_reason": dict(collections.Counter(a.get("finish_reason") for a in attempts)),
            "attempt_provider_status": dict(collections.Counter(a.get("provider_status") for a in attempts)),
            "attempt_error_code": dict(collections.Counter(a.get("error_code") for a in attempts)),
            "attempts_with_usage": sum(1 for a in attempts if a.get("raw_usage")),
            "latency_ms_live_calls": {"n": len(lat_call), "p50": pct(lat_call,.5), "p90": pct(lat_call,.9), "p95": pct(lat_call,.95), "max": max(lat_call) if lat_call else None},
            "completion_tokens": (lambda v: {"n": len(v), "p50": pct(v,.5), "p95": pct(v,.95), "max": max(v) if v else None})([a["raw_usage"].get("completion_tokens") for a in attempts if a.get("raw_usage") and isinstance(a["raw_usage"].get("completion_tokens"), int)]),
        }
    return out


if __name__ == "__main__":
    res = {}
    for p in sys.argv[1:]:
        res[p] = profile(REPO / p)
    print(json.dumps(res, indent=1, ensure_ascii=False))
