#!/usr/bin/env python3
"""The conflict-pair defect, reproduced on identical inputs by the Round 23 engine and the Round 24 engine.

Inputs are SYNTHETIC and labelled: hand-built activation entries and claims run through the REAL conflict detector and the REAL B2 gate (tests/fixtures), plus one
CONTROLLED MODIFICATION (a record B2 cannot produce). Each case's arbitration payload is judged by both engines' ``evaluate_must_detect_if_evidence_present``.
Everything is in-process and offline (a network trap counts attempts); nothing is written except the two output files.

    python repro_before_after.py --round23-engine <round23 acceptance_engine.py> --out-dir <new dir>
"""
import argparse
import importlib.util
import json
import socket
import sys
import urllib.request
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

attempts = []


def _refuse(name):
    def stub(*_a, **_k):
        attempts.append(name)
        raise RuntimeError("network attempted: " + name)

    return stub


socket.socket.connect = _refuse("connect")
socket.create_connection = _refuse("create_connection")
socket.getaddrinfo = _refuse("getaddrinfo")
urllib.request.urlopen = _refuse("urlopen")

from comqutor_alpha.alpha_library.alpha_schema import ConflictAlpha  # noqa: E402
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts  # noqa: E402
from comqutor_alpha.regression import acceptance_engine as new_engine  # noqa: E402
from tests.fixtures.week4_conflict_cases import (  # noqa: E402
    activation_entry,
    activation_payload,
    fake_alpha,
)

TAXONOMY = {
    "A": fake_alpha("A", [ConflictAlpha(alpha_id="B", contradiction_weight=0.9)]),
    "B": fake_alpha("B", [ConflictAlpha(alpha_id="A", contradiction_weight=0.9)]),
}
A_SUPPORT = [("a1", "NVDA strong datacenter demand signal one."), ("a2", "NVDA new supply agreement signal two.")]
B_SUPPORT = [("b1", "NVDA strong valuation risk signal one."), ("b2", "NVDA margin compression signal two.")]
A_NOT_TICKER = [("a1", "Strong datacenter demand signal one."), ("a2", "New supply agreement signal two.")]


def claim(cid, alpha, text):
    return {
        "claim_id": cid, "source_agent_output_id": f"o_{cid}", "agent": "market_agent", "match_status": "matched", "matched_alpha": alpha, "matched_alpha_name": alpha,
        "score": 0.8, "direction": "positive", "assertion_status": "asserted", "semantic_polarity": "activation", "claim": text, "evidence": text, "reason": "fixture",
        "plausible_alphas": [], "candidate_scores": [{"alpha_id": alpha, "score": 0.8, "relation": "activation", "evidence_stance": "supports_alpha"}],
        "claim_quality": "analytical", "factors": [],
    }


def detect(a_entry, b_entry, a_sup, b_sup):
    entries = [e for e in (a_entry, b_entry) if e is not None]
    matches = [claim(c, "A", t) for c, t in a_sup] + [claim(c, "B", t) for c, t in b_sup]
    return detect_alpha_conflicts(run_id="repro", ticker="NVDA", activation_payload=activation_payload(*entries), alpha_matches=matches, taxonomy=TAXONOMY)


