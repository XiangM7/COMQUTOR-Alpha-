"""P4 phase 1 (2026-10-12): the ONLY entry that runs the Alpha relevance judgment -- explicit, experimental, default off.

The research pipeline never calls the relevance task. This entry runs it over a SAVED run directory outside the repository's
``outputs/`` tree (a verification copy), and only when an experiment configuration explicitly enables it:

  * ``DEFAULT_CONFIG`` is disabled: running it sends nothing and writes nothing.
  * ``P4_RELEVANCE_SIMULATED_20261012`` is the one enabled configuration of this phase. Its gateway mode is ``SIMULATED``: the
    shared ``Week2LLMGateway`` (retry / timeout / budget / semantic-runtime machinery unchanged) is given
    ``SimulatedRelevanceProvider`` instead of a model client. Every answer that provider returns is TEST DATA, stamped as such in
    each basis, in the semantic records (provider ``simulated``, execution mode ``test``) and in the results file. A real gateway mode
    does not exist in this phase; asking for one is refused.

Existing execution profiles (``week2_execution_profile``) are not touched: this configuration is independent of them.

Writes, per judged run: ``alpha_relevance_ledger/`` (the task's own semantic records + manifest), ``alpha_relevance_judgments.json``
(``alpha_relevance_judgment.v1``), and -- so the Export carries the result -- a refreshed ``evidence_trace.json`` (only for a run that
already exports one) and ``artifact_manifest.json``. A run is judged once: a second run of the entry on the same directory is
refused (re-judging belongs in a new derived execution), so a relevance ledger never holds two competing answers by design.

P4 phase 2 (2026-10-12) adds ``run_relevance_evaluation_plan``: the controlled execution of a frozen small-sample evaluation plan
(``alpha_relevance_eval_prep``). Its configuration ``P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012`` is disabled for every run-level path
(``judge_run_relevance`` answers "disabled") and is usable only through that function, with an explicit mode (``LIVE`` or the
``SIMULATED_REHEARSAL`` of the same plan), the plan, the sample manifest and a one-time authorization whose hashes all agree. It sends
only the relevance task, only the planned requests (repeats included in the cap), never retries, never widens the scope, and writes
into a new evaluation directory -- one task-own ledger per round -- outside the repository's ``outputs/`` tree.

Session 4 (2026-10-12) adds ``P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012`` for a development-set retest of prompt v2 / criterion exp2
(same entry, same refusals, same settings). The plan pins the task identity it was made for; the current identity must equal it.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from comqutor_alpha import alpha_relevance_eval_prep as ep
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    AlphaRelevanceDefinition,
    RelevanceElementsError,
    load_relevance_definitions,
    sha256_canonical_json,
    taxonomy_content_version,
)
from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
    LEDGER_DIRNAME,
    RESULTS_FILENAME,
    SIMULATED_PROVIDER,
    RelevanceLedger,
    build_results_payload,
    verify_relevance_judgments,
)
from comqutor_alpha.storage.file_store import (
    load_json_record_if_exists,
    run_dir_for,
    save_json_record,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl
from comqutor_alpha.structure_engine.alpha_relevance_llm import (
    CRITERION_EXP3,
    LLM_TASK_NAME,
    PROMPT_IDENTITY_SEPARATOR,
    STATE_JUDGED,
    STATE_UNRESOLVED,
    RelevanceRequestItem,
    batch_payload,
    build_request_items,
    judge_relevance,
    task_identity,
)

EXPERIMENT_CONFIG_SCHEMA = "alpha_relevance_experiment.v1"
GATEWAY_NONE = "NONE"
GATEWAY_SIMULATED = "SIMULATED"
SIMULATED_MODEL = "simulated-relevance.v1"
# v2 (2026-10-12): answers follow output contract v2 (every anchor carries a quote of the claim's own words); one more bucket quotes
# words that are not in the claim, so the evidence check is exercised. v1 answered output v1 (no quotes); its records keep saying v1.
SIMULATION_RULE = "simulated_hash_buckets.v2"
# v3 (2026-10-12, session 6): a request of criterion exp3 is answered in output contract v3 (statements; the module derives the tier),
# with buckets that also exercise an illegal mode, a hit without an element, a foreign quote, a weak without linking words and a hit
# reported together with a no-hit tier. Requests of exp1 / exp2 keep the v2 answers above, so older contracts stay testable.
SIMULATION_RULE_V3 = "simulated_hash_buckets.v3"
SIMULATED_FOREIGN_QUOTE = "SIMULATED words that are not in the claim"


def _simulation_rule() -> str:
    return SIMULATION_RULE_V3 if rl.CRITERION_VERSION == CRITERION_EXP3 else SIMULATION_RULE


@dataclass(frozen=True)
class RelevanceExperimentConfig:
    name: str
    enabled: bool
    gateway_mode: str
    batch_size: int
    timeout_seconds: float
    max_retries: int
    max_calls: int
    basis: str

    def as_dict(self) -> dict[str, Any]:
        return {"schema": EXPERIMENT_CONFIG_SCHEMA, **asdict(self)}


DEFAULT_CONFIG = RelevanceExperimentConfig(
    name="default_off", enabled=False, gateway_mode=GATEWAY_NONE, batch_size=8, timeout_seconds=30.0, max_retries=0, max_calls=1,
    basis="the relevance task is off unless an experiment configuration explicitly enables it",
)
P4_RELEVANCE_SIMULATED_20261012 = RelevanceExperimentConfig(
    name="p4_relevance_simulated_20261012", enabled=True, gateway_mode=GATEWAY_SIMULATED, batch_size=8, timeout_seconds=30.0,
    max_retries=0, max_calls=200,
    basis="P4 phase 1 engineering-chain verification with simulated answers only (zero model, search or data-fetch calls)",
)
EXPERIMENT_CONFIGS = {config.name: config for config in (P4_RELEVANCE_SIMULATED_20261012,)}


class _SimulatedMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class SimulatedRelevanceProvider:
    """TEST DATA ONLY -- never a model and never a judgment. Answers every requested pair by a fixed hash-bucket rule so the engineering
    chain exercises every outcome: core / strong / weak / none / UNRESOLVED, plus an illegal label, a missing result, a duplicate result,
    a tier/anchor contradiction and a quote that is not in the claim (which the contract must turn into FAILED). Every anchor carries a
    quote (the claim's first words), as output contract v2 requires. Makes no network call."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, prompt: str) -> _SimulatedMessage:
        self.calls += 1
        payload = json.loads(prompt.split(PROMPT_IDENTITY_SEPARATOR, 1)[1])
        definitions = {d["alpha_id"]: d for d in payload.get("alpha_definitions") or []}
        out: list[dict[str, Any]] = []
        answers = self._statement_answers if payload.get("criterion_version") == CRITERION_EXP3 else self._answers
        for item in payload.get("items") or []:
            out.extend(answers(item["claim_id"], item["alpha_id"], definitions.get(item["alpha_id"]) or {}, str(item.get("claim_text") or "")))
        return _SimulatedMessage(json.dumps({"items": out}))

    @staticmethod
    def _statement_answers(claim_id: str, alpha_id: str, definition: dict[str, Any], claim_text: str = "") -> list[dict[str, Any]]:
        """Output v3 answers (criterion exp3) -- TEST DATA."""
        bucket = int(hashlib.sha256(f"{claim_id}|{alpha_id}".encode()).hexdigest()[:8], 16) % 23
        elements = definition.get("elements") or []
        core = [e["id"] for e in elements if e.get("ownership") == "core"]
        strong = [e["id"] for e in elements if e.get("ownership") == "strong"]
        basis = f"SIMULATED TEST DATA (rule {SIMULATION_RULE_V3}, bucket {bucket}) -- not a model judgment."
        own_words = " ".join(claim_text.split())[:80]

        def statement(element: str | None, hit: bool, mode: str = "assertion", quote: str | None = None) -> dict[str, Any]:
            return {"quote": own_words if quote is None else quote, "object": "SIMULATED object", "property": "SIMULATED property",
                    "mode": mode, "element_id": element, "hit": hit, "why": "SIMULATED TEST DATA"}

        def answer(outcome: str, statements: list[dict[str, Any]], no_hit: str | None = None, unresolved: str | None = None) -> dict[str, Any]:
            return {"claim_id": claim_id, "alpha_id": alpha_id, "outcome": outcome, "statements": statements, "no_hit_tier": no_hit,
                    "basis": basis, "unresolved_reason": unresolved}

        if bucket <= 5 and core:
            return [answer("DETERMINED", [statement(core[0], True, ("assertion", "forecast", "probability", "condition", "negation", "question")[bucket])])]
        if bucket <= 8 and strong:
            return [answer("DETERMINED", [statement(strong[0], True)])]
        if bucket <= 11:
            return [answer("DETERMINED", [statement(None, False)], "weak")]
        if bucket <= 13:
            return [answer("DETERMINED", [], "none")]
        if bucket <= 15:
            return [answer("UNRESOLVED", [], unresolved="SIMULATED TEST DATA: the information that would decide it is missing")]
        if bucket == 16:
            return [answer("DETERMINED", [statement(core[0] if core else None, True, "speculation")])]  # illegal mode
        if bucket == 17:
            return []  # missing result
        if bucket == 18:
            return [answer("DETERMINED", [], "none"), answer("DETERMINED", [], "none")]  # duplicate result
        if bucket == 19:
            return [answer("DETERMINED", [statement(None, True)])]  # a hit that names no element
        if bucket == 20 and core:
            return [answer("DETERMINED", [statement(core[0], True, quote=SIMULATED_FOREIGN_QUOTE)])]  # a quote that is not in the claim
        if bucket == 21:
            return [answer("DETERMINED", [], "weak")]  # weak without the linking words
        return [answer("DETERMINED", [statement(core[0] if core else None, bool(core))], "weak")]  # a hit reported with a no-hit tier

    @staticmethod
    def _answers(claim_id: str, alpha_id: str, definition: dict[str, Any], claim_text: str = "") -> list[dict[str, Any]]:
        bucket = int(hashlib.sha256(f"{claim_id}|{alpha_id}".encode()).hexdigest()[:8], 16) % 22
        elements = definition.get("elements") or []
        core = [e["id"] for e in elements if e.get("ownership") == "core"]
        strong = [e["id"] for e in elements if e.get("ownership") == "strong"]
        basis = f"SIMULATED TEST DATA (rule {SIMULATION_RULE}, bucket {bucket}) -- not a model judgment."
        own_words = " ".join(claim_text.split())[:80]

        def answer(outcome: str, tier: str | None, anchors: list[str], unresolved: str | None = None, quote: str | None = None) -> dict[str, Any]:
            return {"claim_id": claim_id, "alpha_id": alpha_id, "outcome": outcome, "tier": tier, "anchor_element_ids": anchors,
                    "anchor_evidence": [{"element_id": a, "quote": quote if quote is not None else own_words} for a in anchors],
                    "basis": basis, "unresolved_reason": unresolved}

        if bucket <= 5 and core:
            return [answer("DETERMINED", "core", [core[0]])]
        if bucket <= 8 and strong:
            return [answer("DETERMINED", "strong", [strong[0]])]
        if bucket <= 11:
            return [answer("DETERMINED", "weak", [])]
        if bucket <= 14:
            return [answer("DETERMINED", "none", [])]
        if bucket <= 16:
            return [answer("UNRESOLVED", None, [], "SIMULATED TEST DATA: ownership deliberately left undetermined")]
        if bucket == 17:
            return [answer("DETERMINED", "moderate", [])]  # illegal label
        if bucket == 18:
            return []  # missing result
        if bucket == 19:
            return [answer("DETERMINED", "weak", []), answer("DETERMINED", "none", [])]  # duplicate result
        if bucket == 21 and core:
            return [answer("DETERMINED", "core", [core[0]], quote=SIMULATED_FOREIGN_QUOTE)]  # a quote that is not in the claim
        return [answer("DETERMINED", "strong", core[:1])]  # strong with a core-owned anchor: contradicts Q1


def _fail(code: str, **extra: Any) -> dict[str, Any]:
    return {"status": "failed", "error_code": code, **extra}


def _refresh_exported_artifacts(run_id: str, output_root: Any, metadata: dict[str, Any], ticker: str) -> list[str]:
    """Rebuild what the Export bundles, so it carries the new record (the pipeline is not rerun; scoring artifacts are untouched)."""
    from comqutor_alpha.api.artifact_export import (
        build_and_write_artifact_manifest,  # noqa: PLC0415
    )
    from comqutor_alpha.api.evidence_trace import (  # noqa: PLC0415
        EVIDENCE_TRACE_FILENAME,
        build_evidence_trace_artifact,
    )

    refreshed = []
    if metadata.get("fact_dependency_contract"):
        trace = build_evidence_trace_artifact(run_id, output_root)
        if trace is not None:
            save_json_record(run_id, EVIDENCE_TRACE_FILENAME, trace, output_root=output_root)
            refreshed.append(EVIDENCE_TRACE_FILENAME)
    build_and_write_artifact_manifest(run_id=run_id, ticker=ticker, output_root=output_root)
    refreshed.append("artifact_manifest.json")
    return refreshed


def judge_run_relevance(
    run_id: str,
    *,
    output_root: Any,
    config: RelevanceExperimentConfig = DEFAULT_CONFIG,
    provider: Any = None,
) -> dict[str, Any]:
    """Run the relevance task over one saved run's matched pairs (see the module docstring for every refusal)."""
    from comqutor_alpha.consumption_recompute import refuse_real_outputs  # noqa: PLC0415

    refuse_real_outputs(output_root)
    if not config.enabled:
        return {"status": "disabled", "config": config.name, "provider_calls": 0, "writes": []}
    if config.gateway_mode != GATEWAY_SIMULATED:
        return _fail("REAL_GATEWAY_NOT_AUTHORIZED_IN_PHASE_1", config=config.name, gateway_mode=config.gateway_mode)
    try:
        safe = validate_run_id_for_path(run_id)
    except ValueError:
        return _fail("INVALID_RUN_ID", run_id=str(run_id))
    run_dir = run_dir_for(safe, output_root)
    if not run_dir.is_dir():
        return _fail("RUN_NOT_FOUND", run_id=safe)
    if (run_dir / RESULTS_FILENAME).exists() or (run_dir / LEDGER_DIRNAME).exists():
        return _fail("RELEVANCE_ALREADY_JUDGED", run_id=safe)
    metadata = load_json_record_if_exists(safe, "metadata.json", output_root=output_root) or {}
    alpha_matches = load_json_record_if_exists(safe, "alpha_matches.json", output_root=output_root)
    if not isinstance(alpha_matches, dict) or not isinstance(alpha_matches.get("matches"), list):
        return _fail("ALPHA_MATCHES_MISSING", run_id=safe)
    ticker = str(metadata.get("ticker") or alpha_matches.get("ticker") or "")
    try:
        definitions = load_relevance_definitions()
    except RelevanceElementsError as exc:
        return _fail("RELEVANCE_DEFINITIONS_UNAVAILABLE", reason=exc.reason_code)

    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession  # noqa: PLC0415
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: PLC0415

    items, without_definition = build_request_items(alpha_matches["matches"], ticker=ticker, definitions=definitions)
    provider = provider if provider is not None else SimulatedRelevanceProvider()
    ledger_dir = run_dir / LEDGER_DIRNAME
    ledger_dir.mkdir()
    session = SemanticRuntimeSession(run_id=safe, output_directory=ledger_dir, execution_mode="test", provider=SIMULATED_PROVIDER,
                                     model=SIMULATED_MODEL, profile_id=config.name)
    gateway = Week2LLMGateway(provider, run_id=safe, output_root=str(output_root), timeout_seconds=config.timeout_seconds,
                              max_retries=config.max_retries, max_calls=config.max_calls, provider=SIMULATED_PROVIDER,
                              model_name=SIMULATED_MODEL, semantic_runtime=session)
    results, stats = judge_relevance(items, gateway, batch_size=config.batch_size, timeout_seconds=config.timeout_seconds,
                                     max_retries=config.max_retries, execution_policy_source=f"experiment:{config.name}")
    session.finalize_manifest(complete=True)
    ledger = RelevanceLedger.load(run_dir)
    experiment = {**config.as_dict(), "provider": SIMULATED_PROVIDER, "model": SIMULATED_MODEL, "simulation_rule": _simulation_rule(),
                  "test_data": True}
    payload = build_results_payload(
        run_id=safe, ticker=ticker, items=items, results=results, without_definition=without_definition,
        ledger={k: v for k, v in ledger.description().items() if k in ("directory", "integrity", "calls_file_sha256", "manifest_calls_file_sha256")},
        experiment=experiment, stats=stats.as_dict(), created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_json_record(safe, RESULTS_FILENAME, payload, output_root=output_root)
    refreshed = _refresh_exported_artifacts(safe, output_root, metadata, ticker)
    verification = verify_relevance_judgments(run_dir, run_id=safe, ticker=ticker, matches=alpha_matches["matches"], definitions=definitions)
    return {
        "status": "ok", "run_id": safe, "config": config.name, "gateway_mode": config.gateway_mode, "test_data": True,
        "provider_calls": getattr(provider, "calls", None), "stats": stats.as_dict(), "verification": verification.summary(),
        "writes": [f"{LEDGER_DIRNAME}/", RESULTS_FILENAME, *refreshed],
        "ledger_directory": str(Path(ledger_dir).name),
    }


# --------------------------------------------------------------------------------- P4 phase 2 (2026-10-12): plan execution
GATEWAY_LIVE = "LIVE"
EVAL_MODE_LIVE = "LIVE"
EVAL_MODE_REHEARSAL = "SIMULATED_REHEARSAL"
EVAL_MODES = (EVAL_MODE_LIVE, EVAL_MODE_REHEARSAL)
EVAL_RECORD_FILENAME = "execution_record.json"
EVAL_RECORD_SCHEMA = "alpha_relevance_eval_execution.v1"
AUTHORIZATION_CONSUMED_SUFFIX = ".consumed.json"

P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012 = RelevanceExperimentConfig(
    name="p4_relevance_live_small_sample_20261012", enabled=False, gateway_mode=GATEWAY_LIVE, batch_size=ep.LIVE_BATCH_SIZE,
    timeout_seconds=ep.LIVE_TIMEOUT_SECONDS, max_retries=0, max_calls=ep.LIVE_MAX_CALLS_CEILING,
    basis=("P4 phase 2 small-sample real validation of the relevance task. Disabled for every run-level path; usable only through "
           "run_relevance_evaluation_plan with an explicit mode, the frozen sample manifest and plan, and a one-time authorization. "
           "max_calls is the ceiling any plan may request; the plan's own request cap is what an authorization grants."),
)
# 2026-10-12, session 4: the development-set retest of prompt v2 / criterion exp2 on earlier error, flip and control cases. Same call
# settings as the first real run; disabled for every run-level path like it; its own name so its records never pass as the first run.
P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012 = RelevanceExperimentConfig(
    name="p4_relevance_live_dev_retest_v2_20261012", enabled=False, gateway_mode=GATEWAY_LIVE, batch_size=ep.LIVE_BATCH_SIZE,
    timeout_seconds=ep.LIVE_TIMEOUT_SECONDS, max_retries=0, max_calls=ep.RETEST_MAX_CALLS_CEILING,
    basis=("P4 phase 2 development-set retest of prompt v2 / criterion exp2 on cases chosen from the first real run's disagreements, "
           "flips and agreeing controls: a development result, never an independent validation or an acceptance. Disabled for every "
           "run-level path; usable only through run_relevance_evaluation_plan with an explicit mode, its frozen sample manifest and plan, "
           "and a one-time authorization."),
)
# 2026-10-12, session 6: a fixed-scope rule check of prompt v3 / criterion exp3 on development cases (controls and repeats included).
P4_RELEVANCE_LIVE_RULECHECK_V3_20261012 = RelevanceExperimentConfig(
    name="p4_relevance_live_rulecheck_v3_20261012", enabled=False, gateway_mode=GATEWAY_LIVE, batch_size=ep.LIVE_BATCH_SIZE,
    timeout_seconds=ep.LIVE_TIMEOUT_SECONDS, max_retries=0, max_calls=ep.RETEST_MAX_CALLS_CEILING,
    basis=("P4 phase 2 (session 6) fixed-scope rule check of prompt v3 / criterion exp3 on development cases with positive and negative "
           "controls and an identical repeat: whether the clarified rules are executed, and executed the same way twice. A development "
           "result, never an independent validation or an acceptance. Disabled for every run-level path; usable only through "
           "run_relevance_evaluation_plan with an explicit mode, its frozen sample manifest and plan, and a one-time authorization."),
)
EVALUATION_CONFIGS = {config.name: config for config in (P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012, P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012,
                                                         P4_RELEVANCE_LIVE_RULECHECK_V3_20261012)}


class EvaluationRefused(Exception):
    def __init__(self, code: str, **detail: Any) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass
class _EvaluationContext:
    mode: str
    config: RelevanceExperimentConfig
    plan: dict[str, Any]
    manifest: dict[str, Any]
    authorization: dict[str, Any]
    authorization_path: Path
    authorization_sha256: str
    definitions: Mapping[str, AlphaRelevanceDefinition]
    samples: dict[str, dict[str, Any]]
    eval_root: Path
    provider_name: str
    model_name: str
    execution_mode: str
    model_client: Any
    prices: dict[str, Any] | None
    code_identity: dict[str, Any] = field(default_factory=dict)


def _load_json_file(path: Any, code: str) -> tuple[bytes, Any]:
    try:
        raw = Path(path).read_bytes()
        return raw, json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise EvaluationRefused(code, path=str(path)) from exc


def _parse_time(value: Any, code: str) -> datetime:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationRefused(code, value=str(value)) from exc
    if moment.tzinfo is None:
        raise EvaluationRefused(code, value=str(value), detail="a time zone is required")
    return moment


def _check_authorization(auth: Any, plan: Mapping[str, Any], mode: str, now: datetime) -> None:
    if not isinstance(auth, Mapping) or auth.get("schema") != ep.AUTHORIZATION_SCHEMA:
        raise EvaluationRefused("AUTHORIZATION_INVALID")
    if auth.get("mode") != mode:
        raise EvaluationRefused("AUTHORIZATION_MODE_MISMATCH", authorized_mode=auth.get("mode"), requested_mode=mode)
    if mode == EVAL_MODE_LIVE and auth.get("live_authorized") is not True:
        raise EvaluationRefused("LIVE_NOT_AUTHORIZED")
    if mode == EVAL_MODE_REHEARSAL and (auth.get("rehearsal_authorized") is not True or auth.get("live_authorized") is not False):
        raise EvaluationRefused("REHEARSAL_NOT_AUTHORIZED")
    if auth.get("plan_sha256") != plan["plan_sha256"]:
        raise EvaluationRefused("AUTHORIZATION_PLAN_MISMATCH")
    if auth.get("sample_manifest_content_sha256") != plan["sample_manifest"]["content_sha256"]:
        raise EvaluationRefused("AUTHORIZATION_MANIFEST_MISMATCH")
    if auth.get("max_requests") != plan["request_cap"]:
        raise EvaluationRefused("AUTHORIZATION_CAP_MISMATCH", authorized=auth.get("max_requests"), planned=plan["request_cap"])
    if auth.get("quality_thresholds_confirmed") is True and auth.get("quality_thresholds_sha256") != plan["quality_thresholds_sha256"]:
        raise EvaluationRefused("AUTHORIZATION_THRESHOLDS_MISMATCH")
    if mode == EVAL_MODE_LIVE:
        if (auth.get("provider"), auth.get("model")) != (plan["provider"], plan["model"]):
            raise EvaluationRefused("AUTHORIZATION_PROVIDER_MISMATCH")
        cost = auth.get("max_cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not cost > 0:
            raise EvaluationRefused("AUTHORIZATION_COST_LIMIT_MISSING")
    if not str(auth.get("authorized_by") or "").strip():
        raise EvaluationRefused("AUTHORIZATION_SIGNER_MISSING")
    if _parse_time(auth.get("authorized_at"), "AUTHORIZATION_TIME_INVALID") > now:
        raise EvaluationRefused("AUTHORIZATION_TIME_INVALID", detail="authorized_at is in the future")
    if _parse_time(auth.get("valid_until"), "AUTHORIZATION_EXPIRY_INVALID") <= now:
        raise EvaluationRefused("AUTHORIZATION_EXPIRED")


def _build_live_client(*, provider: str, model: str, timeout_seconds: float, max_output_tokens: int, http_client: Any = None) -> Any:
    """The real model client: the server's configured provider / model must be the plan's; the client's own read timeout is the plan's
    timeout and it never retries (the gateway does not either). Building it sends nothing."""
    from comqutor_alpha.structure_engine.week2_llm import (
        resolve_server_week2_settings,  # noqa: PLC0415
    )

    settings = resolve_server_week2_settings()
    if (settings.get("provider"), settings.get("model_name")) != (provider, model):
        raise EvaluationRefused("PROVIDER_MODEL_MISMATCH", configured_provider=settings.get("provider"), configured_model=settings.get("model_name"))
    kwargs: dict[str, Any] = {"provider": provider, "model": model, "base_url": settings.get("base_url"), "timeout": float(timeout_seconds),
                              "max_retries": 0, "max_tokens": int(max_output_tokens)}
    if http_client is not None:
        kwargs["http_client"] = http_client
    try:
        from tradingagents.llm_clients import create_llm_client  # noqa: PLC0415

        return create_llm_client(**kwargs).get_llm()
    except Exception as exc:
        raise EvaluationRefused("LIVE_CLIENT_UNAVAILABLE", error_type=type(exc).__name__) from exc


def _preflight(
    *, plan_path: Any, manifest_path: Any, authorization_path: Any, eval_root: Any, mode: str, config: RelevanceExperimentConfig,
    provider: Any, now: datetime, repo_root: Path, http_client: Any,
) -> _EvaluationContext:
    from comqutor_alpha.consumption_recompute import refuse_real_outputs  # noqa: PLC0415

    if mode not in EVAL_MODES:
        raise EvaluationRefused("EVALUATION_MODE_NOT_SELECTED", allowed=list(EVAL_MODES))
    if EVALUATION_CONFIGS.get(config.name) is not config or config.gateway_mode != GATEWAY_LIVE or config.max_retries != 0:
        raise EvaluationRefused("UNKNOWN_EVALUATION_CONFIG", config=config.name)
    try:
        refuse_real_outputs(eval_root)
    except ValueError as exc:
        raise EvaluationRefused("REFUSED_REAL_OUTPUTS") from exc
    _raw, plan = _load_json_file(plan_path, "PLAN_UNREADABLE")
    if not isinstance(plan, dict) or plan.get("schema") != ep.PLAN_SCHEMA or plan.get("mode") != "LIVE" or plan.get("status") != "PLANNED_NOT_EXECUTED":
        raise EvaluationRefused("PLAN_INVALID")
    if ep.plan_content_sha256(plan) != plan.get("plan_sha256"):
        raise EvaluationRefused("PLAN_HASH_MISMATCH")
    manifest_raw, manifest = _load_json_file(manifest_path, "MANIFEST_UNREADABLE")
    if hashlib.sha256(manifest_raw).hexdigest() != plan["sample_manifest"]["file_sha256"]:
        raise EvaluationRefused("MANIFEST_FILE_MISMATCH")
    if ep.manifest_content_sha256(manifest) != manifest.get("content_sha256") or manifest.get("content_sha256") != plan["sample_manifest"]["content_sha256"]:
        raise EvaluationRefused("MANIFEST_HASH_MISMATCH")
    auth_raw, authorization = _load_json_file(authorization_path, "AUTHORIZATION_UNREADABLE")
    _check_authorization(authorization, plan, mode, now)
    if Path(str(authorization_path) + AUTHORIZATION_CONSUMED_SUFFIX).exists():
        raise EvaluationRefused("AUTHORIZATION_ALREADY_USED")
    settings = plan["call_settings"]
    if (settings.get("batch_size"), float(settings.get("timeout_seconds") or 0), settings.get("max_retries")) != (config.batch_size, float(config.timeout_seconds), 0):
        raise EvaluationRefused("PLAN_CONFIG_MISMATCH")
    if plan.get("experiment_config") is not None and plan["experiment_config"] != config.name:
        raise EvaluationRefused("PLAN_CONFIG_MISMATCH", planned_config=plan["experiment_config"], config=config.name)
    if sum(len(r["batches"]) for r in plan["rounds"]) != plan["request_cap"] or not 0 < plan["request_cap"] <= config.max_calls:
        raise EvaluationRefused("PLAN_CAP_INVALID", request_cap=plan.get("request_cap"), ceiling=config.max_calls)
    identity = ep.code_identity(repo_root)
    planned_files = plan["code_identity"]["files"]
    changed = sorted(p for p in set(planned_files) | set(identity["files"]) if planned_files.get(p) != identity["files"].get(p))
    if changed:
        raise EvaluationRefused("CODE_IDENTITY_MISMATCH", files=changed)
    if task_identity() != plan["task"]:
        raise EvaluationRefused("TASK_IDENTITY_CHANGED")
    try:
        definitions = load_relevance_definitions()
    except RelevanceElementsError as exc:
        raise EvaluationRefused("RELEVANCE_DEFINITIONS_UNAVAILABLE", reason=exc.reason_code) from exc
    if taxonomy_content_version() != plan["taxonomy_content_version"]:
        raise EvaluationRefused("DEFINITION_CHANGED", detail="taxonomy content version")
    try:
        round1 = ep.plan_batches(manifest, definitions, batch_size=config.batch_size, isolate=plan.get("isolated_samples") or (),
                                 exclude=[entry["sample_id"] for entry in plan.get("not_sent") or []])
    except ValueError as exc:
        raise EvaluationRefused(str(exc).split(":", 1)[0]) from exc
    problems = ep.verify_manifest_sources(manifest)
    if problems:
        raise EvaluationRefused("SOURCE_CHANGED", problems=problems[:10], count=len(problems))
    planned_round1 = {b["batch_id"]: b for b in plan["rounds"][0]["batches"]}
    if plan["rounds"][0]["round"] != 1 or round1 != plan["rounds"][0]["batches"]:
        raise EvaluationRefused("PLAN_REQUESTS_DRIFT", round=1)
    for later in plan["rounds"][1:]:
        for batch in later["batches"]:
            original = planned_round1.get(str(batch["batch_id"])[1:])
            if original is None or dict(batch, batch_id=original["batch_id"]) != original:
                raise EvaluationRefused("PLAN_REQUESTS_DRIFT", round=later["round"], batch=batch.get("batch_id"))
    prices = ep._prices(plan["provider"], plan["model"])  # noqa: SLF001
    if mode == EVAL_MODE_REHEARSAL:
        client, provider_name, model_name, execution_mode = provider or SimulatedRelevanceProvider(), SIMULATED_PROVIDER, SIMULATED_MODEL, "test"
    else:
        if provider is not None:
            raise EvaluationRefused("LIVE_PROVIDER_INJECTION_REFUSED")
        if prices is None:
            raise EvaluationRefused("NO_PRICE_ON_RECORD")
        client = _build_live_client(provider=plan["provider"], model=plan["model"], timeout_seconds=settings["timeout_seconds"],
                                    max_output_tokens=settings["max_output_tokens"], http_client=http_client)
        provider_name, model_name, execution_mode = plan["provider"], plan["model"], "live"
    return _EvaluationContext(
        mode=mode, config=config, plan=plan, manifest=manifest, authorization=dict(authorization), authorization_path=Path(authorization_path),
        authorization_sha256=hashlib.sha256(auth_raw).hexdigest(), definitions=definitions,
        samples={s["sample_id"]: s for s in manifest["samples"]}, eval_root=Path(eval_root), provider_name=provider_name, model_name=model_name,
        execution_mode=execution_mode, model_client=client, prices=prices, code_identity=identity,
    )


class _RelevanceOnlyGateway:
    """The only gateway surface an evaluation hands out: the relevance task's prebuilt-prompt call and its finalization. Any other task
    is refused before the shared gateway sees it; no other gateway method exists here."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def invoke_prebuilt_json_prompt(self, *, task: str, **kwargs: Any) -> Any:
        if task != LLM_TASK_NAME:
            raise EvaluationRefused("TASK_NOT_ALLOWED", task=task)
        return self._gateway.invoke_prebuilt_json_prompt(task=task, **kwargs)

    def finalize_semantic_invocation(self, invocation: Any, **kwargs: Any) -> None:
        self._gateway.finalize_semantic_invocation(invocation, **kwargs)


def _request_item(sample: Mapping[str, Any], definitions: Mapping[str, AlphaRelevanceDefinition]) -> RelevanceRequestItem:
    return RelevanceRequestItem(claim_id=sample["claim_id"], alpha_id=sample["target_alpha_id"], ticker=sample["ticker"],
                                claim_text=sample["claim_text"], claim_text_sha256=sample["claim_text_sha256"],
                                definition=definitions[sample["target_alpha_id"]])


def _ledger_calls(ledger_dir: Path) -> list[dict[str, Any]]:
    path = ledger_dir / "llm_semantic_calls.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def _recorded_usage(calls: list[dict[str, Any]]) -> dict[str, int]:
    usage = {"input_tokens": 0, "output_tokens": 0, "calls_with_usage": 0}
    for call in calls:
        tokens = call.get("token_usage") if isinstance(call.get("token_usage"), Mapping) else {}
        if tokens.get("output_tokens") is not None:
            usage["input_tokens"] += int(tokens.get("input_tokens") or 0)
            usage["output_tokens"] += int(tokens["output_tokens"])
            usage["calls_with_usage"] += 1
    return usage


def run_relevance_evaluation_plan(
    *,
    plan_path: Any,
    manifest_path: Any,
    authorization_path: Any,
    eval_root: Any,
    mode: str | None,
    config: RelevanceExperimentConfig = P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012,
    provider: Any = None,
    now: datetime | None = None,
    repo_root: Path | str | None = None,
    clock: Callable[[], float] = time.monotonic,
    _http_client_for_testing: Any = None,
) -> dict[str, Any]:
    """Execute a frozen evaluation plan once (see the module docstring). Every refusal happens before anything is written or sent."""
    now = now or datetime.now(timezone.utc)
    try:
        ctx = _preflight(plan_path=plan_path, manifest_path=manifest_path, authorization_path=authorization_path, eval_root=eval_root,
                         mode=str(mode), config=config, provider=provider, now=now, repo_root=Path(repo_root or ep.REPO_ROOT),
                         http_client=_http_client_for_testing)
    except EvaluationRefused as exc:
        return _fail(exc.code, **exc.detail)
    return _execute_plan(ctx, now=now, clock=clock)


def _execute_plan(ctx: _EvaluationContext, *, now: datetime, clock: Callable[[], float]) -> dict[str, Any]:
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession  # noqa: PLC0415
    from comqutor_alpha.run_provider_stop import RunProviderStop  # noqa: PLC0415
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: PLC0415

    plan, limits, settings = ctx.plan, ctx.plan["stop_conditions"], ctx.plan["call_settings"]
    cpt_min = ep.estimate_basis(plan["reference"])["chars_per_input_token"]["min"]
    eval_id = f"relevance-eval-{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    eval_dir = ctx.eval_root / eval_id
    consumed = Path(str(ctx.authorization_path) + AUTHORIZATION_CONSUMED_SUFFIX)
    with consumed.open("x", encoding="utf-8") as handle:  # the authorization is used once: claimed before anything else is written or sent
        json.dump({"evaluation_id": eval_id, "evaluation_dir": str(eval_dir), "consumed_at": now.isoformat(), "mode": ctx.mode}, handle, indent=1)
    ctx.eval_root.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir()  # never an existing directory: nothing earlier is overwritten
    test_data = ctx.mode == EVAL_MODE_REHEARSAL
    auth = ctx.authorization
    record: dict[str, Any] = {
        "schema": EVAL_RECORD_SCHEMA, "evaluation_id": eval_id, "mode": ctx.mode, "test_data": test_data, "status": "RUNNING",
        "config": ctx.config.as_dict(), "plan_sha256": plan["plan_sha256"], "sample_manifest_content_sha256": plan["sample_manifest"]["content_sha256"],
        "authorization": {"file_sha256": ctx.authorization_sha256, "authorized_by": auth.get("authorized_by"), "authorized_at": auth.get("authorized_at"),
                          "valid_until": auth.get("valid_until"), "max_requests": auth.get("max_requests"), "max_cost_usd": auth.get("max_cost_usd"),
                          "quality_thresholds_confirmed": auth.get("quality_thresholds_confirmed") is True,
                          "quality_thresholds_sha256": auth.get("quality_thresholds_sha256")},
        "provider": ctx.provider_name, "model": ctx.model_name, "execution_mode": ctx.execution_mode,
        "call_settings": settings, "request_cap": plan["request_cap"], "code_identity_at_start": ctx.code_identity,
        "started_at": now.isoformat(), "finished_at": None, "stop": None, "requests_sent": 0, "rounds": [], "batches": [],
        # samples the plan keeps in its table but never sends (each with the reason recorded when the plan was frozen)
        "not_sent_by_plan": [dict(entry) for entry in plan.get("not_sent") or []],
    }
    ep.write_json(eval_dir / EVAL_RECORD_FILENAME, record)

    def batch_bound(prompt_chars: int) -> float:
        """Peak-price cost of one request at its hard bound (input at the lowest measured characters per token, output at the cap)."""
        if ctx.prices is None:
            return 0.0
        return ep.usd(ctx.prices["peak"], (prompt_chars or 0) / cpt_min, settings["max_output_tokens"])

    def spent_usd() -> float:
        """Peak-price cost of what was sent: recorded usage where the ledger has it, the hard bound where it does not (a timed-out
        request may still be billed)."""
        usage = _recorded_usage(all_calls)
        return ep.usd(ctx.prices["peak"], usage["input_tokens"], usage["output_tokens"]) + unbilled if ctx.prices else 0.0

    sent, consecutive_failed, stop = 0, 0, None
    started = clock()
    all_calls: list[dict[str, Any]] = []
    unbilled = 0.0
    for round_plan in plan["rounds"]:
        number = round_plan["round"]
        round_id = f"{eval_id}-r{number}"
        if stop is not None:
            record["rounds"].append({"round": number, "round_run_id": round_id, "status": "NOT_STARTED", "stop": stop})
            record["batches"].extend({"round": number, "batch_id": b["batch_id"], "status": "NOT_SENT", "stop": stop} for b in round_plan["batches"])
            continue
        ledger_dir = eval_dir / round_id / LEDGER_DIRNAME
        ledger_dir.mkdir(parents=True)
        session = SemanticRuntimeSession(run_id=round_id, output_directory=ledger_dir, execution_mode=ctx.execution_mode,
                                         provider=ctx.provider_name, model=ctx.model_name, profile_id=ctx.config.name)
        gateway = Week2LLMGateway(ctx.model_client, run_id=round_id, output_root=str(eval_dir), timeout_seconds=settings["timeout_seconds"],
                                  max_retries=0, max_calls=len(round_plan["batches"]), provider=ctx.provider_name, model_name=ctx.model_name,
                                  semantic_runtime=session)
        stopper = RunProviderStop(round_id)
        gateway.provider_stop = stopper
        items_sent: list[RelevanceRequestItem] = []
        results: dict[tuple[str, str], dict[str, Any]] = {}
        sample_ids: dict[str, str] = {}
        round_sent = 0
        for batch in round_plan["batches"]:
            if stop is None:
                if sent >= plan["request_cap"]:
                    stop = "REQUEST_CAP_REACHED"
                elif consecutive_failed >= limits["consecutive_failed_batches"]:
                    stop = "CONSECUTIVE_FAILED_BATCHES"
                elif clock() - started > limits["wall_clock_limit_minutes"] * 60:
                    stop = "WALL_CLOCK_LIMIT"
                elif not test_data and spent_usd() + batch_bound(batch["prompt_chars"]) > float(auth["max_cost_usd"]):
                    stop = "COST_LIMIT"
            if stop is not None:
                record["batches"].append({"round": number, "batch_id": batch["batch_id"], "status": "NOT_SENT", "stop": stop})
                continue
            items = [_request_item(ctx.samples[sid], ctx.definitions) for sid in batch["sample_ids"]]
            if sha256_canonical_json(batch_payload(items)) != batch["payload_sha256"]:
                stop = "PLAN_REQUESTS_DRIFT"
                record["batches"].append({"round": number, "batch_id": batch["batch_id"], "status": "NOT_SENT", "stop": stop})
                continue
            sent += 1
            round_sent += 1
            record["requests_sent"] = sent
            before = len(_ledger_calls(ledger_dir))
            t0 = clock()
            batch_results, stats = judge_relevance(items, _RelevanceOnlyGateway(gateway), batch_size=len(items), timeout_seconds=settings["timeout_seconds"], max_retries=0,
                                                   execution_policy_source=f"evaluation:{ctx.config.name}:{eval_id}")
            seconds = round(clock() - t0, 3)
            new_calls = _ledger_calls(ledger_dir)[before:]
            all_calls.extend(new_calls)
            billed = [c for c in new_calls if isinstance(c.get("token_usage"), Mapping) and c["token_usage"].get("output_tokens") is not None]
            if not billed and stats.provider_attempts:
                unbilled += batch_bound(batch["prompt_chars"])  # sent, no recorded usage: counted at its hard bound
            results.update(batch_results)
            items_sent.extend(items)
            sample_ids.update({f"{i.claim_id}|{i.alpha_id}": sid for i, sid in zip(items, batch["sample_ids"], strict=True)})
            valid = any(r["state"] in (STATE_JUDGED, STATE_UNRESOLVED) for r in batch_results.values())
            consecutive_failed = 0 if valid else consecutive_failed + 1
            states: dict[str, int] = {}
            for result in batch_results.values():
                states[result["state"]] = states.get(result["state"], 0) + 1
            record["batches"].append({
                "round": number, "batch_id": batch["batch_id"], "status": "SENT", "seconds": seconds, "provider_attempts": stats.provider_attempts,
                "call_ids": sorted({str(r.get("call_id")) for r in batch_results.values() if r.get("call_id")}), "states": states,
                "failure_reasons": stats.as_dict()["failure_reasons"],
            })
            if stats.batches != 1 or stats.provider_attempts > 1:
                stop = "UNPLANNED_REQUEST"
            elif stopper.triggered is not None:
                stop = "PROVIDER_REFUSAL"
            ep.write_json(eval_dir / EVAL_RECORD_FILENAME, record)
        session.finalize_manifest(complete=round_sent == len(round_plan["batches"]))
        ledger = RelevanceLedger.load(eval_dir / round_id)
        experiment = {**ctx.config.as_dict(), "mode": ctx.mode, "provider": ctx.provider_name, "model": ctx.model_name, "test_data": test_data,
                      **({"simulation_rule": _simulation_rule()} if test_data else {})}
        payload = build_results_payload(
            run_id=round_id, ticker="", items=items_sent, results=results, without_definition=[],
            ledger={k: v for k, v in ledger.description().items() if k in ("directory", "integrity", "calls_file_sha256", "manifest_calls_file_sha256")},
            experiment=experiment, stats={"requests_sent": round_sent, "pairs_sent": len(items_sent)}, created_at=datetime.now(timezone.utc).isoformat(),
        )
        payload["ticker"] = None  # an evaluation round spans several tickers: each record's binding carries its own
        payload["evaluation"] = {"evaluation_id": eval_id, "round": number, "plan_sha256": plan["plan_sha256"], "mode": ctx.mode,
                                 "sample_manifest_content_sha256": plan["sample_manifest"]["content_sha256"], "sample_ids": sample_ids}
        with (eval_dir / round_id / RESULTS_FILENAME).open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
        record["rounds"].append({"round": number, "round_run_id": round_id, "status": "COMPLETE" if round_sent == len(round_plan["batches"]) else "PARTIAL",
                                 "requests_sent": round_sent, "ledger_integrity": ledger.integrity})
    usage = _recorded_usage(all_calls)
    record.update({
        "status": "COMPLETED" if stop is None else "STOPPED", "stop": stop, "finished_at": datetime.now(timezone.utc).isoformat(),
        "requests_sent": sent, "recorded_usage": usage,
        "model_identity": {"request_model": plan["model"], **ep.model_names_in_calls(all_calls),
                           "note": ("the request name does not pin the served model version; returned_by_provider is the model field the "
                                    "provider reported in its responses between first_call_at and last_call_at")},
        "cost_usd_recorded_usage": None if ctx.prices is None or test_data else {
            "off_peak": ep.usd(ctx.prices["off_peak"], usage["input_tokens"], usage["output_tokens"]),
            "peak": ep.usd(ctx.prices["peak"], usage["input_tokens"], usage["output_tokens"]),
            "unrecorded_requests_counted_at_hard_bound_usd": round(unbilled, 4)},
    })
    ep.write_json(eval_dir / EVAL_RECORD_FILENAME, record)
    return {"status": "ok" if stop is None else "stopped", "evaluation_id": eval_id, "evaluation_dir": str(eval_dir), "mode": ctx.mode,
            "test_data": test_data, "requests_sent": sent, "request_cap": plan["request_cap"], "stop": stop,
            "rounds": record["rounds"], "recorded_usage": usage}


__all__ = [
    "DEFAULT_CONFIG",
    "EVALUATION_CONFIGS",
    "EVAL_MODES",
    "EVAL_MODE_LIVE",
    "EVAL_MODE_REHEARSAL",
    "EXPERIMENT_CONFIGS",
    "GATEWAY_LIVE",
    "GATEWAY_SIMULATED",
    "P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012",
    "P4_RELEVANCE_LIVE_RULECHECK_V3_20261012",
    "P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012",
    "P4_RELEVANCE_SIMULATED_20261012",
    "SIMULATED_MODEL",
    "EvaluationRefused",
    "RelevanceExperimentConfig",
    "SimulatedRelevanceProvider",
    "judge_run_relevance",
    "run_relevance_evaluation_plan",
]
