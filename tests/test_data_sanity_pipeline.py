"""Data Sanity v1 pipeline orchestration tests. Fake provider only -- zero
network. Also verifies the sidecar never blocks Research completion and
never mutates any artifact it does not own."""

from __future__ import annotations

import datetime as dt
import json

from comqutor_alpha.data_sanity.pipeline import run_data_sanity_stage
from comqutor_alpha.data_sanity.yfinance_provider import MarketDataProviderError


class _FakeProvider:
    def __init__(self, rows=None, raise_error=False, version="fake-1.0"):
        self.rows = rows if rows is not None else []
        self.raise_error = raise_error
        self.call_count = 0
        self._version = version

    def get_history_rows(self, ticker, start_date, end_exclusive):
        self.call_count += 1
        if self.raise_error:
            raise MarketDataProviderError("DATA_SANITY_PROVIDER_UNAVAILABLE")
        return self.rows

    def provider_version(self):
        return self._version


def _clean_row(date):
    return {
        "date": date, "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0,
        "adjusted_close": 102.0, "volume": 1000, "dividend": 0.0, "stock_split": 0.0, "capital_gain": 0.0,
    }


def _seed_run(tmp_path, run_id, ticker="MU", analysis_date="2026-07-24", with_structured=True):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "analysis_date": analysis_date}), encoding="utf-8"
    )
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "agent_outputs": []}), encoding="utf-8"
    )
    if with_structured:
        (run_dir / "structured_agent_outputs.json").write_text(
            json.dumps({"run_id": run_id, "ticker": ticker, "records": []}), encoding="utf-8"
        )
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "matches": []}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "nodes": [], "edges": []}), encoding="utf-8"
    )
    return run_dir


class TestEnabledDisabled:
    def test_enabled_calls_fake_provider_exactly_once(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-a"
        _seed_run(tmp_path, run_id)
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        payload = run_data_sanity_stage(
            run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24)
        )
        assert provider.call_count == 1
        assert payload["status"] == "ok"
        assert (tmp_path / run_id / "market_data_snapshot.json").exists()
        assert (tmp_path / run_id / "data_sanity.json").exists()

    def test_disabled_makes_zero_provider_calls(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMQUTOR_DATA_SANITY_ENABLED", raising=False)
        run_id = "run-b"
        _seed_run(tmp_path, run_id)
        provider = _FakeProvider()
        payload = run_data_sanity_stage(run_id, tmp_path, provider=provider)
        assert provider.call_count == 0
        assert payload["status"] == "disabled"
        # Disabled strategy is consistent: still writes the artifact so API/
        # UI can distinguish disabled from not-yet-generated/unavailable.
        assert (tmp_path / run_id / "data_sanity.json").exists()
        assert not (tmp_path / run_id / "market_data_snapshot.json").exists()


class TestNonBlockingFailure:
    def test_provider_failure_produces_unavailable_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-c"
        _seed_run(tmp_path, run_id)
        provider = _FakeProvider(raise_error=True)
        payload = run_data_sanity_stage(
            run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24)
        )
        assert payload["status"] == "unavailable"
        assert payload["warnings"][0]["code"] == "DATA_SANITY_PROVIDER_UNAVAILABLE"

    def test_unexpected_internal_error_never_propagates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-d"
        _seed_run(tmp_path, run_id)

        class _BrokenProvider:
            def get_history_rows(self, *args, **kwargs):
                raise ValueError("unexpected bug, not a MarketDataProviderError")

        # Must not raise -- always degrades to a safe unavailable artifact.
        payload = run_data_sanity_stage(run_id, tmp_path, provider=_BrokenProvider())
        assert payload["status"] == "unavailable"

    def test_at_most_one_provider_attempt_per_run_no_retry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-e"
        _seed_run(tmp_path, run_id)
        provider = _FakeProvider(raise_error=True)
        run_data_sanity_stage(run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24))
        assert provider.call_count == 1


