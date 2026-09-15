"""v0.1.3 QA Closure, Item 9: offline replay proof.

Proves Section C (Alpha Level Alignment) and Section D (Evidence Polarity)
have real, material effect on real, already-persisted historical
production data -- without a single new Provider or TradingAgents call.
Both tests recompute a downstream stage fresh, using the exact real inputs
already on disk from a run that predates this session's fixes (the Step 11
r2 six-ticker set), and compare against what the OLD, pre-fix persisted
artifact actually shows.

Zero Provider calls, zero TradingAgents calls: every input here is already
on disk from a prior, separately-authorized run.
"""

from __future__ import annotations

import json
from pathlib import Path

from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.alpha_level_classifier import classify_alpha_level

REPO_ROOT = Path(__file__).resolve().parents[1]
MSFT_RUN_DIR = REPO_ROOT / "outputs" / "runs" / "6cd2566d-e0f1-4306-995f-74f39efb21eb"


def test_section_c_a301_real_msft_run_was_incorrectly_active_before_the_fix_now_gates_to_candidate():
    """Real historical MSFT run (predates this session's Section C fix):
    A301 scored 58.8715 with cap_reason_codes containing BOTH
    NO_TICKER_SPECIFIC_EVIDENCE and NO_LOCAL_STRUCTURE_SUPPORT (0 of 16
    unique evidence groups ticker-specific, 0 local structure edges), yet
    the OLD persisted alpha_activations.json shows status="active" -- this
    is a genuine, on-disk instance of John's exact A301 complaint, not a
    synthetic example. Feeding these same real inputs through the CURRENT
    (fixed) classify_alpha_level proves the fix corrects this exact real
    case."""
    activations = json.loads((MSFT_RUN_DIR / "alpha_activations.json").read_text())
    a301 = next(a for a in activations["activation"]["alphas"] if a["alpha_id"] == "A301")

    # The old, pre-fix persisted record: genuinely active, despite lacking
    # both required signals.
    assert a301["status"] == "active"
    assert a301["activation_score"] == 58.8715
    assert set(a301["cap_reason_codes"]) == {"NO_TICKER_SPECIFIC_EVIDENCE", "NO_LOCAL_STRUCTURE_SUPPORT"}
    assert a301["components"]["ticker_specificity"]["ticker_specific_evidence_count"] == 0
    assert a301["components"]["local_structure_support"]["local_edge_count"] == 0

    # Re-classify with the CURRENT code, using the exact same real score and
    # cap reason codes activation_scorer_v2 already computed for this run
    # (activation_scorer_v2 itself was never touched by the Section C fix --
    # only alpha_level_classifier.py's decision logic changed).
    fixed = classify_alpha_level(
        activation_score=a301["activation_score"],
        dominant_cap_reason_codes=a301["cap_reason_codes"],
    ).to_dict()

    assert fixed["target_level"] == "active"  # the raw score still clears ACTIVE_THRESHOLD
    assert fixed["qualified_level"] == "candidate"  # but the fix gates it down
    assert fixed["is_blocked"] is True
    assert list(fixed["blocked_from"]) == ["active"]
    assert fixed["activation_level"] == "candidate"  # what the frontend actually renders
    assert set(fixed["blocked_reason_codes"]) == {"NO_TICKER_SPECIFIC_EVIDENCE", "NO_LOCAL_STRUCTURE_SUPPORT"}


def test_section_d_real_msft_conflicts_drop_misattributed_display_claims_without_changing_the_score():
    """Same real historical MSFT run. Recomputing detect_alpha_conflicts
    with the CURRENT code (Section D's fix) against the exact same real
    activation payload and alpha_matches already on disk reproduces the
    identical admitted conflicts, identical conflict_score, and identical
    main_conflict as the OLD persisted conflicts.json (proving the frozen
    conflict-score formula is untouched) -- while the DISPLAYED bull/bear
    claim counts drop, because claims whose evidence_stance was not
    "supports_alpha" for that side are no longer shown as if they were."""
    activation_payload = json.loads((MSFT_RUN_DIR / "alpha_activations.json").read_text())["activation"]
    alpha_matches = json.loads((MSFT_RUN_DIR / "alpha_matches.json").read_text())["matches"]
    metadata = json.loads((MSFT_RUN_DIR / "metadata.json").read_text())
    old = json.loads((MSFT_RUN_DIR / "conflicts.json").read_text())

    new = detect_alpha_conflicts(
        run_id=metadata["run_id"],
        ticker=metadata["ticker"],
        activation_payload=activation_payload,
        alpha_matches=alpha_matches,
    )

    old_by_id = {c["conflict_id"]: c for c in old.get("conflicts", [])}
    new_by_id = {c["conflict_id"]: c for c in new.get("conflicts", [])}

    # Same admitted conflicts, same main_conflict, same frozen score.
    assert set(new_by_id) == set(old_by_id) == {"A101__A304", "A304__A601"}
    assert new["main_conflict"]["conflict_id"] == old["main_conflict"]["conflict_id"] == "A101__A304"
    for conflict_id in new_by_id:
        assert new_by_id[conflict_id]["conflict_score"] == old_by_id[conflict_id]["conflict_score"]
        assert new_by_id[conflict_id]["bull_raw_claim_count"] == old_by_id[conflict_id]["bull_raw_claim_count"]
        assert new_by_id[conflict_id]["bear_raw_claim_count"] == old_by_id[conflict_id]["bear_raw_claim_count"]

    # But the OLD persisted display claim_ids include claims that should
    # never have counted as that side's evidence -- the fix removes them.
    old_a101_a304_bear = len(old_by_id["A101__A304"]["bear_structure"]["claim_ids"])
    new_a101_a304_bear = len(new_by_id["A101__A304"]["bear_structure"]["claim_ids"])
    assert old_a101_a304_bear == 24
    assert new_a101_a304_bear == 16
    assert new_a101_a304_bear < old_a101_a304_bear

    old_a304_a601_bull = len(old_by_id["A304__A601"]["bull_structure"]["claim_ids"])
    new_a304_a601_bull = len(new_by_id["A304__A601"]["bull_structure"]["claim_ids"])
    old_a304_a601_bear = len(old_by_id["A304__A601"]["bear_structure"]["claim_ids"])
    new_a304_a601_bear = len(new_by_id["A304__A601"]["bear_structure"]["claim_ids"])
    assert old_a304_a601_bull == 24 and new_a304_a601_bull == 15
    assert old_a304_a601_bear == 24 and new_a304_a601_bear == 16
