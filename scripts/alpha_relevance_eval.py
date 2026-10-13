#!/usr/bin/env python3
"""Offline tools of the P4 phase 2 small-sample relevance evaluation -- no model, no network, no database.

  build-sample  --out-dir <dir> [--a9-fixtures <json>]
      scan every ORIGINAL saved run (outputs/runs, outputs/t4_runs; derived executions excluded), select the stratified sample of real
      (claim, saved matched Alpha) pairs, write sample/sample_manifest.json, sample/coverage_report.md, sample/sample_list.csv and
      sample/candidate_pool_summary.json
  build-review  --manifest <json> --out-dir <dir> [--a9-fixtures <json>]
      the blind review packet (review/blind_review_sheet_A.csv, _B.csv, review_definitions.md, README) and, apart from it,
      engineering_draft/engineering_draft_labels_DRAFT.csv
  build-plan    --manifest <json> --out-dir <dir> [--stance-ledger <jsonl> ...] [--cap-ledger <jsonl> ...]
                [--relevance-ledger <jsonl> ...] [--repeat-samples S1,S2] [--purpose <text>] [--purpose-kind <kind>]
                [--experiment-config <name>] [--retest] [--pre-registered <file>]
      the LIVE execution plan (plan/execution_plan.json + .md) and the unsigned authorization template. With --relevance-ledger the
      estimates are measured on the relevance task's own real calls; --retest = a development retest (no quality threshold);
      --pre-registered freezes that file's sha256 (e.g. the engineering expectations) into the plan before anything is sent
  build-retest-sample --manifest <json> --selection <json> --review-a <csv> --out-dir <dir>
      session 4: an exact subset of the sample for a development retest (retest_sample/retest_manifest.json, the reference rows of
      reviewer A for those samples copied field by field, and the provenance) -- no sample is created and no answer is changed.
      Session 6: the selection may list "repaired" samples ({original_sample_id, source_file, json_path, char_start, char_end,
      defect, method}); each becomes a separate sample <id>R read from the saved source (the original is unchanged) and has no
      reference row until the owner labels it
  input-quality --manifest <json> --out <json>
      session 6: per sample, the mechanical text notes (sent to the model as hints) and the report-only notes; nothing is excluded
  evaluate      --manifest <json> --plan <json> --eval-dir <dir> --review-a <csv> [--review-b <csv>] --out-dir <dir>
      the evaluation report (evaluation_report.json + .md, per_sample.csv)

Execution itself is NOT here: it is ``scripts/alpha_relevance_judgment.py run-plan`` (explicit mode + authorization).
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha import alpha_relevance_eval_prep as ep  # noqa: E402
from comqutor_alpha.alpha_library.alpha_relevance_elements import (  # noqa: E402
    load_relevance_definitions,
)

A9_FIXTURES = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/round36_t1_migration_20261010/followup_20261011/A9_criterion/alpha_tier_fixtures_v2.json"
STANCE_LEDGERS = (
    REPO_ROOT / "outputs/t4_runs/12591384-0b26-470d-a99d-a49c00be440b/llm_semantic_calls.jsonl",
    REPO_ROOT / "outputs/t4_runs/fa642639-8d93-4f9a-9de1-2c4d789eade8/llm_semantic_calls.jsonl",
)
# 2026-10-12 (P4 phase 2): the request name is not the served model. The vendor's CURRENT description of what serves the request name
# is quoted from the owner's brief of that date (not re-checked online in this round); the earlier vendor note is the one recorded in
# comqutor_alpha/llm/cost_basis.py. What the provider actually reported is measured from the saved ledgers and recorded per call at execution.
MODEL_IDENTITY_NOTE = {
    "documented_serving_model": {"name": "V4.1-Flash", "as_of": "2026-10-12",
                                 "source": "owner brief of 2026-10-12 citing the vendor's current documentation; not re-checked online in this round"},
    "earlier_vendor_note": {"text": "deepseek-v4-flash is the vendor's documented legacy alias of deepseek-flash", "queried_at": "2026-09-30",
                            "source": "comqutor_alpha/llm/cost_basis.py PRICING_SOURCE"},
}
CAP_LEDGERS = (
    REPO_ROOT / "outputs/runs/034a0a60-430e-41f8-8321-03a11389707a/llm_semantic_calls.jsonl",
    *sorted((REPO_ROOT / "outputs/t3_prompt_v7_verification").glob("t3live_*/llm_semantic_calls.jsonl")),
)


def _original_runs() -> list[Path]:
    return sorted(p for root in ep.SAVED_RUN_ROOTS if root.is_dir() for p in root.iterdir() if p.is_dir() and ep.is_original_run_dir(p))


def _coverage_markdown(manifest: dict, pool: dict) -> str:
    selected = collections.Counter(s["selection"]["primary_stratum"] for s in manifest["samples"])
    lines = ["# Sample coverage report (P4 phase 2)", "",
             f"Pool: {pool['original_runs']} original saved runs, {pool['matched_pairs']} matched (claim, saved matched Alpha) pairs, "
             f"{pool['unique_pairs']} unique by (claim text, Alpha). Sample: {manifest['sample_count']} real pairs, "
             f"{len({s['source_run_id'] for s in manifest['samples']})} source runs.", "",
             "Strata come from lexical heuristics and the round-36 A9 material. They decide SELECTION only; they are not labels, never "
             "reach the blind sheet, and a pair may belong to several strata (its primary stratum is the one it was selected for).", "",
             "| stratum | meaning | unique pairs available | target | selected |", "|---|---|---|---|---|"]
    for stratum in ep.STRATUM_PRIORITY:
        lines.append(f"| {stratum} | {ep.STRATUM_MEANING[stratum]} | {manifest['availability_unique_pairs'][stratum]} | "
                     f"{ep.DEFAULT_QUOTAS.get(stratum, 0)} | {selected.get(stratum, 0)} |")
    lines += ["", "Shortfalls (target not reached): " + (json.dumps(manifest["shortfalls"], ensure_ascii=False) if manifest["shortfalls"] else "none"), "",
              "## Boundary elements (every element of the definitions, zero rows included)", "",
              "| kind | element | unique pool pairs that trigger it lexically | selected |", "|---|---|---|---|"]
    gaps = []
    for kind, elements in manifest["boundary_element_coverage"].items():
        for element, counts in elements.items():
            lines.append(f"| {kind} | `{element}` | {counts['available']} | {counts['selected']} |")
            if counts["available"] == 0:
                gaps.append(f"{kind} `{element}`: no real pair in the pool")
            elif counts["selected"] == 0:
                gaps.append(f"{kind} `{element}`: {counts['available']} pool pairs, none selected (quota reached)")
    lines += ["", "Gaps (reported, never filled with constructed samples):", ""] + ([f"- {g}" for g in gaps] or ["- none"])
    lines += ["", "| Alpha | selected | pool pairs |", "|---|---|---|"]
    by_alpha = collections.Counter(s["target_alpha_id"] for s in manifest["samples"])
    for alpha in sorted(pool["pairs_by_alpha"]):
        lines.append(f"| {alpha} | {by_alpha.get(alpha, 0)} | {pool['pairs_by_alpha'][alpha]} |")
    lines += ["", "| ticker | selected | pool pairs |", "|---|---|---|"]
    by_ticker = collections.Counter(s["ticker"] for s in manifest["samples"])
    for ticker in sorted(pool["pairs_by_ticker"]):
        lines.append(f"| {ticker} | {by_ticker.get(ticker, 0)} | {pool['pairs_by_ticker'][ticker]} |")
    lines += ["", "This sample serves a preliminary verification only; it does not represent every Alpha or every input.", ""]
    return "\n".join(lines)


def build_sample(args: argparse.Namespace) -> dict:
    out = Path(args.out_dir) / "sample"
    out.mkdir(parents=True, exist_ok=False)
    definitions = load_relevance_definitions()
    runs = _original_runs()
    candidates = ep.scan_candidates(runs, definitions, a9_fixtures_path=Path(args.a9_fixtures))
    selection = ep.select_sample(candidates)
    manifest = ep.build_manifest(selection, definitions, pool_runs=[r.name for r in runs])
    unique = {c.key: c for c in candidates}
    pool = {"original_runs": len(runs), "matched_pairs": len(candidates), "unique_pairs": len(unique),
            "pairs_by_alpha": dict(sorted(collections.Counter(c.alpha_id for c in unique.values()).items())),
            "pairs_by_ticker": dict(sorted(collections.Counter(c.ticker for c in unique.values()).items())),
            "availability_unique_pairs": selection.availability, "runs": [r.name for r in runs]}
    manifest_sha = ep.write_json(out / "sample_manifest.json", manifest)
    ep.write_json(out / "candidate_pool_summary.json", pool)
    (out / "coverage_report.md").write_text(_coverage_markdown(manifest, pool), encoding="utf-8")
    rows = [{"sample_id": s["sample_id"], "target_alpha_id": s["target_alpha_id"], "ticker": s["ticker"], "agent": s["agent"],
             "primary_stratum": s["selection"]["primary_stratum"], "all_strata": ";".join(s["selection"]["all_strata"]),
             "source_run_id": s["source_run_id"], "claim_id": s["claim_id"], "claim_text": s["claim_text"]} for s in manifest["samples"]]
    (out / "sample_list.csv").write_text(ep.render_csv(rows, list(rows[0])), encoding="utf-8")
    return {"status": "ok", "samples": manifest["sample_count"], "manifest_file_sha256": manifest_sha, "content_sha256": manifest["content_sha256"],
            "shortfalls": manifest["shortfalls"], "out_dir": str(out)}


def build_review(args: argparse.Namespace) -> dict:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if ep.manifest_content_sha256(manifest) != manifest["content_sha256"]:
        return {"status": "failed", "error_code": "MANIFEST_HASH_MISMATCH"}
    definitions = load_relevance_definitions()
    review, draft = Path(args.out_dir) / "review", Path(args.out_dir) / "engineering_draft"
    review.mkdir(parents=True, exist_ok=False)
    draft.mkdir(parents=True, exist_ok=False)
    rows = ep.blind_review_rows(manifest, definitions)
    sheet = ep.render_csv(rows, ep.REVIEW_COLUMNS)
    for name in ("A", "B"):
        (review / f"blind_review_sheet_{name}.csv").write_text(sheet, encoding="utf-8")
    (review / "review_definitions.md").write_text(ep.render_definitions_markdown(manifest, definitions), encoding="utf-8")
    (review / "README_盲审说明.md").write_text(ep.REVIEW_INSTRUCTIONS, encoding="utf-8")
    drafts = ep.draft_label_rows(manifest, Path(args.a9_fixtures))
    (draft / "engineering_draft_labels_DRAFT.csv").write_text(
        ep.render_csv(drafts, ["sample_id", "engineering_draft_tier", "draft_basis", "draft_source", "status"]), encoding="utf-8")
    return {"status": "ok", "rows": len(rows), "draft_rows_with_a_tier": sum(1 for d in drafts if d["engineering_draft_tier"]),
            "review_dir": str(review), "draft_dir": str(draft)}


def _plan_markdown(plan: dict) -> str:
    est, cost, ref = plan["estimates"]["total"], plan["cost_estimate"], plan["reference"]
    stance = ep.estimate_basis(ref)
    purpose = plan.get("purpose") or {}
    title = ("# Execution plan — development retest of the relevance task (LIVE, not executed)" if purpose.get("kind") == ep.RETEST_PURPOSE_KIND
             else "# Execution plan — small-sample relevance evaluation (LIVE, not executed)")
    lines = [title, "",
             *([f"- purpose ({purpose.get('kind')}): {purpose.get('text')}"] if purpose else []),
             *([f"- experiment configuration: `{plan['experiment_config']}` (the plan runs under this configuration only)"] if plan.get("experiment_config") else []),
             *([f"- pre-registered: `{json.dumps(plan['pre_registered'], ensure_ascii=False)}`"] if plan.get("pre_registered") else []),
             *([f"- sent alone in their own request: {', '.join(plan['isolated_samples'])}"] if plan.get("isolated_samples") else []),
             *([f"- kept in the sample table but NOT sent ({plan['not_sent_count']}): "
                + "; ".join(f"{e['sample_id']} ({e['reason']})" for e in plan["not_sent"])] if plan.get("not_sent") else []),
             f"- plan sha256 `{plan['plan_sha256']}`", f"- sample manifest `{plan['sample_manifest']['content_sha256']}` ({plan['sample_manifest']['sample_count']} pairs)",
             f"- provider / requested model name: **{plan['provider']} / {plan['model']}** (a request name, not a pinned model version: see Model identity)",
             f"- task: `{json.dumps(plan['task'], ensure_ascii=False)}`",
             f"- call settings: {json.dumps(plan['call_settings'], ensure_ascii=False)}", "",
             "## Requests", "", f"- round 1: {plan['requests']['round_1']} batches (every sample once)",
             f"- round 2: {plan['rounds'][1]['purpose']}: "
             + ", ".join(f"{b['batch_id']} = {b['repeats']} ({b['alpha_id']}, {b['pairs']})" for b in plan["requests"]["repeat_batches"]),
             f"- **request cap = {plan['request_cap']}** (repeats included; no retry; a failed batch is never re-sent)", "",
             "| round | batch | Alpha | samples | prompt chars |", "|---|---|---|---|---|"]
    for r in plan["rounds"]:
        for b in r["batches"]:
            lines.append(f"| {r['round']} | {b['batch_id']} | {b['alpha_id']} | {', '.join(b['sample_ids'])} | {b['prompt_chars']} |")
    identity = plan["model_identity"]
    observed = identity.get("observed_in_saved_real_ledgers") or {}
    lines += ["", "## Model identity", "",
              f"- requested name: `{identity['request_model']}` -- {identity['pinning']}",
              f"- vendor's current description of the served model: **{identity['documented_serving_model']['name']}** "
              f"(as of {identity['documented_serving_model']['as_of']}; {identity['documented_serving_model']['source']})",
              f"- earlier vendor note ({identity['earlier_vendor_note']['queried_at']}): {identity['earlier_vendor_note']['text']}",
              "- what the provider returned in the saved real ledgers (call dates " + ", ".join(observed.get("call_dates") or []) + "): "
              + "; ".join(f"requested `{p['requested']}` -> " + (f"returned `{p['returned_by_provider']}`" if p["returned_by_provider"] else "no model field (no response arrived)")
                          + f" x {p['calls']}" for p in observed.get("pairs") or []),
              f"- at execution: {identity['recorded_at_execution']}"]
    basis_line = (f"- this task's own real calls (`{ref['basis_task']}`, prompt versions {json.dumps(ref.get('basis_prompt_versions'))}) on "
                  f"{', '.join(ref['reference_provider_models'])}: {stance['calls']} live calls; excluded {stance.get('excluded')}"
                  if ref.get("basis_kind") else
                  f"- reference task `{ref['reference_task']}` on {', '.join(ref['reference_provider_models'])}: {stance['calls']} live calls")
    lines += ["", "## Basis measured from saved real ledgers", "", basis_line,
              f"- characters per billed input token: {stance['chars_per_input_token']}",
              f"- billed output tokens per item (incl. hidden reasoning): {stance['output_tokens_per_item']}; reasoning share {stance['reasoning_share_of_output']}",
              f"- latency per item (s): {stance['latency_seconds_per_item']}; per call: {stance['latency_seconds_per_call']}",
              f"- max_tokens enforcement: {ref['max_tokens_enforcement']['calls']} capped live calls, {ref['max_tokens_enforcement']['calls_over_cap']} over the cap; "
              f"by cap {json.dumps({k: {'calls': v['calls'], 'max_output': v['max_output_tokens'], 'finish': v['finish_reasons']} for k, v in ref['max_tokens_enforcement']['by_cap'].items()})}",
              "- sources: " + "; ".join(f"`{Path(s['path']).parent.name}/{Path(s['path']).name}` sha256 {s['sha256'][:12]}… ({s['role']})" for s in ref["sources"]), "",
              "## Estimates (all requests)", "", f"Method: {json.dumps(plan['estimate_method'], ensure_ascii=False, indent=1)}", "",
              f"- input tokens: central {est['input_tokens']['central']}, range {est['input_tokens']['low']}–{est['input_tokens']['high']}",
              f"- output tokens: central {est['output_tokens']['central']}, high {est['output_tokens']['high']}, hard bound {est['output_tokens']['hard_bound']}",
              f"- latency: central {round(est['latency_seconds']['central'] / 60, 1)} min, worst case {round(est['latency_seconds']['worst_case'] / 60, 1)} min (sequential)",
              f"- cost (USD): central {cost.get('central_usd')}, high (peak) {cost.get('high_usd_peak')}, hard bound (peak) {cost.get('hard_bound_usd_peak')}",
              f"- prices: {json.dumps(cost.get('prices'), ensure_ascii=False)}", f"- suggested max_cost_usd for the authorization: {ep.suggested_max_cost_usd(plan)}", "",
              "## Unknowns", ""] + [f"- {u}" for u in plan["unknowns"]] + ["", "## Stop conditions", ""] + \
        [f"- {k}: {v}" for k, v in plan["stop_conditions"].items()] + ["", f"## Quality thresholds — {plan['quality_thresholds']['status']}", "",
                                                                        plan["quality_thresholds"]["rule"], ""] + \
        [f"- **{t['id']}** {t['metric']}: {t['comparator'] or ''} {t['value'] if t['value'] is not None else ''} (min n {t['min_n']}) — {t['why']}" for t in plan["quality_thresholds"]["thresholds"]] + \
        ["", plan["quality_thresholds"].get("sample_size_note") or "", ""]
    return "\n".join(lines)


def build_plan(args: argparse.Namespace) -> dict:
    manifest_path = Path(args.manifest)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    if ep.manifest_content_sha256(manifest) != manifest["content_sha256"]:
        return {"status": "failed", "error_code": "MANIFEST_HASH_MISMATCH"}
    out = Path(args.out_dir) / "plan"
    out.mkdir(parents=True, exist_ok=False)
    if args.relevance_ledger:
        reference = ep.measure_relevance_ledgers([Path(p) for p in args.relevance_ledger])
    else:
        reference = ep.measure_reference_ledgers([Path(p) for p in args.stance_ledger], [Path(p) for p in args.cap_ledger])
    pre_registered = None
    if args.pre_registered:
        pre_path = Path(args.pre_registered)
        pre_registered = {"file": pre_path.name, "file_sha256": ep._sha256_bytes(pre_path.read_bytes()),  # noqa: SLF001
                          "note": "frozen before execution: the result is read against this file; it holds engineering expectations, not reference answers"}
    plan = ep.build_plan(manifest, load_relevance_definitions(), manifest_file_sha256=ep._sha256_bytes(raw), reference=reference,  # noqa: SLF001
                         provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL, batch_size=ep.LIVE_BATCH_SIZE, repeat_every=ep.LIVE_REPEAT_EVERY,
                         timeout_seconds=ep.LIVE_TIMEOUT_SECONDS, max_output_tokens=ep.LIVE_MAX_OUTPUT_TOKENS, repo_root=REPO_ROOT,
                         model_identity_note=MODEL_IDENTITY_NOTE,
                         repeat_sample_ids=[s.strip() for s in args.repeat_samples.split(",") if s.strip()] if args.repeat_samples else None,
                         purpose=args.purpose, purpose_kind=args.purpose_kind, experiment_config=args.experiment_config,
                         quality_thresholds=ep.RETEST_THRESHOLDS if args.retest else None, pre_registered=pre_registered,
                         isolate=[s.strip() for s in args.isolate.split(",") if s.strip()] if args.isolate else None,
                         not_sent=json.loads(Path(args.not_sent).read_text(encoding="utf-8")) if args.not_sent else None)
    plan_file_sha = ep.write_json(out / "execution_plan.json", plan)
    ep.write_json(out / "authorization_LIVE_TEMPLATE.json", ep.authorization_template(plan))
    (out / "execution_plan.md").write_text(_plan_markdown(plan), encoding="utf-8")
    return {"status": "ok", "plan_sha256": plan["plan_sha256"], "plan_file_sha256": plan_file_sha, "request_cap": plan["request_cap"],
            "cost_estimate": plan["cost_estimate"], "out_dir": str(out)}


def build_retest_sample(args: argparse.Namespace) -> dict:
    """Session 4 (2026-10-12): the development retest sample -- an exact subset of the existing manifest and of reviewer A's rows."""
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    sheet_path = Path(args.review_a)
    sheet_raw = sheet_path.read_bytes()
    out = Path(args.out_dir) / "retest_sample"
    out.mkdir(parents=True, exist_ok=False)
    try:
        by_id = {s["sample_id"]: s for s in manifest["samples"]}
        repaired = []
        for spec in selection.get("repaired") or []:
            original = by_id[spec["original_sample_id"]]
            run_path = ep._run_path(original["source_run_id"])  # noqa: SLF001
            if run_path is None:
                raise ValueError(f"REPAIR_SOURCE_RUN_MISSING: {spec['original_sample_id']}")
            repaired.append(ep.build_repaired_sample(original, run_path=run_path, source_file=spec["source_file"], json_path=spec["json_path"],
                                                     char_start=spec["char_start"], char_end=spec["char_end"], defect=spec["defect"], method=spec["method"]))
        retest = ep.build_retest_manifest(manifest, selection["samples"], purpose=selection["purpose"], repaired=repaired)
        sheet_text, check = ep.review_sheet_subset(sheet_raw.decode("utf-8-sig"), [s["sample_id"] for s in retest["samples"] if not s.get("repair")])
    except ValueError as exc:
        return {"status": "failed", "error_code": str(exc).split(":", 1)[0], "detail": str(exc)}
    manifest_sha = ep.write_json(out / "retest_manifest.json", retest)
    (out / "reference_A_subset.csv").write_text(sheet_text, encoding="utf-8")
    subset_sha = ep._sha256_bytes((out / "reference_A_subset.csv").read_bytes())  # noqa: SLF001
    rows = [{"sample_id": s["sample_id"], "target_alpha_id": s["target_alpha_id"], "ticker": s["ticker"], "category": s["retest"]["category"],
             "checks": s["retest"]["checks"], "claim_text": s["claim_text"]} for s in retest["samples"]]
    (out / "retest_list.csv").write_text(ep.render_csv(rows, list(rows[0])), encoding="utf-8")
    provenance = {
        "schema": "alpha_relevance_retest_provenance.v1",
        "original_manifest": {"path": str(Path(args.manifest)), "content_sha256": manifest["content_sha256"],
                              "file_sha256": ep._sha256_bytes(Path(args.manifest).read_bytes())},  # noqa: SLF001
        "selection": {"path": str(Path(args.selection)), "file_sha256": ep._sha256_bytes(Path(args.selection).read_bytes())},  # noqa: SLF001
        "reference_sheet": {"path": str(sheet_path), "file_sha256": ep._sha256_bytes(sheet_raw), "subset_file_sha256": subset_sha, **check,  # noqa: SLF001
                            "rule": "the owner's confirmed rows of the retest samples, copied field by field; nothing is changed or filled in"},
        "retest_manifest": {"content_sha256": retest["content_sha256"], "file_sha256": manifest_sha, "sample_count": retest["sample_count"],
                            "categories": retest["retest"]["categories"]},
        "repaired_samples": [{"sample_id": s["sample_id"], "repair": s["repair"],
                              "reference": "none: a repaired sample has no row in reviewer A's sheet until the owner labels it"}
                             for s in retest["samples"] if s.get("repair")],
    }
    ep.write_json(out / "provenance.json", provenance)
    return {"status": "ok", "samples": retest["sample_count"], "categories": retest["retest"]["categories"], "content_sha256": retest["content_sha256"],
            "manifest_file_sha256": manifest_sha, "reference_subset_sha256": subset_sha, "every_field_identical": check["every_field_identical_to_source"],
            "out_dir": str(out)}


