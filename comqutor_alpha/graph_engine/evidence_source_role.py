"""John's Primary/Secondary Evidence Source-Role Qualification (Step 6).

The ONE centralized source-role authority. Evidence QUALIFICATION for
activation-input purposes only -- this module never changes B1's five
stance labels, never reinterprets them by role, never changes Alpha Mapper
semantic meaning, and never changes any B2/B4 threshold VALUE. It only
answers, for each already-qualifying evidence claim (i.e. a claim that has
already passed the existing eligibility/relation/assertion pipelines in
``evidence_fact_index``/``activation_scorer_v2``/``conflict_detector``),
one further question: should *this* claim, given who produced it, be
allowed to independently count toward activation/conflict evidence
strength?

Design (see docs/audit_artifacts/primary_secondary_evidence_qualification_v0.1.2.1.md
for the full rationale):

* Agent -> role mapping is the single source of truth here (never scattered
  hardcoded agent-name checks in the scoring modules themselves).
* PRIMARY_RESEARCH agents (first-order TradingAgents analysts) qualify
  under the existing rules, unchanged.
* SECONDARY_DECISION_OR_DEBATE agents (bull/bear debate, risk analysts,
  research manager, trader, portfolio manager) default to
  ``activation_eligible=False`` unless the claim is independently
  ticker-specific AND carries the strongest already-existing causal-evidence
  signal (``relation == "activation"`` and ``assertion_status == "asserted"``
  -- the two fields every consumer already uses to gate ALL qualifying
  evidence, reused here rather than inventing a new keyword classifier).
* Any agent name not in either registry is UNKNOWN and always
  ``activation_eligible=False`` -- default-deny, never default-to-PRIMARY.
* Role is never used as a score multiplier (no 1.0/0.5 weighting) -- only
  binary eligibility plus an auditable reason code.
* Nothing is deleted: every member keeps its original fields, plus the four
  additive fields (`source_agent`, `source_role`, `activation_eligible`,
  `activation_qualification_reason`). Secondary evidence remains fully
  visible for audit/explanation/debate-trace/decision-trace/provenance.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

EVIDENCE_SOURCE_ROLE_CONTRACT_VERSION = "evidence_source_role_v1"

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

SOURCE_ROLE_PRIMARY_RESEARCH = "PRIMARY_RESEARCH"
SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE = "SECONDARY_DECISION_OR_DEBATE"
SOURCE_ROLE_UNKNOWN = "UNKNOWN"

# Verified from the real fresh six-ticker persisted source data
# (outputs/runs/_step5a_coverage_{nvda,qqq,msft,sndk,tsm,amd}/alpha_matches.json
# "agent" field) -- not assumed/invented. These are the first-order
# TradingAgents analyst roles (cross-checked against server_execution.py's
# REAL_RUN_ALLOWED_ANALYSTS).
PRIMARY_RESEARCH_AGENTS: frozenset[str] = frozenset(
    {
        "fundamental_agent",
        "market_agent",
        "sentiment_agent",
        "news_agent",
    }
)

# Debate/decision/risk-management agents: they consume and restate Primary
# research, and independently make recommendations, but are not themselves
# first-order ticker-specific factual research.
SECONDARY_DECISION_OR_DEBATE_AGENTS: frozenset[str] = frozenset(
    {
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "portfolio_manager",
        "conservative_risk_analyst",
        "neutral_risk_analyst",
        "aggressive_risk_analyst",
    }
)

# ---------------------------------------------------------------------------
# Reason codes (suggested family; composed additively, never overwriting
# existing fields)
# ---------------------------------------------------------------------------

REASON_PRIMARY_QUALIFIED = "PRIMARY_QUALIFIED"
REASON_PRIMARY_EXISTING_RULE_REJECTED = "PRIMARY_EXISTING_RULE_REJECTED"
REASON_SECONDARY_NOT_INDEPENDENT_EVIDENCE = "SECONDARY_NOT_INDEPENDENT_EVIDENCE"
REASON_SECONDARY_NOT_TICKER_SPECIFIC = "SECONDARY_NOT_TICKER_SPECIFIC"
REASON_SECONDARY_DUPLICATE_OF_PRIMARY = "SECONDARY_DUPLICATE_OF_PRIMARY"
REASON_SECONDARY_CAUSALITY_UNPROVEN = "SECONDARY_CAUSALITY_UNPROVEN"
REASON_SECONDARY_QUALIFIED_CAUSAL_EVIDENCE = "SECONDARY_QUALIFIED_CAUSAL_EVIDENCE"
REASON_UNKNOWN_SOURCE_ROLE = "UNKNOWN_SOURCE_ROLE"

ALL_QUALIFICATION_REASON_CODES = frozenset(
    {
        REASON_PRIMARY_QUALIFIED,
        REASON_PRIMARY_EXISTING_RULE_REJECTED,
        REASON_SECONDARY_NOT_INDEPENDENT_EVIDENCE,
        REASON_SECONDARY_NOT_TICKER_SPECIFIC,
        REASON_SECONDARY_DUPLICATE_OF_PRIMARY,
        REASON_SECONDARY_CAUSALITY_UNPROVEN,
        REASON_SECONDARY_QUALIFIED_CAUSAL_EVIDENCE,
        REASON_UNKNOWN_SOURCE_ROLE,
    }
)

# The strongest already-existing relation/assertion signal combination --
# reused (never re-derived) as the conservative proxy for "safely
# establishable causal evidence" a Secondary claim must clear on its own.
STRONG_CAUSAL_RELATIONS: frozenset[str] = frozenset({"activation"})
STRONG_ASSERTION_STATUSES: frozenset[str] = frozenset({"asserted"})


def source_role_for_agent(agent: str | None) -> str:
    """The single authoritative agent -> role mapping. Unknown/blank/future
    agent names default-deny to UNKNOWN -- never silently treated as
    PRIMARY."""
    name = str(agent or "").strip()
    if name in PRIMARY_RESEARCH_AGENTS:
        return SOURCE_ROLE_PRIMARY_RESEARCH
    if name in SECONDARY_DECISION_OR_DEBATE_AGENTS:
        return SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE
    return SOURCE_ROLE_UNKNOWN


def _is_strong_causal_member(member: Mapping[str, Any]) -> bool:
    relation = str(member.get("relation") or "").strip().lower()
    assertion_status = str(member.get("assertion_status") or "").strip().lower()
    return relation in STRONG_CAUSAL_RELATIONS and assertion_status in STRONG_ASSERTION_STATUSES


def qualify_evidence_group(
    members: Sequence[Mapping[str, Any]],
    *,
    is_ticker_specific: Callable[[Mapping[str, Any]], bool],
) -> list[dict[str, Any]]:
    """Qualify one already-grouped Evidence Fact's member claims for
    activation-input eligibility.

    ``members`` are the group's existing per-claim dicts (already shaped by
    the caller's own eligibility pipeline -- this function never re-derives
    match/relation/assertion eligibility, it only adds a role-based
    activation-input filter on top). Each member must carry ``agent``, and
    the causal-evidence check reads ``relation``/``assertion_status`` when
    present (defaulting conservatively to "not proven" when absent).

    Returns a NEW list of dicts: every original key is preserved, plus the
    four additive fields ``source_agent``, ``source_role``,
    ``activation_eligible``, ``activation_qualification_reason``.

    Policy:
      * Any PRIMARY_RESEARCH member in the group -> that member is
        PRIMARY_QUALIFIED (eligible); every SECONDARY member in the SAME
        group is SECONDARY_DUPLICATE_OF_PRIMARY (ineligible -- the fact is
        already carried by the Primary member, so a Secondary restatement
        cannot inflate the group's count).
      * Secondary-only group (no Primary member): not ticker-specific ->
        SECONDARY_NOT_TICKER_SPECIFIC (ineligible). Ticker-specific and
        relation=="activation" and assertion_status=="asserted" ->
        SECONDARY_QUALIFIED_CAUSAL_EVIDENCE (eligible). Otherwise ->
        SECONDARY_CAUSALITY_UNPROVEN (ineligible, conservative default).
      * UNKNOWN role -> always UNKNOWN_SOURCE_ROLE (ineligible).
    """
    roles = [source_role_for_agent(member.get("agent")) for member in members]
    has_primary = any(role == SOURCE_ROLE_PRIMARY_RESEARCH for role in roles)

    qualified: list[dict[str, Any]] = []
    for member, role in zip(members, roles):
        agent = str(member.get("agent") or "").strip()
        if role == SOURCE_ROLE_PRIMARY_RESEARCH:
            eligible, reason = True, REASON_PRIMARY_QUALIFIED
        elif role == SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE:
            if has_primary:
                eligible, reason = False, REASON_SECONDARY_DUPLICATE_OF_PRIMARY
            elif not is_ticker_specific(member):
                eligible, reason = False, REASON_SECONDARY_NOT_TICKER_SPECIFIC
            elif _is_strong_causal_member(member):
                eligible, reason = True, REASON_SECONDARY_QUALIFIED_CAUSAL_EVIDENCE
            else:
                eligible, reason = False, REASON_SECONDARY_CAUSALITY_UNPROVEN
        else:
            eligible, reason = False, REASON_UNKNOWN_SOURCE_ROLE

        new_member = dict(member)
        new_member["source_agent"] = agent
        new_member["source_role"] = role
        new_member["activation_eligible"] = eligible
        new_member["activation_qualification_reason"] = reason
        qualified.append(new_member)
    return qualified


def filter_eligible(members: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Members already run through ``qualify_evidence_group`` whose
    ``activation_eligible`` is True."""
    return [dict(member) for member in members if member.get("activation_eligible")]


__all__ = [
    "EVIDENCE_SOURCE_ROLE_CONTRACT_VERSION",
    "SOURCE_ROLE_PRIMARY_RESEARCH",
    "SOURCE_ROLE_SECONDARY_DECISION_OR_DEBATE",
    "SOURCE_ROLE_UNKNOWN",
    "PRIMARY_RESEARCH_AGENTS",
    "SECONDARY_DECISION_OR_DEBATE_AGENTS",
    "REASON_PRIMARY_QUALIFIED",
    "REASON_PRIMARY_EXISTING_RULE_REJECTED",
    "REASON_SECONDARY_NOT_INDEPENDENT_EVIDENCE",
    "REASON_SECONDARY_NOT_TICKER_SPECIFIC",
    "REASON_SECONDARY_DUPLICATE_OF_PRIMARY",
    "REASON_SECONDARY_CAUSALITY_UNPROVEN",
    "REASON_SECONDARY_QUALIFIED_CAUSAL_EVIDENCE",
    "REASON_UNKNOWN_SOURCE_ROLE",
    "ALL_QUALIFICATION_REASON_CODES",
    "STRONG_CAUSAL_RELATIONS",
    "STRONG_ASSERTION_STATUSES",
    "source_role_for_agent",
    "qualify_evidence_group",
    "filter_eligible",
]
