"""W7: fixed server Research Profile tests.

Covers: the frozen profile field contract, profile-driven TradingAgents
config construction, the full non-secret profile identity in the request
fingerprint (profile change => fingerprint change => no stale reuse), HTTP
field-injection resistance, credential-gate behavior before any claim, and
secret non-leakage.
"""

from __future__ import annotations

import dataclasses

import pytest

from comqutor_alpha import research_profiles, server_execution
from comqutor_alpha.research_lifecycle import (
    build_research_request_fingerprint,
    build_research_request_identity,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", raising=False)


# ---------------------------------------------------------------------------
# Frozen profile contract
# ---------------------------------------------------------------------------


def test_active_profile_fields_are_frozen():
    profile = research_profiles.get_active_research_profile()
    assert profile.profile_id == "comqutor_anthropic_medium_sonnet46_v1"
    assert profile.display_name == "COMQUTOR Anthropic Medium v1"
    assert profile.llm_provider == "anthropic"
    assert profile.quick_think_llm == "claude-sonnet-4-6"
    assert profile.deep_think_llm == "claude-sonnet-4-6"
    assert profile.backend_url is None
    assert profile.output_language == "English"
    assert profile.max_debate_rounds == 3
    assert profile.max_risk_discuss_rounds == 3


def test_profile_dataclass_is_immutable():
    profile = research_profiles.get_active_research_profile()
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.llm_provider = "openai"  # type: ignore[misc]


def test_profile_config_applies_exactly_the_profile_keys():
    from tradingagents.default_config import DEFAULT_CONFIG

    config = research_profiles.build_profile_tradingagents_config()
    assert config["llm_provider"] == "anthropic"
    assert config["quick_think_llm"] == "claude-sonnet-4-6"
    assert config["deep_think_llm"] == "claude-sonnet-4-6"
    assert config["backend_url"] is None
    assert config["output_language"] == "English"
    assert config["max_debate_rounds"] == 3
    assert config["max_risk_discuss_rounds"] == 3
    for key, value in config.items():
        if key not in research_profiles.PROFILE_CONFIG_KEYS:
            assert value == DEFAULT_CONFIG[key]


def test_profile_config_never_mutates_default_config():
    import copy

    from tradingagents.default_config import DEFAULT_CONFIG

    before = copy.deepcopy(DEFAULT_CONFIG)
    config = research_profiles.build_profile_tradingagents_config()
    config["llm_provider"] = "mutated"
    config["data_vendors"]["core_stock_apis"] = "mutated"
    assert before == DEFAULT_CONFIG


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_provider": "openai"},
        {"llm_provider": ""},
        {"quick_think_llm": ""},
        {"deep_think_llm": "  "},
        {"output_language": ""},
        {"max_debate_rounds": 0},
        {"max_debate_rounds": True},
        {"max_risk_discuss_rounds": -1},
        {"profile_id": ""},
    ],
)
def test_invalid_profile_variants_are_rejected(overrides):
    base = research_profiles.get_active_research_profile()
    broken = dataclasses.replace(base, **overrides)
    with pytest.raises(research_profiles.ResearchProfileError) as exc_info:
        research_profiles.validate_research_profile(broken)
    assert exc_info.value.reason_code == "RESEARCH_PROFILE_INVALID"


def test_display_name_lookup():
    assert (
        research_profiles.display_name_for_profile_id(research_profiles.ACTIVE_PROFILE_ID)
        == "COMQUTOR Anthropic Medium v1"
    )
    assert research_profiles.display_name_for_profile_id("unknown_profile") is None
    assert research_profiles.display_name_for_profile_id(None) is None


# ---------------------------------------------------------------------------
# Profile identity in the request fingerprint
# ---------------------------------------------------------------------------


def test_profile_identity_enters_the_fingerprint():
    payload = {"ticker": "NVDA", "analysis_date": "2026-07-16"}
    identity_without = build_research_request_identity(payload)
    execution_identity = server_execution.build_execution_identity(
        research_profiles.build_profile_tradingagents_config()
    )
    identity_with = build_research_request_identity(
        payload, server_execution_identity=execution_identity
    )
    assert identity_with["profile_id"] == research_profiles.ACTIVE_PROFILE_ID
    assert identity_with["profile_identity"] == research_profiles.build_profile_identity()
    assert build_research_request_fingerprint(identity_with) != build_research_request_fingerprint(
        identity_without
    )


