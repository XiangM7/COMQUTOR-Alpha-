#!/usr/bin/env python3
"""T4 delivery (round 31): identity and configuration record of one run, from its OWN saved files only (standard library).

Reads the run directory (metadata.json incl. run_environment, the semantic ledger, the research-agent call log, source registry,
market snapshot, formal_acceptance.json, week2_gateway_budget.json) plus the package's code snapshot and run records. Writes one
JSON. Values the run did not record are written "未记录"; nothing is filled in from today's code or environment.

    python3 tools/build_run_identity.py --run-dir runs/<run_id> --records run_records/<dir> --out run_records/<dir>/identity_and_config.json
"""
from __future__ import annotations

import argparse
import hashlib

import json
import tarfile
from collections import Counter
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
NR = "未记录"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []


def untracked_identity_from_snapshot(tar_path: Path, files_list: Path) -> dict:
    """Recompute comqutor_alpha.run_environment's untracked identity (sha256 over 'path\\0sha256(file)\\n', sorted paths) from
    the saved tarball, without the repository."""
    entries = [x.split("  ", 1) for x in files_list.read_text(encoding="utf-8").splitlines() if x.strip()]  # "<sha256>  <path>"
    listed_sha = {path: digest for digest, path in entries if "__pycache__" not in path}
    listed = sorted(listed_sha)
    contents = {}
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile():
                contents[member.name.removeprefix("./")] = tar.extractfile(member).read()
    missing = [p for p in listed if p not in contents]
    mismatched = [p for p in listed if p in contents and hashlib.sha256(contents[p]).hexdigest() != listed_sha[p]]
    listing = "".join(f"{p}\0{hashlib.sha256(contents[p]).hexdigest()}\n" for p in listed if p in contents)
    return {"files_listed": len(listed), "files_in_tar": len(contents), "missing_from_tar": missing, "listed_sha_mismatch": mismatched,
            "recomputed_untracked_runtime_source_sha256": hashlib.sha256(listing.encode("utf-8")).hexdigest()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--records", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    d, rec = Path(args.run_dir), Path(args.records)
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
    env = meta.get("run_environment") or {}
    code = env.get("code_identity") or {}
    ledger = jl(d / "llm_semantic_calls.jsonl")
    agent_calls = jl(d / "tradingagents_llm_calls.jsonl")
    sources = json.loads((d / "source_registry.json").read_text(encoding="utf-8"))["sources"]
    market = json.loads((d / "market_data_snapshot.json").read_text(encoding="utf-8"))
    formal = json.loads((d / "formal_acceptance.json").read_text(encoding="utf-8"))
    budget = json.loads((d / "week2_gateway_budget.json").read_text(encoding="utf-8")) if (d / "week2_gateway_budget.json").is_file() else None
    response = json.loads((rec / "research_response.json").read_text(encoding="utf-8"))
    db_check_path = next((rec / n for n in ("verification_result.json", "db_export_status_check.json") if (rec / n).is_file()), None)
    db_check = json.loads(db_check_path.read_text(encoding="utf-8")) if db_check_path else {}

    snap = PKG / "code_identity"
    diff_sha = sha(snap / "tracked_diff_vs_HEAD.diff")
    untracked = untracked_identity_from_snapshot(snap / "untracked_runtime_source.tar.gz", snap / "untracked_runtime_source_files.txt")

    prompts = Counter((r["task"], r.get("prompt_version"), r.get("prompt_sha256"), r.get("input_schema_version"), r.get("output_schema_version"),
                       r.get("taxonomy_version"), r.get("provider"), r.get("model")) for r in ledger)
    published = sorted(s["published_at"] for s in sources if s.get("published_at"))
    retrieved = sorted(s["retrieved_at"] for s in sources if s.get("retrieved_at"))
    rows = market.get("rows") or []
    rules = formal.get("effective_rules") or {}

    doc = {
        "schema": "t4.round31.run_identity.v1",
        "run_id": meta["run_id"],
        "ticker": meta.get("ticker"),
        "analysis_date": meta.get("analysis_date"),
        "started_by": "项目负责人 Xiang Mao 在 http://127.0.0.1:5177/research 网页亲自点击 Start Research（负责人陈述；8002 日志中每次一个 POST /api/research）；没有启动录像",
        "status": {"final_status_api": response.get("status"), "alpha_classification_status": response.get("alpha_classification_status"),
                   "completion": response.get("alpha_classification_completion"), "summary_text": response.get("summary"),
                   "db_record": db_check.get("db") or {k: db_check.get(k) for k in ("db_status", "db_row") if k in db_check} or NR,
                   "status_source": f"{rec.name}/research_response.json (GET /api/research/{{run_id}} after the run) and {db_check_path.name if db_check_path else NR}"},
        "code": {
            "git_head": code.get("git_head", NR),
            "committed": False,
            "uncommitted_changes": code.get("uncommitted_changes", NR),
            "tracked_diff_sha256_recorded_by_run": code.get("tracked_diff_sha256", NR),
            "untracked_runtime_source_sha256_recorded_by_run": code.get("untracked_runtime_source_sha256", NR),
            "untracked_runtime_source_files_recorded_by_run": code.get("untracked_runtime_source_files", NR),
            "computed_at": code.get("computed_at", NR),
            "snapshot_in_package": {
                "tracked_diff": "code_identity/tracked_diff_vs_HEAD.diff", "tracked_diff_file_sha256": diff_sha,
                "tracked_diff_matches_run": diff_sha == code.get("tracked_diff_sha256"),
                "untracked_tar": "code_identity/untracked_runtime_source.tar.gz", **untracked,
                "untracked_matches_run": untracked["recomputed_untracked_runtime_source_sha256"] == code.get("untracked_runtime_source_sha256"),
                "taken_at": "Round 28 re-freeze (2026-10-09 ~00:47Z), docs/audit_artifacts/round_source_linking_t0_t2/round28_t4_launch_protection_20261008/04_refreeze/code_snapshot/",
            },
            "statement": "代码 = git HEAD 7a9aefa + 未提交的完整 tracked diff + 未跟踪运行源码快照；没有提交，不能称为已提交版本",
        },
        "execution_type": env.get("execution_type", NR),
        "database": env.get("database", NR),
        "effective_config_recorded_by_run": env.get("effective_config", NR),
        "config_notes": {
            "structured_adapter_and_structure_extractor_timeout": "共享 45 s（effective_config.week2_semantic.shared_timeout_seconds_other_tasks），没有单独的 profile 设置",
            "retries": "两层都是 0：research_agents.max_retries=0；Week 2 gateway_max_retries=0，每个任务 application_retries=0、sdk_retries=0",
            "week2_cap": "1800 次网关预算占用（不是 HTTP 请求数）",
            "frozen_config": "code_identity/frozen_config.json（Round 28 冻结，sha256 见 manifest）",
        },
        "models_and_prompts": {
            "research_agents": {"calls": len(agent_calls), "provider_model_as_logged": dict(Counter(f"{c.get('provider')}|{c.get('model')}" for c in agent_calls)),
                                "provider_note": "调用日志的 provider 字段记为 openai：LangChain 对 DeepSeek 的 OpenAI 兼容客户端的标记；模型名 deepseek-v4-flash，effective_config 记 provider=deepseek",
                                "prompt_hash": "未记录（研究 Agent 层的调用日志没有 prompt 哈希）",
                                "profile": (env.get("effective_config") or {}).get("research_agents", NR)},
            "week2_semantic_by_task": [{"task": k[0], "prompt_version": k[1], "prompt_sha256": k[2], "input_schema_version": k[3], "output_schema_version": k[4],
                                        "taxonomy_version": k[5], "provider": k[6], "model": k[7], "logical_calls": n} for k, n in sorted(prompts.items())],
        },
        "inputs": {
            "raw_agent_outputs_sha256": sha(d / "raw_agent_outputs.json"),
            "source_registry_sha256": sha(d / "source_registry.json"),
            "market_data_snapshot_sha256": sha(d / "market_data_snapshot.json"),
            "derived_inputs_sha256": sha(d / "derived_inputs.json"),
            "sources": {"count": len(sources), "by_type": dict(Counter(s.get("source_type") for s in sources)),
                        "with_content_hash": sum(1 for s in sources if s.get("content_hash")), "metadata_status": dict(Counter(s.get("metadata_status") for s in sources))},
            "agents": meta.get("agents"), "selected_analysts": meta.get("selected_analysts"),
        },
        "evidence_cutoff": {
            "recorded_field": "未记录（运行没有专门的证据截止字段）",
            "derived_from_saved_files": {
                "analysis_date": meta.get("analysis_date"),
                "news_published_at_range": [published[0], published[-1]] if published else NR,
                "sources_retrieved_at_range": [retrieved[0], retrieved[-1]] if retrieved else NR,
                "market_snapshot": {"provider": market.get("provider"), "provider_version": market.get("provider_version"), "retrieved_at": market.get("retrieved_at"),
                                    "query": market.get("query"), "last_row_date": rows[-1].get("date") if rows else NR, "rows": len(rows)},
            },
            "note": "以上是从已保存文件推出的范围，不是运行记录的截止参数",
        },
        "rules_and_versions": {
            "formal_status": formal.get("formal_status"),
            "acceptance_engine": rules.get("schema_version"),
            "gold_contract": rules.get("gold_contract"), "taxonomy": rules.get("taxonomy"), "label_v2": rules.get("label_v2"), "label_v1": rules.get("label_v1"),
            "source": "runs/<run_id>/formal_acceptance.json（运行时写入的哈希）",
        },
        "week2_gateway_budget": budget or NR,
        "dependency_versions": "未记录（运行时没有记录依赖版本；不用今天的环境补填）",
        "artifacts": {
            "results_dir_original": f"outputs/t4_runs/{meta['run_id']}/（仓库相对路径；本包 runs/{meta['run_id']}/ 是逐字节副本）",
            "call_logs": {"research_agents": f"runs/{meta['run_id']}/tradingagents_llm_calls.jsonl",
                          "week2_ledger": f"runs/{meta['run_id']}/llm_semantic_calls.jsonl",
                          "week2_wire_audit_requests": f"runs/{meta['run_id']}/error_logs/week2_llm_provider_request_audit.jsonl",
                          "week2_wire_audit_responses": f"runs/{meta['run_id']}/error_logs/week2_llm_provider_response_audit.jsonl",
                          "usage_report": f"runs/{meta['run_id']}/llm_usage_report.json"},
            "api_export_zip": {"path": f"{rec.name}/api_export.zip", "sha256": sha(rec / "api_export.zip")},
            "page_download_export_zip": {"path": f"{rec.name}/page_download_export.zip", "sha256": sha(rec / "page_download_export.zip")},
        },
    }
    Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": doc["run_id"], "status": doc["status"]["final_status_api"],
                      "tracked_match": doc["code"]["snapshot_in_package"]["tracked_diff_matches_run"],
                      "untracked_match": doc["code"]["snapshot_in_package"]["untracked_matches_run"],
                      "missing_from_tar": untracked["missing_from_tar"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
