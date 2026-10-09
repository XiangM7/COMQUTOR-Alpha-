#!/usr/bin/env python3
"""T3 closeout: replay the whole prediction of execution t3joint-20261008T170322Z-bd99811e OFFLINE from its saved real responses.

The real production path runs unchanged -- the frozen sample loader, the production request builders, one production Week2LLMGateway per
task built from tradingagents' create_llm_client with the execution's signed configuration, the send guard checking every request against
the execution's frozen inputs, the production request/response audit and the checkpoint, the production validators, mapper, stance pass
and L4 gates. Only the bottom HTTP transport is replaced: it answers each request with the response the provider really returned to the
byte-identical request in the execution (looked up by the request body's sha256). A request that the execution never sent gets no answer
(a transport error, recorded) -- nothing is invented.

What this proves: how the CURRENT code judges the SAME real responses. Run on the unchanged code it must reproduce the execution's
predictions exactly; after a fix, every difference is attributable to the fix. It is NOT a new model judgment, and its results are a
development-regression view -- they never replace the execution's frozen predictions or score.

    python replay_execution_offline.py --work-dir <new dir> --compare outputs/t3_joint_evaluations/<id>/joint_predictions.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
DRIVERS = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
ROUND25 = DRIVERS / "round25_t3_minimal_prep_20261008"
EXECUTION_ID = "t3joint-20261008T170322Z-bd99811e"
EXECUTION_DIR = REPO / "outputs/t3_joint_evaluations" / EXECUTION_ID
PLAN = ROUND25 / f"B4_execution/authorized_plan_SIGNED_{EXECUTION_ID}.json"
FAKE_KEY = "offline-replay-not-a-key"


def load_driver():
    spec = importlib.util.spec_from_file_location("t3_joint_driver_replay", DRIVERS / "t3_joint_sample_driver.py")
    assert spec is not None and spec.loader is not None
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    return driver


def saved_responses(driver) -> dict[str, dict[str, Any]]:
    """request body sha256 -> the provider's saved response for that exact request, across the three tasks."""
    out: dict[str, dict[str, Any]] = {}
    for task in driver.TASKS:
        logs = EXECUTION_DIR / task / EXECUTION_ID / "error_logs"
        requests = [json.loads(line) for line in (logs / "week2_llm_provider_request_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        responses = {r["attempt_id"]: r for r in (json.loads(line) for line in
                     (logs / "week2_llm_provider_response_audit.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
        for req in requests:
            if hashlib.sha256(req["body"].encode("utf-8")).hexdigest() != req["body_sha256"]:
                raise ValueError(f"{task} {req['attempt_id']}: saved request body does not match its recorded sha256")
            resp = responses.get(req["attempt_id"])
            if resp is None:
                continue  # no saved response: the replay gives no answer either
            if hashlib.sha256(resp["body"].encode("utf-8")).hexdigest() != resp["body_sha256"]:
                raise ValueError(f"{task} {req['attempt_id']}: saved response body does not match its recorded sha256")
            out[req["body_sha256"]] = {"task": task, "attempt_id": req["attempt_id"], "status_code": resp["status_code"], "body": resp["body"]}
    return out


def replay(work_dir: Path) -> dict[str, Any]:
    driver = load_driver()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    config = driver.FrozenConfig(**{**plan["config"], "stop_on_http_status": tuple(plan["config"]["stop_on_http_status"])})
    frozen = json.loads((REPO / plan["frozen_requests"]).read_text(encoding="utf-8"))
    saved = saved_responses(driver)
    answered: list[str] = []
    unanswered: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sha = hashlib.sha256(request.content).hexdigest()
        hit = saved.get(sha)
        if hit is None:
            unanswered.append({"request_body_sha256": sha})
            raise httpx.ConnectError("offline replay: this exact request was never sent in the execution, so there is no saved answer")
        answered.append(hit["attempt_id"])
        return httpx.Response(hit["status_code"], content=hit["body"].encode("utf-8"), headers={"content-type": "application/json"})

    work_dir.mkdir(parents=True, exist_ok=False)
    checkpoint = driver.Checkpoint(work_dir / "checkpoint.jsonl")
    guard = driver.SendGuard(frozen, checkpoint)
    gateways = driver.build_task_gateways(config, work_dir, f"replay-of-{EXECUTION_ID}", guard,
                                          base_transport_factory=lambda: httpx.MockTransport(handler), api_key=FAKE_KEY)
    manifest = REPO / plan["manifest"]
    # keep the match records and the records the L4 step judged (predict() itself does not return them); the wrapper only observes
    consumed: dict[str, Any] = {}
    production_l4 = driver._l4

    def observing_l4(samples, l2, l3, matches):
        consumed.update({s["sample_id"]: {"match": matches.get(s["sample_id"]), "record_after_L1": s["record"]} for s in samples})
        return production_l4(samples, l2, l3, matches)

    driver._l4 = observing_l4
    predictions = driver.predict(driver.load_samples(manifest), gateways=gateways, config=config, guard=guard)
    with (work_dir / "replayed_predictions.jsonl").open("w", encoding="utf-8") as fh:
        for p in predictions:
            fh.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
    (work_dir / "l4_inputs_by_sample.json").write_text(json.dumps(consumed, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n",
                                                       encoding="utf-8")
    return {"predictions": predictions, "guard_tripped": guard.tripped, "saved_responses_used": len(answered),
            "saved_responses_available": len(saved), "requests_without_saved_answer": unanswered,
            "checkpoint": driver.summarize_checkpoint(checkpoint.path)}


def compare(predictions: list[dict], reference_path: Path) -> dict[str, Any]:
    reference = {json.loads(line)["sample_id"]: json.loads(line) for line in reference_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    replayed = {p["sample_id"]: p for p in predictions}
    differences = []
    for sid in sorted(set(reference) | set(replayed)):
        a, b = reference.get(sid), replayed.get(sid)
        if a is None or b is None:
            differences.append({"sample_id": sid, "link": "*", "execution": a is not None, "replay": b is not None})
            continue
        for link in sorted(set(a) | set(b)):
            if json.dumps(a.get(link), sort_keys=True) != json.dumps(b.get(link), sort_keys=True):
                differences.append({"sample_id": sid, "link": link, "execution": a.get(link), "replay": b.get(link)})
    return {"reference": str(reference_path.relative_to(REPO)), "samples": len(replayed), "identical": not differences, "differences": differences}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--compare", default=str(EXECUTION_DIR / "joint_predictions.jsonl"))
    args = ap.parse_args(argv)
    work_dir = Path(args.work_dir)
    if work_dir.exists():
        print("refusing: work dir exists", work_dir, file=sys.stderr)
        return 2
    result = replay(work_dir)
    comparison = compare(result["predictions"], Path(args.compare).resolve())
    summary = {k: v for k, v in result.items() if k != "predictions"}
    summary["comparison_with_execution"] = comparison
    summary["note"] = ("offline replay of SAVED real responses through the current production code; not a new model judgment; "
                       "the execution's own predictions and score are unchanged")
    (work_dir / "replay_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"guard_tripped": result["guard_tripped"], "saved_responses_used": result["saved_responses_used"],
                      "saved_responses_available": result["saved_responses_available"],
                      "requests_without_saved_answer": len(result["requests_without_saved_answer"]),
                      "identical_to_execution": comparison["identical"], "differences": len(comparison["differences"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