class TestReportedPriceSkipWhenNoStructuredClaims:
    def test_missing_structured_agent_outputs_skips_reported_price_check_without_failing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-f"
        _seed_run(tmp_path, run_id, with_structured=False)
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        payload = run_data_sanity_stage(
            run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24)
        )
        assert payload["status"] == "ok"
        reported_check = next(c for c in payload["checks"] if c["name"] == "reported_price_cross_check")
        assert reported_check["status"] == "skipped"
        assert payload["summary"]["reported_price_check_count"] == 0


class TestArtifactAtomicityAndIsolation:
    def test_artifact_is_valid_complete_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-g"
        _seed_run(tmp_path, run_id)
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        run_data_sanity_stage(run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24))
        with (tmp_path / run_id / "data_sanity.json").open() as f:
            reloaded = json.load(f)
        assert reloaded["schema_version"] == "comqutor.data_sanity.v1"

    def test_does_not_rewrite_existing_artifacts(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-h"
        run_dir = _seed_run(tmp_path, run_id)
        before = {
            name: (run_dir / name).read_text(encoding="utf-8")
            for name in (
                "metadata.json",
                "raw_agent_outputs.json",
                "structured_agent_outputs.json",
                "alpha_matches.json",
                "extracted_structures.json",
            )
        }
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        run_data_sanity_stage(run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24))
        for name, content in before.items():
            assert (run_dir / name).read_text(encoding="utf-8") == content, f"{name} was rewritten"

    def test_does_not_touch_activation_or_conflict_inputs(self, tmp_path, monkeypatch):
        """alpha_matches.json/extracted_structures.json feed Activation and
        the Structure Graph -- Data Sanity must never read-modify-write
        them."""
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-i"
        run_dir = _seed_run(tmp_path, run_id)
        before_matches = (run_dir / "alpha_matches.json").read_text(encoding="utf-8")
        before_structures = (run_dir / "extracted_structures.json").read_text(encoding="utf-8")
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        run_data_sanity_stage(run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24))
        assert (run_dir / "alpha_matches.json").read_text(encoding="utf-8") == before_matches
        assert (run_dir / "extracted_structures.json").read_text(encoding="utf-8") == before_structures


class TestInputContract:
    def test_ticker_mismatch_short_circuits_before_provider_call(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-j"
        run_dir = _seed_run(tmp_path, run_id, ticker="MU")
        (run_dir / "raw_agent_outputs.json").write_text(
            json.dumps({"run_id": run_id, "ticker": "SNDK", "agent_outputs": []}), encoding="utf-8"
        )
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        payload = run_data_sanity_stage(run_id, tmp_path, provider=provider)
        assert provider.call_count == 0
        assert payload["status"] == "critical"
        assert payload["warnings"][0]["code"] == "TICKER_METADATA_MISMATCH"

    def test_invalid_analysis_date_short_circuits_before_provider_call(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-k"
        _seed_run(tmp_path, run_id, analysis_date="07/24/2026")
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        payload = run_data_sanity_stage(run_id, tmp_path, provider=provider)
        assert provider.call_count == 0
        assert payload["status"] == "critical"
        assert payload["warnings"][0]["code"] == "INVALID_ANALYSIS_DATE_FOR_DATA_SANITY"

    def test_ticker_fallback_to_raw_agent_outputs_when_metadata_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("COMQUTOR_DATA_SANITY_ENABLED", "true")
        run_id = "run-l"
        run_dir = tmp_path / run_id
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(
            json.dumps({"run_id": run_id, "analysis_date": "2026-07-24"}), encoding="utf-8"
        )
        (run_dir / "raw_agent_outputs.json").write_text(
            json.dumps({"run_id": run_id, "ticker": "MU", "agent_outputs": []}), encoding="utf-8"
        )
        provider = _FakeProvider(rows=[_clean_row("2026-07-24")])
        payload = run_data_sanity_stage(
            run_id, tmp_path, provider=provider, current_utc_date=dt.date(2026, 7, 24)
        )
        assert payload["ticker"] == "MU"
        assert provider.call_count == 1
