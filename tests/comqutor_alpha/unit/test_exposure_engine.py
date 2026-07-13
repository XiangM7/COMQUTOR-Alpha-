from __future__ import annotations

import pytest

from comqutor_alpha.structure_engine.exposure_engine import ExposureEngine
from comqutor_alpha.structure_engine.structure_schema import ExposureStatus


@pytest.mark.unit
def test_explicit_nvda_seed_uses_decomposable_formula() -> None:
    result = ExposureEngine.from_yaml().calculate(
        ticker="nvda",
        alpha_id="A101",
        current_evidence=0.8,
        agent_confidence=0.9,
        evidence_references=["claim:one"],
    )
    assert result.status == ExposureStatus.SEEDED
    assert result.historical_mapping == 0.95
    assert result.exposure_score == pytest.approx(0.95 * 0.5 + 0.8 * 0.3 + 0.9 * 0.2)


@pytest.mark.unit
@pytest.mark.parametrize(("ticker", "alpha_id"), [("QQQ", "A001"), ("NVDA", "A001")])
def test_missing_seed_returns_no_seed_without_guess(ticker, alpha_id) -> None:
    result = ExposureEngine.from_yaml().calculate(
        ticker=ticker,
        alpha_id=alpha_id,
        current_evidence=0.8,
        agent_confidence=0.9,
    )
    assert result.status == ExposureStatus.NO_SEED
    assert result.historical_mapping is None
    assert result.exposure_score is None