def input_quality(args: argparse.Namespace) -> dict:
    """Session 6: the mechanical observations about every sample's text (hints only; nothing is excluded)."""
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rows = ep.input_quality_rows(manifest)
    ep.write_json(Path(args.out), {"schema": "alpha_relevance_input_quality.v1", "sample_manifest_content_sha256": manifest.get("content_sha256"),
                                   "rule": "text_notes are sent to the model as hints of possible incompleteness; report_only_notes are not sent; nothing is excluded",
                                   "rows": rows})
    return {"status": "ok", "samples": len(rows), "with_text_notes": [r["sample_id"] for r in rows if r["text_notes"]],
            "report_only": sum(1 for r in rows if r["report_only_notes"]), "out": str(args.out)}


def evaluate(args: argparse.Namespace) -> dict:
    from comqutor_alpha import alpha_relevance_evaluation as ev  # noqa: PLC0415

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    try:
        report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=args.eval_dir, review_a=args.review_a, review_b=args.review_b)
    except ev.EvaluationInputError as exc:
        return {"status": "failed", "error_code": exc.code}
    ep.write_json(out / "evaluation_report.json", report)
    (out / "evaluation_report.md").write_text(ev.render_markdown(report), encoding="utf-8")
    (out / "per_sample.csv").write_text(ep.render_csv(report["samples"], ev.SAMPLE_TABLE_COLUMNS), encoding="utf-8")
    return {"status": "ok", "test_data": report["test_data"], "totals": {k: v["outcomes"] for k, v in report["totals"].items()},
            "reference_rows": report["reference"]["reference_rows"], "thresholds": report["thresholds"]["status"], "out_dir": str(out)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build-sample")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--a9-fixtures", default=str(A9_FIXTURES))
    p = sub.add_parser("build-review")
    p.add_argument("--manifest", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--a9-fixtures", default=str(A9_FIXTURES))
    p = sub.add_parser("build-plan")
    p.add_argument("--manifest", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--stance-ledger", action="append", default=None)
    p.add_argument("--cap-ledger", action="append", default=None)
    p.add_argument("--relevance-ledger", action="append", default=None)
    p.add_argument("--repeat-samples", default=None)
    p.add_argument("--purpose", default=None)
    p.add_argument("--purpose-kind", default=None)
    p.add_argument("--experiment-config", default=None)
    p.add_argument("--retest", action="store_true")
    p.add_argument("--pre-registered", default=None)
    p.add_argument("--isolate", default=None, help="comma-separated sample ids sent alone in their own request")
    p.add_argument("--not-sent", default=None, help="JSON file: [{sample_id, reason, evidence}] kept in the plan's table, never sent")
    p = sub.add_parser("input-quality")
    p.add_argument("--manifest", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("build-retest-sample")
    p.add_argument("--manifest", required=True)
    p.add_argument("--selection", required=True)
    p.add_argument("--review-a", required=True)
    p.add_argument("--out-dir", required=True)
    p = sub.add_parser("evaluate")
    p.add_argument("--manifest", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--review-a", required=True)
    p.add_argument("--review-b", default=None)
    p.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    if args.command == "build-plan":
        args.stance_ledger = args.stance_ledger or [str(p) for p in STANCE_LEDGERS]
        args.cap_ledger = args.cap_ledger or [str(p) for p in CAP_LEDGERS]
    result = {"build-sample": build_sample, "build-review": build_review, "build-plan": build_plan, "build-retest-sample": build_retest_sample,
              "input-quality": input_quality, "evaluate": evaluate}[args.command](args)
    print(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
