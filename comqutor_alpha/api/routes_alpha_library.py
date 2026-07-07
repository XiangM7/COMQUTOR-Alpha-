"""Week 1 alpha library helpers and optional FastAPI routes."""

from __future__ import annotations

from comqutor_alpha.alpha_library.alpha_loader import get_alpha_by_id, load_alpha_taxonomy


SCHEMA_VERSION = "week1.alpha_library.v1"


def serialize_alpha(alpha):
    return {
        "alpha_id": alpha.alpha_id,
        "name_en": alpha.name_en,
        "name_cn": alpha.name_cn,
        "layer": alpha.layer,
        "status": alpha.status,
        "core_thesis": alpha.core_thesis,
        "keywords": list(alpha.keywords),
        "trigger_signals": list(alpha.trigger_signals),
        "confirmation_signals": list(alpha.confirmation_signals),
        "beneficiary_assets": list(alpha.beneficiary_assets),
        "risk_assets": list(alpha.risk_assets),
        "conflict_alphas": [
            {
                "alpha_id": conflict.alpha_id,
                "contradiction_weight": conflict.contradiction_weight,
            }
            for conflict in alpha.conflict_alphas
        ],
        "invalidation_conditions": list(alpha.invalidation_conditions),
        "agent_sources": list(alpha.agent_sources),
    }


def get_alpha_library():
    taxonomy = load_alpha_taxonomy()
    alphas = [serialize_alpha(taxonomy[alpha_id]) for alpha_id in sorted(taxonomy)]
    return {
        "schema_version": SCHEMA_VERSION,
        "alpha_count": len(alphas),
        "alphas": alphas,
    }


def get_alpha_detail(alpha_id):
    alpha = get_alpha_by_id(alpha_id)
    if alpha is None:
        return {"error": f"Alpha not found: {alpha_id}"}
    return serialize_alpha(alpha)


try:
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/api/alpha-library")
    def get_alpha_library_route():
        return get_alpha_library()

    @router.get("/api/alpha-library/{alpha_id}")
    def get_alpha_detail_route(alpha_id: str):
        return get_alpha_detail(alpha_id)

except ImportError:
    router = None