def hand_edit_to_omission(payload):
    (entry,) = payload["arbitration"]["candidate_evaluations"]
    entry["outcome"], entry["reason_codes"] = "suppressed", []
    entry["admissibility"]["status"], entry["admissibility"]["reason_codes"] = "candidate", []
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--round23-engine", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        print("refusing: output directory is not empty", file=sys.stderr)
        return 2
    spec = importlib.util.spec_from_file_location("acceptance_engine_round23", args.round23_engine)
    old_engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old_engine
    spec.loader.exec_module(old_engine)

    a_ok, b_ok = activation_entry("A", score=80.0, direction="positive"), activation_entry("B", score=80.0, direction="negative")
    cases = [
        ("control: every B2 condition met (2 ticker-specific facts per side, scores 80/80, both active)", "real detector + real B2", detect(a_ok, b_ok, A_SUPPORT, B_SUPPORT)),
        ("A1: Alpha A never identified (no activation entry), its two supporting claims still in alpha_matches", "real detector + real B2", detect(None, b_ok, A_SUPPORT, B_SUPPORT)),
        ("A2: Alpha A present but capped_active (not an official detected level)", "real detector + real B2", detect(activation_entry("A", score=60.0, status="capped_active"), b_ok, A_SUPPORT, B_SUPPORT)),
        ("B: exactly ONE supporting fact per side (scores 80/80, ticker-specific)", "real detector + real B2", detect(a_ok, b_ok, A_SUPPORT[:1], B_SUPPORT[:1])),
        ("B': two facts per side, none of A's ticker-specific", "real detector + real B2", detect(a_ok, b_ok, A_NOT_TICKER, B_SUPPORT)),
        ("B'': two facts per side, Alpha A score 40 (< 50)", "real detector + real B2", detect(activation_entry("A", score=40.0, status="candidate"), b_ok, A_SUPPORT, B_SUPPORT)),
        ("C: no supporting evidence at all, both Alphas active", "real detector + real B2", detect(a_ok, b_ok, [], [])),
        ("D: the control record hand-edited to 'candidate, no reason' (B2 cannot produce it)", "CONTROLLED MODIFICATION", hand_edit_to_omission(detect(a_ok, b_ok, A_SUPPORT, B_SUPPORT))),
    ]
    rows = []
    for name, fixture, payload in cases:
        lookup_old = old_engine.pair_admissibility_lookup(payload)
        lookup_new = new_engine.pair_admissibility_lookup(payload)
        (before,) = old_engine.evaluate_must_detect_if_evidence_present(ticker_v2_label={"required_conflicts": ["A__B"]}, admissibility_lookup=lookup_old)
        (after,) = new_engine.evaluate_must_detect_if_evidence_present(
            ticker_v2_label={"required_conflicts": ["A__B"]}, admissibility_lookup=lookup_new, declared_pair_count=payload["arbitration"]["declared_pair_count"]
        )
        raw = payload["arbitration"]["candidate_evaluations"][0]
        adm = raw.get("admissibility") or {}
        rows.append(
            {
                "case": name,
                "fixture": fixture,
                "what_the_run_recorded": {
                    "outcome": raw["outcome"],
                    "detector_reasons": raw.get("reason_codes"),
                    "has_b2_block": bool(adm),
                    "b2_status": adm.get("status"),
                    "b2_reasons": adm.get("reason_codes"),
                    "supports_bull_bear": [adm.get("bull_supporting_evidence_count"), adm.get("bear_supporting_evidence_count")],
                    "ticker_specific_bull_bear": [adm.get("bull_ticker_specific_support_count"), adm.get("bear_ticker_specific_support_count")],
                    "scores_bull_bear": [adm.get("bull_score"), adm.get("bear_score")],
                    "evidence_audit_qualifying_claims": {k: (raw.get("evidence_audit") or {}).get(k, {}).get("qualifying_count") for k in ("alpha_a", "alpha_b")},
                },
                "round23_verdict": before["verdict"],
                "round23_detail": before["detail"],
                "round24_verdict": after["verdict"],
                "round24_state": after["state"],
                "round24_detail": after["detail"],
            }
        )
    doc = {"network_attempts": len(attempts), "provider_calls": 0, "cases": rows}
    out.mkdir(parents=True, exist_ok=True)
    (out / "repro_before_after.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = [
        "# The conflict-pair defect on identical inputs: Round 23 engine vs Round 24 engine",
        "",
        f"Provider calls 0; network attempts {len(attempts)}. Inputs are synthetic (real detector + real B2 on hand-built activation entries and claims) except case D, a labelled controlled modification.",
        "",
        "| Case | Fixture | What the run recorded | Round 23 | Round 24 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        w = r["what_the_run_recorded"]
        recorded = f"outcome {w['outcome']}; " + (
            f"B2 {w['b2_status']} {w['b2_reasons'] or '[]'}, supports {w['supports_bull_bear']}, ticker-specific {w['ticker_specific_bull_bear']}, scores {w['scores_bull_bear']}"
            if w["has_b2_block"]
            else f"no B2 block; detector reasons {w['detector_reasons']}; qualifying claims in its own evidence audit {w['evidence_audit_qualifying_claims']}"
        )
        md.append(f"| {r['case']} | {r['fixture']} | {recorded} | **{r['round23_verdict']}** | **{r['round24_verdict']}** ({r['round24_state']}) |".replace("\n", " "))
    md += ["", "Reading: in Round 23 the FAIL fell on B2's correct rejections (B, B', B'') and the cases where the pair was never judged (A1, A2) were waved through as `not_applicable`; case D, the only record that is a real omission, got the same FAIL as the correct rejections. In Round 24 each situation has its own result.", ""]
    (out / "repro_before_after.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps([(r["case"][:3], r["round23_verdict"], r["round24_verdict"]) for r in rows]), "| network attempts", len(attempts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