def test_any_profile_field_change_changes_the_fingerprint():
    payload = {"ticker": "NVDA", "analysis_date": "2026-07-16"}
    base_profile = research_profiles.get_active_research_profile()
    base_identity_dict = server_execution.build_execution_identity(
        research_profiles.build_profile_tradingagents_config()
    )
    base_fp = build_research_request_fingerprint(
        build_research_request_identity(payload, server_execution_identity=base_identity_dict)
    )

    for overrides in (
        {"profile_id": "comqutor_anthropic_medium_sonnet46_v2"},
        {"deep_think_llm": "claude-opus-4-8"},
        {"max_debate_rounds": 5},
        {"output_language": "Chinese"},
    ):
        changed_profile = dataclasses.replace(base_profile, **overrides)
        changed_identity_dict = dict(base_identity_dict)
        changed_identity_dict["profile_id"] = changed_profile.profile_id
        changed_identity_dict["profile_identity"] = research_profiles.build_profile_identity(
            changed_profile
        )
        changed_fp = build_research_request_fingerprint(
            build_research_request_identity(
                payload, server_execution_identity=changed_identity_dict
            )
        )
        assert changed_fp != base_fp, overrides


def test_profile_identity_contains_no_secret_or_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-should-never-leak")
    identity = research_profiles.build_profile_identity()
    serialized = str(identity)
    for forbidden in ("sk-test-should-never-leak", "/Users/", "ANTHROPIC", "api_key", "secret"):
        assert forbidden not in serialized


# ---------------------------------------------------------------------------
# HTTP injection resistance + credential gate (full app)
# ---------------------------------------------------------------------------


def test_http_model_and_config_fields_cannot_override_the_profile(tmp_path, monkeypatch):
    """A request stuffed with every forbidden knob still resolves to the
    fixed profile: the ResearchRequest model has no such fields, so Pydantic
    drops them before the server ever sees them."""
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        # Stop the job manager so the claimed run fails fast instead of
        # spawning a real worker -- this test only inspects the claim.
        client.app.state.job_manager.shutdown()
        client.app.state.job_manager = None
        response = client.post(
            "/api/research",
            json={
                "ticker": "NVDA",
                "llm_provider": "evil-provider",
                "quick_think_llm": "evil-quick",
                "deep_think_llm": "evil-deep",
                "backend_url": "http://evil.example.com",
                "output_language": "Klingon",
                "research_depth": "maximum",
                "max_debate_rounds": 99,
                "max_risk_discuss_rounds": 99,
                "reasoning_effort": "max",
                "api_key": "evil-key",
                "config": {"llm_provider": "evil"},
                "allow_real_tradingagents_run": True,
            },
        )
    # The request was accepted as an ordinary real submission (then failed
    # only because the job manager is down) -- never rejected/honored for
    # the injected fields.
    body = response.json()
    assert body.get("error_code") in (None, "JOB_MANAGER_UNAVAILABLE")

    repo = build_write_repository_from_env(str(tmp_path))
    records = repo.list_research_run_records(limit=10)
    assert len(records) == 1
    # The claimed row records only the server-fixed identity labels.
    assert records[0]["provider_identity"] == "anthropic"
    assert records[0]["model_identity"] == "claude-sonnet-4-6:claude-sonnet-4-6"


def test_post_returns_503_before_claim_when_credential_missing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/research", json={"ticker": "NVDA"})

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "REAL_RUN_CREDENTIAL_MISSING"
    assert "ANTHROPIC" not in str(body)
    # No queued row was ever created.
    repo = build_write_repository_from_env(str(tmp_path))
    assert repo.list_research_run_records(limit=10) == []


def test_claimed_run_records_profile_id_in_progress_row(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        client.app.state.job_manager.shutdown()
        client.app.state.job_manager = None
        response = client.post("/api/research", json={"ticker": "NVDA"})

    run_id = response.json()["run_id"]
    repo = build_write_repository_from_env(str(tmp_path))
    progress = repo.get_research_progress(run_id)
    assert progress is not None
    assert progress["profile_id"] == research_profiles.ACTIVE_PROFILE_ID
