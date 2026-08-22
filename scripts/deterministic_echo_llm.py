"""Offline LLM test/demo double for callers written before Pure-LLM Alpha
semantic authority (see comqutor_alpha/structure_engine/alpha_mapper.py).

Under that architecture, matched_alpha is exclusively an LLM decision -- a
pipeline run with no llm_gateway wired now reports match_status=
"unavailable" for every claim instead of silently reusing the deterministic
scorer's result. This starves any offline (zero-Provider-call) pipeline run
-- the W5 local demo seed (``seed_w5_demo.py``) and pipeline-level tests --
of real Activation/Conflict/Graph evidence.

``DeterministicEchoAlphaModel`` is a real ``Week2LLMGateway``-compatible
model whose alpha_classifier response deterministically ECHOES the same
deterministic scorer's own top candidate (select) or none -- so these
callers keep producing realistic, evidence-differentiated Alpha matches
without a real Provider call, exactly preserving demo_fixture metadata's
own ``live_provider_used: False`` contract.

Every OTHER semantic task (claim_batch_enrichment, structure_extractor,
evidence_stance_classifier) deliberately receives invalid/unrecognized
output from this model. Each of those tasks' existing fail-soft path never
rewrites the already-computed deterministic value on a rejected/invalid
response -- only provenance fields change (e.g.
evidence_stance_llm._apply_fallback stamps stance_method/
stance_fallback_reason but leaves evidence_stance itself untouched, since
alpha_mapper._attach_evidence_stance already computed it deterministically
before this module ever runs). So passing this gateway changes exactly one
thing versus not passing a gateway at all: the Alpha classifier itself goes
from "unavailable" to a real, deterministic-matching LLM decision.
"""

from __future__ import annotations

import json
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine.alpha_mapper import map_claim_to_alpha
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class DeterministicEchoAlphaModel:
    def __init__(self) -> None:
        self.calls = 0
        self._taxonomy = load_alpha_taxonomy()

    def invoke(self, prompt: str) -> _Response:
        self.calls += 1
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        if "alpha_taxonomy" not in payload:
            # claim_batch_enrichment / structure_extractor / evidence_stance_
            # classifier: deliberately invalid -> clean deterministic
            # fallback in each task's own existing fail-soft path (see
            # module docstring).
            return _Response(json.dumps({"invalid_by_design": True}))

        record = {
            "claim": payload.get("claim", ""),
            "evidence": payload.get("evidence", ""),
            "ticker": payload.get("ticker", ""),
            "factors": payload.get("factors", []),
            "direction": payload.get("direction", "neutral"),
        }
        deterministic = map_claim_to_alpha(record, self._taxonomy, classifier_enabled=False)
        top_alpha = deterministic["deterministic_top_alpha"]
        if top_alpha:
            decision: dict[str, Any] = {"decision": "select", "selected_alpha_id": top_alpha}
        else:
            decision = {"decision": "none", "selected_alpha_id": None}
        return _Response(json.dumps(decision))


def build_deterministic_echo_gateway(run_id: str, output_root: Any) -> Week2LLMGateway:
    """A real Week2LLMGateway wired to DeterministicEchoAlphaModel -- pass as
    ``week2_llm_gateway=`` to ``run_research_request``/``seed_w5_demo`` in
    place of the default (no gateway) so the Alpha classifier is genuinely
    consulted and exercised end to end, with zero real Provider calls."""
    return Week2LLMGateway(
        DeterministicEchoAlphaModel(),
        run_id=run_id,
        output_root=output_root,
        timeout_seconds=5.0,
        max_retries=0,
        max_calls=200,
        provider="offline-deterministic-echo",
        model_name="offline-deterministic-echo",
    )
