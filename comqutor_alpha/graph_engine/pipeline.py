"""Assembles the canonical Week 3 ``structure_graph.json`` contract.

Combines :func:`graph_builder.build_structure_graph` and
:func:`activation_scorer.score_alpha_activations` into the single payload
that is written as the ``structure_graph.json`` file artifact and persisted
verbatim into ``structure_graphs.graph_json``. Kept as a thin composition
layer so the two engines stay independently unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.exposure.seed_loader import load_exposure_seed, resolve_exposure_mode
from comqutor_alpha.exposure_engine import compute_run_entity_alpha_exposures
from comqutor_alpha.graph_engine.activation_scorer import score_alpha_activations
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    ACTIVATION_V2_FORMULA_VERSION,
    score_alpha_activations_v2,
)
from comqutor_alpha.graph_engine.alpha_level_classifier import classify_and_rebuild_collections
from comqutor_alpha.graph_engine.graph_builder import build_structure_graph
from comqutor_alpha.graph_engine.graph_schema import (
    ACTIVATION_SCORER_VERSION,
    GRAPH_BUILDER_VERSION,
    GRAPH_SCHEMA_VERSION_V2,
)
from comqutor_alpha.graph_engine.issuer_aliases import company_names_for_ticker
from comqutor_alpha.graph_engine.verified_evidence_gate import (
    EVIDENCE_GATE_POLICY_VERSION,
    EVIDENCE_GATE_SOURCES_UNAVAILABLE,
    EVIDENCE_GATE_STRUCTURED_RECORDS_UNAVAILABLE,
    EVIDENCE_GATE_VERSION,
    EvidenceGateInputError,
    requires_source_resolution,
    score_alpha_activations_v2_verified,
)


def _match_relation_details(record: Mapping[str, Any], alpha_id: str) -> dict[str, Any]:
    """Read back the Week 2 candidate entry for this claim's matched alpha.

    Never recomputes semantics -- only surfaces what the mapper already
    attached (relation / matched_keywords / matched_factors)."""
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                return {
                    "relation": str(candidate.get("relation") or "unknown"),
                    "matched_keywords": [
                        str(k) for k in (candidate.get("matched_keywords") or []) if str(k).strip()
                    ],
                    "matched_factors": [
                        str(f) for f in (candidate.get("matched_factors") or []) if str(f).strip()
                    ],
                }
    return {"relation": "unknown", "matched_keywords": [], "matched_factors": []}


def _attach_evidence_detail(
    activation_alphas: list[dict[str, Any]],
    alpha_matches_payload: Mapping[str, Any],
) -> None:
    """Additively attach full per-claim evidence provenance to each scored
    alpha (claim text, agent, source_agent_output_id, match score, relation,
    matched keywords/factors, assertion status, direction). Purely a
    read-back join against ``alpha_matches`` records -- the frozen activation
    formula, weights, and every existing field stay byte-identical."""
    matches = (
        alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    )
    by_claim_id: dict[str, Mapping[str, Any]] = {}
    if isinstance(matches, list):
        for record in matches:
            if isinstance(record, Mapping) and record.get("claim_id"):
                by_claim_id[str(record["claim_id"])] = record

    for entry in activation_alphas:
        alpha_id = str(entry.get("alpha_id") or "")
        details = []
        for claim_id in entry.get("claim_ids") or []:
            record = by_claim_id.get(str(claim_id))
            if record is None:
                continue
            relation_details = _match_relation_details(record, alpha_id)
            details.append(
                {
                    "claim_id": str(claim_id),
                    "claim": str(record.get("claim") or ""),
                    "agent": str(record.get("agent") or ""),
                    "source_agent_output_id": str(record.get("source_agent_output_id") or ""),
                    "match_score": record.get("score", 0.0),
                    "assertion_status": str(record.get("assertion_status") or "unknown"),
                    "direction": str(record.get("direction") or "unknown"),
                    **relation_details,
                }
            )
        details.sort(key=lambda item: item["claim_id"])
        entry["evidence_detail"] = details


def _provenance(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
) -> dict[str, Any]:
    records = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    records = records if isinstance(records, list) else []
    counts = {"matched": 0, "ambiguous": 0, "no_match": 0}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        status = record.get("match_status")
        if status in counts:
            counts[status] += 1
    return {
        "source_artifacts": {
            "alpha_matches_schema_version": alpha_matches_payload.get("schema_version")
            if isinstance(alpha_matches_payload, Mapping)
            else None,
            "extracted_structures_schema_version": extracted_structures_payload.get("schema_version")
            if isinstance(extracted_structures_payload, Mapping)
            else None,
        },
        "committed_match_count": counts["matched"],
        "ambiguous_match_count": counts["ambiguous"],
        "no_match_count": counts["no_match"],
        "total_claim_count": len(records),
    }


def build_structure_graph_stage(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Stage 1: build the Structure Graph only (no activation scoring).

    Split out from :func:`build_and_score_structure_graph` so callers that
    need to distinguish "graph construction failed" from "activation
    scoring failed" (e.g. for a stage-specific error code) can catch each
    stage independently.
    """
    return build_structure_graph(alpha_matches_payload, extracted_structures_payload)


