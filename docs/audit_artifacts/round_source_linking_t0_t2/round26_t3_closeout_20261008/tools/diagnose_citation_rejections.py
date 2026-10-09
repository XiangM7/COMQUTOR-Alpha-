#!/usr/bin/env python3
"""T3 closeout: the six content-support replies that execution t3joint-20261008T170322Z-bd99811e rejected as quote_or_data_not_found,
taken apart against the request's real candidates (zero network).

For each: what the model cited (source, location, text/values), what the request actually offered (the candidate's excerpt and
data_snapshot, rebuilt with the production request builder and checked equal to the saved request), and what each production check
decides on it -- the multi-field path check, the whole-quote literal check, the data-value check -- plus, per ';' part: is it a literal
excerpt quote at token boundaries, does its paired path resolve, and does the part's value equal the resolved value. The final line is
the CURRENT production validator's verdict on the saved reply, so the same tool shows the behavior before and after a fix.

    python diagnose_citation_rejections.py --out 01_citation_rejections/six_rejections_<before|after>_fix.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
DRIVERS = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
ROUND25 = DRIVERS / "round25_t3_minimal_prep_20261008"
EXECUTION_ID = "t3joint-20261008T170322Z-bd99811e"
EXECUTION_DIR = REPO / "outputs/t3_joint_evaluations" / EXECUTION_ID
LOGS = EXECUTION_DIR / "content_support_verification" / EXECUTION_ID / "error_logs"


def _load_driver():
    spec = importlib.util.spec_from_file_location("t3_joint_driver_diag", DRIVERS / "t3_joint_sample_driver.py")
    assert spec is not None and spec.loader is not None
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    return driver


def _boundary_literal(part: str, excerpt: str) -> bool:
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(part) + r"(?![A-Za-z0-9]|\.\d)", excerpt) is not None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    from comqutor_alpha.structure_engine import content_support_llm as cs

    driver = _load_driver()
    predictions = {json.loads(line)["sample_id"]: json.loads(line) for line in (EXECUTION_DIR / "joint_predictions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    rejected = sorted(sid for sid, p in predictions.items() if p["L1"].get("status") == "TASK_FAILED" and p["L1"].get("reason") == "quote_or_data_not_found")
    plan = json.loads((ROUND25 / f"B4_execution/authorized_plan_SIGNED_{EXECUTION_ID}.json").read_text(encoding="utf-8"))
    samples = driver.load_samples(REPO / plan["manifest"])
    for s in samples:
        driver.strip_saved_llm_content_verdict(s["record"])
    items = {i.claim_id: i for run_items in driver.content_support_request_items(samples).values() for i in run_items}
    requests = [json.loads(line) for line in (LOGS / "week2_llm_provider_request_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    responses = {r["attempt_id"]: r for r in (json.loads(line) for line in (LOGS / "week2_llm_provider_response_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    by_claim = {r["claim_ids"][0]: r for r in requests if len(r.get("claim_ids") or []) == 1}

    out = []
    for sid in rejected:
        sample = next(s for s in samples if s["sample_id"] == sid)
        claim_id = sample["record"]["claim_id"]
        item = items[claim_id]
        req = by_claim[claim_id]
        content = json.loads(req["body"])["messages"][0]["content"]
        sent_payload = json.loads(content[content.index('{"items"'):])
        rebuilt_equal = sent_payload == json.loads(json.dumps({"items": [item.payload]}, ensure_ascii=False, default=str))
        resp = responses[req["attempt_id"]]
        reply = json.loads(json.loads(resp["body"])["choices"][0]["message"]["content"])["items"][0]
        candidate = item.candidates_by_id.get(str(reply.get("used_source_id") or ""))
        quote = str(reply.get("supporting_quote_or_data") or "").strip()
        location = str(reply.get("used_location") or "")
        excerpt = str((candidate or {}).get("excerpt") or "")
        parts = [q.strip() for q in quote.split(";") if q.strip()]
        paths = [p.strip() for p in location.split(";") if p.strip()]
        path_list = bool(paths) and all(cs._looks_like_dotted_path(p) for p in paths)
        part_checks = []
        for index, part in enumerate(parts):
            check = {"part": part, "literal_in_excerpt": part in excerpt, "literal_at_token_boundaries": _boundary_literal(part, excerpt),
                     "excerpt_occurrences": excerpt.count(part)}
            if path_list and len(paths) == len(parts):
                resolved = cs._resolve_candidate_path(candidate or {}, paths[index])
                value = re.split(r"[=:]", part)[-1].strip()
                check.update({"paired_path": paths[index], "path_resolves": resolved is not cs._MISSING_PATH,
                              "resolved_value": None if resolved is cs._MISSING_PATH else resolved, "part_value": value,
                              "value_equals_resolved": resolved is not cs._MISSING_PATH and cs._values_match(value, resolved),
                              "label_form_accepted_by_path_check": ":" in part and cs._normalize_field_label(part.partition(":")[0])
                              == cs._normalize_field_label(paths[index].rsplit(".", 1)[-1])})
            part_checks.append(check)
        validated, reason = cs._validate_response_item(item, reply)
        out.append({
            "sample_id": sid, "claim_id": claim_id, "attempt_id": req["attempt_id"],
            "request_body_sha256": req["body_sha256"], "response_body_sha256": resp["body_sha256"],
            "request_rebuilt_by_production_builder_equals_sent": rebuilt_equal,
            "model_reply": {k: reply.get(k) for k in ("status", "support_basis", "used_source_id", "used_location", "supporting_quote_or_data",
                                                      "unsupported_remainder_materiality")},
            "request_candidates": [{"source_id": c.get("source_id"), "source_type": c.get("source_type"), "excerpt_chars": len(str(c.get("excerpt") or "")),
                                    "excerpt_sha256": hashlib.sha256(str(c.get("excerpt") or "").encode("utf-8")).hexdigest(),
                                    "data_snapshot_keys": sorted((c.get("data_snapshot") or {}).keys())} for c in item.payload["allowed_candidates"]],
            "cited_source_in_candidates": candidate is not None,
            "production_checks_on_whole_citation": {
                "multi_field_path_check": cs._multi_field_citation_valid(candidate, location, quote) if candidate else None,
                "used_location_is_dotted_path_list": path_list, "path_count": len(paths), "quote_part_count": len(parts),
                "whole_quote_literal_in_excerpt": cs._quote_found_in_excerpt(quote, excerpt),
                "whole_quote_as_data_value": cs._data_field_found(quote, (candidate or {}).get("data_snapshot")),
            },
            "quote_parts": part_checks,
            "current_validator": {"accepted": reason is None, "reason": reason,
                                  "effective_content_support_status": cs._effective_content_support_status(validated) if validated else None},
        })
    Path(args.out).write_text(json.dumps({"execution_id": EXECUTION_ID, "rejected_at_execution": rejected, "items": out},
                                         ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    for row in out:
        print(row["sample_id"], "rebuilt==sent:", row["request_rebuilt_by_production_builder_equals_sent"], "| current validator:",
              row["current_validator"]["reason"] or f"ACCEPTED -> {row['current_validator']['effective_content_support_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
