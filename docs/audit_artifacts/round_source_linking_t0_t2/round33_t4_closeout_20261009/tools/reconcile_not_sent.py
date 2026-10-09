#!/usr/bin/env python3
"""T4 round 33 (2026-10-09): reconcile "6 refused / 5 corrected" for the second NVDA Fresh run, from saved records only.

Reads (never writes) the run's semantic ledger, gateway budget, wire audits and structured_agent_outputs.json; the Round 32
final-code replay execution (same saved replies, final code) for the corrected labels; and the summary statements of the
Round 30 / 31 / 32 reports, each quoted verbatim and checked against the records. Standard library only, zero network.

    python3 tools/reconcile_not_sent.py --out-json 03_not_sent_reconcile/reconcile.json --out-md 03_not_sent_reconcile/对账.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
RUN_ID = "12591384-0b26-470d-a99d-a49c00be440b"
RUN = REPO / "outputs" / "t4_runs" / RUN_ID
REPLAY_ID = "t4r32-replay-20261009T202841Z-12f19149"
REPLAY = REPO / "outputs" / "t4_r32_verify_runs" / REPLAY_ID
LIMIT = 60000
DOCS = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
# (file, verbatim quote, what the records say, verdict) -- the verdict is recomputed below from the records, not trusted
STATEMENTS = [
    ("round30_t4_nvda_fresh_run2_20261009/FRESH_RUN2_REPORT.md", "`malformed_response` 8 条（其中 5 条是因输入超长而没有发送）", "labels_total_8_of_which_not_sent_5"),
    ("round30_t4_nvda_fresh_run2_20261009/FRESH_RUN2_REPORT.md", "6 个请求超过 60,000 字符没有发送；内容核验仍把这种情况标为 `malformed_response`", "refused_6_cs_labels_malformed"),
    ("round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md", "6 个请求因输入过大没有发送", "refused_6"),
    ("round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md", "6 个请求输入超限，且被标成 `malformed_response`", "all_6_labelled_malformed"),
    ("round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md", "5 条输入超限没有发送", "cs_refused_5"),
    ("round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md", "**未发送**：6 次输入超限（内容核验 5、适配器 1）", "refused_6_split_5_1"),
    ("round31_t4_delivery_20261009/T4_delivery/00_T4交付主报告.md", "10 条没有发出请求：5 条确定性核对、5 条输入超限", "cs_refused_5"),
    ("round32_t4_closure_20261009/T4_final/00_T4最终交付报告.md", "| 第二次 Fresh | 6（内容核验 5、适配器 1） | 5 |", "refused_6_split_5_1_mislabelled_5"),
    ("round32_t4_closure_20261009/T4_final/00_T4最终交付报告.md", "5 条从未发送的内容核验，原因由 `malformed_response` 改为 `input_too_large`；6 条账本记录新增 `error_message`", "corrected_5_ledger_messages_6"),
    ("round32_t4_closure_20261009/T4_final/03_not_sent/未发送记录修复说明.md", "6 个未发送请求（内容核验 5、适配器 1），其中 5 个被误标为 `malformed_response`", "refused_6_split_5_1_mislabelled_5"),
    ("round32_t4_closure_20261009/T4_final/05_stage_disclosure/结构抽取与降级披露.md", "| claim_enrichment | model_not_used | 7 次超时、1 次未发送、1 次回复未被接受 |", "adapter_refused_1"),
    ("round32_t4_closure_20261009/T4_final/05_stage_disclosure/结构抽取与降级披露.md", "185 被采用；48 引文找不到；3 格式不合格；5 未发送", "cs_refused_5"),
]


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _size(payload) -> int:
    return len(json.dumps(payload, ensure_ascii=False, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args(argv)

    ledger = _jsonl(RUN / "llm_semantic_calls.jsonl")
    budget = json.loads((RUN / "week2_gateway_budget.json").read_text(encoding="utf-8"))
    requests = _jsonl(RUN / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    replies = _jsonl(RUN / "error_logs" / "week2_llm_provider_response_audit.jsonl")
    records = json.loads((RUN / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    by_claim = {r["claim_id"]: r for r in records["records"]}
    replay_ledger = {r["call_sequence"]: r for r in _jsonl(REPLAY / "llm_semantic_calls.jsonl")}
    replay_records = {r["claim_id"].split(":", 1)[1]: r for r in json.loads((REPLAY / "structured_agent_outputs.json").read_text(encoding="utf-8"))["records"]}

    def is_cache_hit(r):
        return isinstance(r.get("cache"), dict) and r["cache"].get("hit") is True

    attempts = sum(len(r.get("request_attempts") or []) for r in ledger)
    refused = [r for r in ledger if r["provider_status"] == "not_called" and r.get("error_code") == "WEEK2_LLM_INPUT_TOO_LARGE"]
    cache_hits = [r for r in ledger if r["provider_status"] == "not_called" and is_cache_hit(r)]
    sent = [r for r in ledger if r.get("request_attempts")]
    send_ledger = {
        "ledger_records": len(ledger),
        "sent_with_http_attempt": len(sent),
        "http_attempts": attempts,
        "gateway_budget_reservations": budget["budget_reservations"],
        "wire_audit_request_rows": len(requests),
        "wire_audit_reply_rows": len(replies),
        "same_run_cache_hits_not_sent": len(cache_hits),
        "cache_hits_by_task": Counter(r["task"] for r in cache_hits),
        "refused_locally_input_too_large": len(refused),
        "refused_by_task": Counter(r["task"] for r in refused),
        "other_not_sent": len(ledger) - len(sent) - len(cache_hits) - len(refused),
        "identity": f"{len(ledger)} = {len(sent)} sent + {len(cache_hits)} cache hits + {len(refused)} refused",
    }
    send_ledger["balances"] = (len(ledger) == len(sent) + len(cache_hits) + len(refused) and attempts == budget["budget_reservations"] == len(requests))

    rows = []
    for r in sorted(refused, key=lambda x: x["call_sequence"]):
        payload = r["input_payload"]
        row = {
            "task": r["task"],
            "call_sequence": r["call_sequence"],
            "call_id": r["call_id"],
            "attempt_id": None,
            "request_attempts": len(r.get("request_attempts") or []),
            "input_chars": _size(payload),
            "over_limit_by": _size(payload) - LIMIT,
            "send_status": "not sent (refused locally before budget reservation and HTTP)",
            "wire_audit_request_row": any(q.get("semantic_call_id") == r["call_id"] for q in requests),
            "saved_ledger_reason": r.get("fallback_reason"),
            "final_code_ledger_reason": replay_ledger[r["call_sequence"]].get("fallback_reason"),
            "final_code_ledger_error_message": replay_ledger[r["call_sequence"]].get("error_message"),
        }
        if r["task"] == "content_support_verification":
            claim_id = payload["items"][0]["claim_id"]
            rec = by_claim[claim_id]
            after = replay_records[claim_id.split(":", 1)[1]]
            row.update({
                "unit": "claim", "claim_id": claim_id, "result_records": 1,
                "saved_claim_label": rec.get("content_support_llm_fallback_reason"),
                "saved_claim_status": rec.get("content_support_status"),
                "final_code_claim_label": after.get("content_support_llm_fallback_reason"),
                "final_code_claim_status": after.get("content_support_status"),
            })
        else:
            row.update({
                "unit": "batch", "agent": payload["agent"], "segments": len(payload["segments"]), "result_records": 0,
                "saved_claim_label": None,
                "note": "the adapter writes no per-claim reason; its 64 segments were enriched deterministically like every other "
                        "batch (structured_agent_outputs.metadata.llm_batch_fallback_count = 9); its ledger reason was already the "
                        "correct WEEK2_LLM_INPUT_TOO_LARGE",
            })
        rows.append(row)

    labels_saved = Counter(r.get("content_support_llm_fallback_reason") for r in records["records"] if r.get("content_support_llm_fallback_reason"))
    labels_final = Counter(r.get("content_support_llm_fallback_reason") for r in replay_records.values() if r.get("content_support_llm_fallback_reason"))
    real_malformed = [r["call_sequence"] for r in ledger if r.get("fallback_reason") == "malformed_response" and r["provider_status"] == "success"]
    facts = {
        "refused": len(rows),
        "refused_cs": sum(1 for x in rows if x["task"] == "content_support_verification"),
        "refused_adapter": sum(1 for x in rows if x["task"] == "structured_adapter"),
        "refused_labelled_malformed": sum(1 for x in rows if x["saved_claim_label"] == "malformed_response" or x["saved_ledger_reason"] == "malformed_response"),
        "claim_labels_malformed_saved": labels_saved.get("malformed_response", 0),
        "real_malformed_replies": len(real_malformed),
        "corrected_to_input_too_large": sum(1 for x in rows if x.get("final_code_claim_label") == "input_too_large"),
        "final_ledger_messages": sum(1 for x in rows if x["final_code_ledger_error_message"]),
    }
    truth = {
        "labels_total_8_of_which_not_sent_5": facts["claim_labels_malformed_saved"] == 8 and facts["refused_cs"] == 5,
        "refused_6_cs_labels_malformed": facts["refused"] == 6 and facts["refused_labelled_malformed"] == facts["refused_cs"],
        "refused_6": facts["refused"] == 6,
        "all_6_labelled_malformed": facts["refused_labelled_malformed"] == 6,
        "cs_refused_5": facts["refused_cs"] == 5,
        "refused_6_split_5_1": (facts["refused"], facts["refused_cs"], facts["refused_adapter"]) == (6, 5, 1),
        "refused_6_split_5_1_mislabelled_5": (facts["refused"], facts["refused_cs"], facts["refused_adapter"], facts["refused_labelled_malformed"]) == (6, 5, 1, 5),
        "corrected_5_ledger_messages_6": facts["corrected_to_input_too_large"] == 5 and facts["final_ledger_messages"] == 6,
        "adapter_refused_1": facts["refused_adapter"] == 1,
    }
    statements = []
    for rel, quote, key in STATEMENTS:
        text = (DOCS / rel).read_text(encoding="utf-8")
        statements.append({"file": rel, "quote": quote, "quote_found_verbatim": quote in text, "consistent_with_records": truth[key]})

    doc = {
        "run_id": RUN_ID, "final_code_replay_execution": REPLAY_ID, "limit_chars": LIMIT,
        "send_ledger": send_ledger, "refused_requests": rows, "facts": facts,
        "claim_labels": {"saved": labels_saved, "final_code": labels_final, "real_malformed_reply_call_sequences": real_malformed},
        "statements": statements,
        "answer": "6 refusal events = 6 ledger call records. 5 are content-support calls, one claim each; those 5 claim result records "
                  "carried malformed_response and are the 5 corrections (input_too_large in the final code). The 6th is one adapter "
                  "batch of 64 segments: no per-claim result record carries its reason, and its ledger reason was already "
                  "WEEK2_LLM_INPUT_TOO_LARGE, so nothing was missed. One summary is wrong: the Round 31 main report says all 6 were "
                  "labelled malformed_response; 5 were.",
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=dict) + "\n", encoding="utf-8")

    md = ["# 第二次 Fresh：超长输入“6 次拒绝／5 条更正”对账", "",
          f"run `{RUN_ID}`；只读保存记录。更正后的标签取自 Round 32 用最终代码消费同一批保存回复的派生执行 `{REPLAY_ID}`。由 `tools/reconcile_not_sent.py` 生成。", "",
          "## 1. 发送总账", "",
          f"- 账本 {send_ledger['ledger_records']} 条 = 实际发送 {send_ledger['sent_with_http_attempt']} + 同 run 缓存命中 {send_ledger['same_run_cache_hits_not_sent']}（Alpha 分类，复用先前答案，未发送）+ 本地拒绝 {send_ledger['refused_locally_input_too_large']}；其他未发送 {send_ledger['other_not_sent']}。",
          f"- HTTP 尝试 {send_ledger['http_attempts']} = 网关预算占用 {send_ledger['gateway_budget_reservations']} = 线路审计请求行 {send_ledger['wire_audit_request_rows']}。回复行 {send_ledger['wire_audit_reply_rows']}，差的 6 行是没有回复的超时（与“6 次拒绝”无关）。",
          f"- 平衡：{'是' if send_ledger['balances'] else '**否**'}。", "",
          "## 2. 6 次本地拒绝逐条", "",
          "| # | task | claim / batch | call_sequence | call_id | attempt_id | 输入字符（上限 60,000） | 发送状态 | 保存的原因 | 对应结果记录 | 最终代码的原因 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(rows, 1):
        unit = f"claim `{x['claim_id'].split(':', 1)[1]}`" if x["unit"] == "claim" else f"批次：{x['agent']}，{x['segments']} 段"
        saved = f"账本 `{x['saved_ledger_reason']}`" + (f"；claim `{x['saved_claim_label']}`（{x['saved_claim_status']}）" if x["unit"] == "claim" else "；claim 上不记原因")
        result = "1 条 claim 记录" if x["unit"] == "claim" else "0 条（64 段走确定性抽取）"
        after = (f"claim `{x['final_code_claim_label']}`（{x['final_code_claim_status']}）" if x["unit"] == "claim" else f"账本 `{x['final_code_ledger_reason']}`（不变）") + "；账本写入实际字符数"
        md.append(f"| {i} | {x['task']} | {unit} | {x['call_sequence']} | `{x['call_id'].rsplit(':', 1)[1][:12]}…` | 无（未发送） | {x['input_chars']:,}（超 {x['over_limit_by']:,}） | 未发送 | {saved} | {result} | {after} |")
    md += ["", "## 3. 结论", "",
           f"- **6 次事件对应 6 条账本调用记录，其中 5 条对应 5 条 claim 结果记录**：内容核验每次只核验 1 条 claim，这 5 条 claim 原标签是 `malformed_response`，最终代码中更正为 `input_too_large`，状态仍是 PENDING_REVIEW。",
           "- **第 6 次是适配器的一批（fundamental_agent，64 段）**：适配器不在 claim 上记原因；账本里的原因原本就是正确的 `WEEK2_LLM_INPUT_TOO_LARGE`，不需要更正。最终代码只给它补了 `error_message`（6 条账本记录都补了）。",
           f"- **更正没有遗漏**。内容核验的 `malformed_response` 标签原来共 {facts['claim_labels_malformed_saved']} 条：5 条未发送，{facts['real_malformed_replies']} 条是模型确实返回了不合格的回复（call_sequence {', '.join(map(str, real_malformed))}），这 3 条在最终代码中仍是 `malformed_response`。",
           "- **有一份摘要写错了**：Round 31 主报告第 1 节写“6 个请求输入超限，且被标成 `malformed_response`”。实际是 6 个未发送，其中 5 个（内容核验）被标成 `malformed_response`，适配器那 1 个的原因一直是 `WEEK2_LLM_INPUT_TOO_LARGE`。Round 31 包是历史文件，不改；更正记在这里。", "",
           "## 4. 各报告原句核对", "", "| 文件 | 原句 | 原句存在 | 与记录一致 |", "|---|---|---|---|"]
    for s in statements:
        md.append(f"| `{s['file']}` | {s['quote'].replace('|', '｜')} | {'是' if s['quote_found_verbatim'] else '**否**'} | {'是' if s['consistent_with_records'] else '**否**'} |")
    md += ["", "文件路径是仓库中 `docs/audit_artifacts/round_source_linking_t0_t2/` 下的位置。在 T4 最终交付包中可以这样查到原文：",
           "- Round 30 报告的原文副本和 Round 31 主报告在 `round32/references/T4_delivery_round31_20261009.zip` 中"
           "（`T4_delivery/run_records/run2_12591384/original_round30_FRESH_RUN2_REPORT.md`、`T4_delivery/00_T4交付主报告.md`）；",
           "- Round 32 的两份说明在 `round32/03_not_sent/` 和 `round32/05_stage_disclosure/` 中；",
           "- Round 32 主报告已被本版报告取代，表中引用的两句已原样并入本版报告第 6 节。", ""]
    Path(args.out_md).write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"send_ledger": send_ledger, "facts": facts, "statements_inconsistent": [s["quote"] for s in statements if not s["consistent_with_records"]],
                      "quotes_missing": [s["quote"] for s in statements if not s["quote_found_verbatim"]]}, ensure_ascii=False, indent=1, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