def _activation_block(activation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "formula_version": activation["formula_version"],
        "weights": activation["weights"],
        "run_timestamp": activation["run_timestamp"],
        "as_of": activation["as_of"],
        "alphas": activation["alphas"],
    }


def score_and_assemble_structure_graph(
    graph: Mapping[str, Any],
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
    structured_records: Any = None,
    exposure_run_id: str | None = None,
    exposure_seed_bundle: Any = None,
    exposure_mode_decision: Any = None,
    sources: list[dict[str, Any]] | None = None,
    require_verified_evidence_gate: bool = False,
) -> dict[str, Any]:
    """Stage 2: score all MVP-10 Alphas against an already-built graph and
    assemble the final ``structure_graph.json`` contract.

    Versioned activation contract (Activation v2 sprint, additive):
    ``activation_versions`` holds every computed view, keyed by name, and
    ``primary_activation_version`` names which VIEW's formula_version is
    OFFICIAL -- ``activation`` (the field every existing consumer reads) is
    always exactly that named view, never independently drifting from it
    (``validate_structure_graph_contract`` enforces this). The v1 payload
    is computed by the unchanged v1 scorer -- it stays available as the
    audit baseline. ``schema_version`` is unchanged: historical graphs
    (v1-only, no ``activation_versions``) remain fully readable.

    ``sources`` (T1 verified-support eligibility gate; escalated
    2026-09-28 from "additive diagnostic" to "official result"): OPTIONAL,
    this run's own source_registry.json ``sources`` list. When supplied
    together with ``structured_records``, a third view -- computed via
    ``verified_evidence_gate.score_alpha_activations_v2_verified`` (the
    SAME, unmodified Activation v2 formula/weights/thresholds, restricted
    to claims whose source link is genuinely HUMAN_REVIEWED-verified) --
    BECOMES the OFFICIAL result: ``activation``/``primary_activation_
    version``/``dominant_alphas``/``active_alphas``/``regime_level_alphas``
    /``candidate_alphas``/``blocked_alphas``/``entity_alpha_exposures`` are
    all computed from it (B3 Exposure and B4 classification run on the
    VERIFIED pool, exactly as they otherwise run on v2 -- neither function
    is alpha-version-aware, both operate generically on "an activation
    payload of this shape"). The RAW v2 view survives unconditionally as
    ``activation_versions["v2"]`` -- a diagnostic/audit-only view once a
    verified view exists, no longer a route to an official result that
    bypasses the gate. An alpha with zero verified evidence naturally
    scores near/at zero and lands in the existing "inactive"/"watch" bands
    -- there is no new invented status string; insufficient reviewed
    evidence surfaces through the SAME frozen status vocabulary, never a
    fabricated one. Omitting ``sources`` (every pre-existing caller,
    including every historical run computed before this gate existed)
    computes EXACTLY today's original behavior: official = v2, no
    "v2_verified" key at all -- a historical artifact is never rewritten or
    reinterpreted by this function; it simply never reaches this branch.

    ``require_verified_evidence_gate`` (2026-09-28 closing fix, extended
    2026-09-29 to the normal new-research production entrypoint): OPTIONAL,
    default ``False``. ``False`` means the OLD opportunistic behavior:
    a historical-read-only caller or a caller that genuinely has no gate
    concept never sets this, and the gate is used only when data happens to
    be available. Whether the gate is REQUIRED is decided by this explicit
    flag -- never merely inferred from whether ``sources``/
    ``structured_records`` happen to be present. When ``True`` (today: both
    ``routes_research.run_research_request``'s normal new-research
    production path and ``routes_research.trigger_content_support_
    reevaluation``'s own execution -- the SAME rule for both, so Activation
    and Conflict, and new research and re-evaluation, can never diverge),
    ``structured_records is None`` (``structured_agent_outputs.json``
    itself missing or corrupted -- this artifact is REQUIRED for any run
    reaching Week 3) always raises
    :class:`verified_evidence_gate.EvidenceGateInputError`. ``sources is
    None`` raises the SAME error ONLY when ``structured_records`` actually
    contains at least one claim with ``source_link_status == VALID`` (see
    ``verified_evidence_gate.requires_source_resolution``) -- a run with NO
    source-linked claims at all (every non-news chain; every pre-existing
    offline fixture that predates source-linking entirely) never needed
    ``sources`` to resolve anything, so its absence is immaterial: the gate
    simply never activates for that run and the v2/raw pool stays official,
    exactly as if this flag were ``False`` -- never mistaken for "verified
    with zero evidence." A required execution must never quietly produce an
    "official PASS" under the old formula just because its OWN relevant
    input failed to load. A genuinely-resolved but EMPTY ``sources`` list
    (``[]``) is NOT an error -- the gate still runs, honestly reporting zero
    verified evidence (insufficient evidence, not a failure). When this flag
    is ``True``, the persisted payload additionally names
    ``evidence_gate_policy_version`` -- an explicit, traceable record of
    WHICH EXECUTION RULE governed this run, independent of whether the gate
    happened to activate for it.
    """
    activation_v1 = score_alpha_activations(
        alpha_matches_payload,
        graph["graph_coherence"]["score"],
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )
    _attach_evidence_detail(activation_v1["alphas"], alpha_matches_payload)

    activation_v2 = score_alpha_activations_v2(
        alpha_matches_payload,
        graph_edges=graph.get("edges") or (),
        ticker=graph.get("ticker"),
        # P1 Evidence Correctness Fix: canonical issuer-name/alias lookup
        # (graph_engine/issuer_aliases.py) -- previously always omitted,
        # which silently defaulted to () and made ticker-specificity match
        # only the bare ticker symbol, never the issuer's real name (see
        # docs/audit_artifacts/v0_1_3_a102_cross_company_integrity_audit.md).
        # Returns () for any ticker not in the registry (including QQQ),
        # a safe no-op that preserves current behavior exactly for those.
        company_names=company_names_for_ticker(graph.get("ticker")),
        structured_records=structured_records,
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )
    _attach_evidence_detail(activation_v2["alphas"], alpha_matches_payload)

    if require_verified_evidence_gate:
        if structured_records is None:
            raise EvidenceGateInputError(EVIDENCE_GATE_STRUCTURED_RECORDS_UNAVAILABLE)
        if sources is None and requires_source_resolution(structured_records):
            raise EvidenceGateInputError(EVIDENCE_GATE_SOURCES_UNAVAILABLE)

    # 2026-09-29 gate-bypass fix: "does this run need to READ sources" and
    # "is this run's evidence QUALIFIED" are different questions -- the
    # former being moot (no claim needs source resolution -- e.g. every
    # claim is source_link_status=NOT_PROVIDED, a source type this round
    # has not yet wired real linking for) must never make the latter true
    # by default. Once require_verified_evidence_gate=True has survived the
    # fail-closed check above, the verified (qualified-evidence-only) pool
    # is ALWAYS official -- never conditioned on sources happening to be
    # non-None or on any claim actually needing it. score_alpha_v2_verified
    # (via compute_verified_support_eligibility) already safely treats
    # sources=None as "nothing resolvable" and correctly rejects every
    # NOT_PROVIDED/UNKNOWN_ID/CONTENT_UNAVAILABLE/TIME_INVALID claim before
    # ever consulting sources at all, so a run with zero qualifying claims
    # (no source-linked claims anywhere, or none yet reviewed) still runs
    # this SAME scorer and honestly reports zero verified evidence -- never
    # silently satisfied by the raw v2 pool instead. For an OPPORTUNISTIC
    # caller (require_verified_evidence_gate=False -- every historical run,
    # and every caller that genuinely has no gate concept), behavior is
    # UNCHANGED: the verified view is used only when both sources and
    # structured_records happen to be supplied.
    verified_evidence_available = require_verified_evidence_gate or (
        sources is not None and structured_records is not None
    )
    activation_v2_verified = None
    if verified_evidence_available:
        activation_v2_verified = score_alpha_activations_v2_verified(
            alpha_matches_payload,
            structured_records=structured_records,
            sources=sources,
            graph_edges=graph.get("edges") or (),
            ticker=graph.get("ticker"),
            company_names=company_names_for_ticker(graph.get("ticker")),
            taxonomy=taxonomy,
            run_timestamp=run_timestamp,
            as_of=as_of,
        )
        _attach_evidence_detail(activation_v2_verified["alphas"], alpha_matches_payload)

    # The OFFICIAL pool: v2_verified when this run supports the gate,
    # otherwise v2 exactly as before. B3 Exposure and B4 classification run
    # ONLY on the official pool (matching pre-existing behavior when no
    # verified view exists) -- the raw v2 diagnostic view, when a verified
    # view exists, intentionally does NOT get exposure/classification
    # re-run a second time, since it is no longer an official-result
    # candidate.
    official_activation = activation_v2_verified if verified_evidence_available else activation_v2
    official_formula_version = (
        official_activation["formula_version"] if verified_evidence_available else ACTIVATION_V2_FORMULA_VERSION
    )

    seed_bundle = exposure_seed_bundle or load_exposure_seed()
    mode_decision = exposure_mode_decision or resolve_exposure_mode(seed_bundle, str(graph["ticker"]))
    official_activation, exposure_artifact = compute_run_entity_alpha_exposures(
        run_id=exposure_run_id or str(graph["run_id"]),
        ticker=str(graph["ticker"]),
        activation_payload=official_activation,
        seed_bundle=seed_bundle,
        mode_decision=mode_decision,
    )
    # B4 alpha-level classification (task B4_ACTIVATION_LEVEL_ALIGNMENT):
    # the single authoritative pass, run only now that every qualification
    # input -- the official pool's own score/caps/regime gate, and B3
    # Entity Exposure's per-alpha record -- is available. Writes the final
    # status/target_level/qualified_level/is_blocked/blocked_from/
    # blocked_reason_codes/diagnostic_reason_codes onto each official alpha
    # entry and rebuilds dominant_alphas/active_alphas/regime_level_alphas/
    # candidate_alphas/blocked_alphas exactly once -- never re-derived
    # independently by the API or the frontend afterward.
    official_activation = classify_and_rebuild_collections(official_activation)
    if verified_evidence_available:
        activation_v2_verified = official_activation
    else:
        activation_v2 = official_activation

    # Built exactly once and reused for both "activation" (the OFFICIAL
    # payload callers read) and its own named entry in activation_versions
    # -- so the two can never independently drift apart;
    # validate_structure_graph_contract checks this invariant holds, but
    # constructing it once makes a violation structurally impossible rather
    # than merely usually-true.
    v1_block = _activation_block(activation_v1)
    v2_block = _activation_block(activation_v2)
    official_block = _activation_block(official_activation)

    activation_versions = {"v1": v1_block, "v2": v2_block}
    if verified_evidence_available:
        activation_versions["v2_verified"] = official_block

    payload = {
        "schema_version": GRAPH_SCHEMA_VERSION_V2,
        "graph_builder_version": GRAPH_BUILDER_VERSION,
        "activation_scorer_version": ACTIVATION_SCORER_VERSION,
        "run_id": graph["run_id"],
        "ticker": graph["ticker"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "graph_metrics": graph["graph_metrics"],
        "graph_coherence": graph["graph_coherence"],
        "activation": official_block,
        "activation_versions": activation_versions,
        "primary_activation_version": official_formula_version,
        "dominant_alphas": official_activation["dominant_alphas"],
        # B4 additive authoritative collections (task
        # B4_ACTIVATION_LEVEL_ALIGNMENT, section 11) -- dominant_alphas
        # above keeps its exact pre-existing meaning (dominant OR
        # regime_level) for backward compatibility; these four are new,
        # split by the single true qualified_level/is_blocked B4 just
        # computed. Sibling top-level fields, same pattern as
        # dominant_alphas -- never nested inside the narrower
        # activation/activation_versions blocks. All computed from
        # ``official_activation`` -- the verified pool when this run
        # supports the gate, never the bypassed raw pool.
        "active_alphas": official_activation["active_alphas"],
        "regime_level_alphas": official_activation["regime_level_alphas"],
        "candidate_alphas": official_activation["candidate_alphas"],
        "blocked_alphas": official_activation["blocked_alphas"],
        "entity_alpha_exposures": exposure_artifact,
        "provenance": _provenance(alpha_matches_payload, extracted_structures_payload),
    }
    if verified_evidence_available:
        # Explicit, traceable rule-version marker (2026-09-28): names the
        # gate that produced this run's OFFICIAL result. Absent entirely
        # (never a fabricated/backfilled value) on a historical run or any
        # run whose caller did not supply sources.
        payload["evidence_gate_version"] = EVIDENCE_GATE_VERSION
        payload["evidence_gate_applied"] = True
    if require_verified_evidence_gate:
        # Explicit, persisted record of WHICH EXECUTION RULE this run's
        # caller used (2026-09-29 closing fix) -- independent of whether
        # the gate happened to activate for it (a run with no source-linked
        # claims at all still recorded this rule as required, even though
        # verified_evidence_available above is False and no v2_verified
        # view exists). Absent entirely on any run whose caller left the
        # gate opportunistic (default), and on every historical run.
        payload["evidence_gate_policy_version"] = EVIDENCE_GATE_POLICY_VERSION
        payload["evidence_gate_required"] = True
    return payload


def build_and_score_structure_graph(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
    structured_records: Any = None,
    sources: list[dict[str, Any]] | None = None,
    require_verified_evidence_gate: bool = False,
) -> dict[str, Any]:
    """Build the Structure Graph and score all MVP-10 Alphas against it.

    Pure function of its inputs (plus the optional deterministic
    ``run_timestamp``/``as_of`` pair) -- no I/O, no wall-clock reads. Both
    stages combined; callers that need per-stage error isolation should use
    :func:`build_structure_graph_stage` and
    :func:`score_and_assemble_structure_graph` directly instead.

    ``require_verified_evidence_gate`` is passed straight through to
    :func:`score_and_assemble_structure_graph` -- see that function's
    docstring for the opportunistic-vs-required distinction.
    """
    graph = build_structure_graph_stage(alpha_matches_payload, extracted_structures_payload)
    return score_and_assemble_structure_graph(
        graph,
        alpha_matches_payload,
        extracted_structures_payload,
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
        structured_records=structured_records,
        sources=sources,
        require_verified_evidence_gate=require_verified_evidence_gate,
    )
