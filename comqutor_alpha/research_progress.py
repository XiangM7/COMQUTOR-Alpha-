"""W7: Real research-run progress contract and reporter.

Frozen stage vocabulary, deterministic percent boundaries, and a
``ResearchProgressReporter`` that persists progress through the repository's
monotonic ``research_run_progress`` methods.

Progress is only ever advanced by a *real* pipeline milestone -- a
TradingAgents analyst actually finishing its report, the structured-claims
adapter actually succeeding, the conflict pipeline actually persisting --
never by a timer, never by an automatic per-second increment. A progress
write failure is logged safely (exception type name only) and swallowed:
missing telemetry must never fail the run or fabricate progress, and the
lifecycle row (``research_runs``) remains the terminal source of truth.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# The frozen public analyst vocabulary, in canonical order. "sentiment" is
# the only public name that maps to a different internal TradingAgents key
# ("social") -- that mapping happens exclusively at the TradingAgentsGraph
# boundary (see runners/tradingagents_runner.py) and never appears here, in
# the API, or in the UI.
PUBLIC_ANALYST_ORDER: tuple[str, ...] = ("market", "sentiment", "news", "fundamentals")

ANALYST_STAGES: dict[str, str] = {
    "market": "market_analysis",
    "sentiment": "sentiment_analysis",
    "news": "news_analysis",
    "fundamentals": "fundamentals_analysis",
}

# Percent boundaries for every non-analyst stage. Analyst stages divide the
# 10-50 window evenly across the actually-selected analysts (see
# ResearchProgressReporter.record_analyst_completed).
STAGE_PERCENT: dict[str, int] = {
    "request_validated": 5,
    "queued": 8,
    "initializing": 10,
    "research_debate": 58,
    "trading_plan": 64,
    "risk_review": 70,
    "raw_outputs_saved": 74,
    "structured_claims": 79,
    "alpha_mapping": 84,
    "structure_graph": 89,
    "activation_scoring": 92,
    "conflict_analysis": 96,
    "result_persistence": 98,
    "result_assembly": 99,
    "completed": 100,
    "completed_partial": 100,
}

ANALYST_WINDOW: tuple[int, int] = (10, 50)

# Stages that each represent one completed unit of work. total_units =
# len(selected analysts) + len(UNIT_STAGES).
UNIT_STAGES: tuple[str, ...] = (
    "research_debate",
    "trading_plan",
    "risk_review",
    "raw_outputs_saved",
    "structured_claims",
    "alpha_mapping",
    "structure_graph",
    "activation_scoring",
    "conflict_analysis",
    "result_persistence",
    "result_assembly",
)

# Safe, user-facing one-liners. Never a traceback, exception text, path,
# DSN, provider response, or credential.
STAGE_MESSAGES: dict[str, str] = {
    "queued": "Research request is queued.",
    "initializing": "Initializing the research run.",
    "market_analysis": "Running the Market Analyst.",
    "sentiment_analysis": "Running the Sentiment Analyst.",
    "news_analysis": "Running the News Analyst.",
    "fundamentals_analysis": "Running the Fundamentals Analyst.",
    "research_debate": "Running the research debate.",
    "trading_plan": "Drafting the trading plan.",
    "risk_review": "Performing the risk review.",
    "raw_outputs_saved": "Saving agent outputs.",
    "structured_claims": "Extracting structured claims.",
    "alpha_mapping": "Mapping claims to Alpha structures.",
    "structure_graph": "Building the structure graph.",
    "activation_scoring": "Scoring Alpha activation.",
    "conflict_analysis": "Analyzing structural conflicts.",
    "result_persistence": "Persisting results.",
    "result_assembly": "Assembling the final research result.",
}

POST_STAGE_TRANSITIONS: dict[str, str] = {
    "research_debate": "trading_plan",
    "trading_plan": "risk_review",
    "risk_review": "raw_outputs_saved",
    "raw_outputs_saved": "structured_claims",
    "structured_claims": "alpha_mapping",
    "alpha_mapping": "structure_graph",
    "structure_graph": "activation_scoring",
    "activation_scoring": "conflict_analysis",
    "conflict_analysis": "result_persistence",
    "result_persistence": "result_assembly",
}

# profile_id recorded for offline (fixture-driven) runs, which never touch a
# provider and never contribute ETA samples (ETA history is restricted to
# execution_mode == "real").
OFFLINE_PROFILE_ID = "offline_fixture_v1"


def canonical_public_analysts(selected_analysts: Any) -> list[str]:
    """Deduplicated, canonically-ordered public analyst list (market,
    sentiment, news, fundamentals). Unknown names are dropped here (the
    submission gate has already rejected them for real runs)."""
    requested = {str(item).strip() for item in (selected_analysts or []) if str(item or "").strip()}
    return [analyst for analyst in PUBLIC_ANALYST_ORDER if analyst in requested]


def normalize_public_analysts(
    selected_analysts: Any,
    *,
    default_if_missing: bool = True,
) -> list[str]:
    """Validate and canonicalize the public analyst selection.

    This is the strict request/fingerprint boundary. Unknown values (including
    TradingAgents' internal ``social`` name), scalar strings, and an empty
    explicit selection are rejected instead of being silently dropped.
    """
    raw = PUBLIC_ANALYST_ORDER if selected_analysts is None and default_if_missing else selected_analysts
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("INVALID_ANALYST_SELECTION: selected_analysts must be a list")

    requested: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if not name:
            continue
        if name not in PUBLIC_ANALYST_ORDER:
            raise ValueError(
                "INVALID_ANALYST_SELECTION: selected_analysts contains an unsupported analyst"
            )
        requested.add(name)
    if not requested:
        raise ValueError("INVALID_ANALYST_SELECTION: at least one analyst must be selected")
    return [analyst for analyst in PUBLIC_ANALYST_ORDER if analyst in requested]


def compute_total_units(selected_analysts: Any) -> int:
    analysts = canonical_public_analysts(selected_analysts)
    return max(1, len(analysts)) + len(UNIT_STAGES)


def analyst_progress_percent(completed_count: int, analyst_count: int) -> int:
    """Percent after ``completed_count`` of ``analyst_count`` selected
    analysts have genuinely finished: the 10-50 window divided evenly. With
    four analysts that is 20/30/40/50; with two, 30/50."""
    low, high = ANALYST_WINDOW
    if analyst_count <= 0:
        return low
    completed = max(0, min(completed_count, analyst_count))
    return low + round((high - low) * completed / analyst_count)


class ResearchProgressReporter:
    """Persists real progress milestones for one run. Every write is
    best-effort: a database hiccup is logged (exception type name only) and
    swallowed -- telemetry loss must never fail the research run itself, and
    it must never fabricate progress either (nothing is retried with made-up
    values; the next real milestone simply writes the next real state)."""

    def __init__(
        self,
        repository: Any,
        run_id: str,
        *,
        profile_id: str,
        selected_analysts: Any,
    ) -> None:
        self._repository = repository
        self._run_id = run_id
        self._profile_id = str(profile_id or OFFLINE_PROFILE_ID)
        self._analysts = canonical_public_analysts(selected_analysts)
        self._total_units = compute_total_units(selected_analysts)
        self._completed_units = 0
        self._progress_percent = STAGE_PERCENT["queued"]
        self._reached: set[str] = set()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def total_units(self) -> int:
        return self._total_units

    def _guarded(self, description: str, call, *args, **kwargs):
        try:
            return call(*args, **kwargs)
        except Exception as exc:
            logger.warning(
                "research progress write failed (run_id=%s, step=%s, exc_type=%s)",
                self._run_id,
                description,
                type(exc).__name__,
            )
            return None

    def initialize(self) -> None:
        """Idempotent: creates the row at queued/8 if absent; never resets
        progress an earlier writer already recorded."""
        self._guarded(
            "initialize",
            self._repository.initialize_research_progress,
            self._run_id,
            profile_id=self._profile_id,
            total_units=self._total_units,
            current_stage="queued",
            progress_percent=STAGE_PERCENT["queued"],
            progress_message=STAGE_MESSAGES["queued"],
        )

    def _write_current_stage(self, stage: str, *, percent: int | None = None) -> None:
        if percent is not None:
            self._progress_percent = max(self._progress_percent, percent)
        self._guarded(
            stage,
            self._repository.update_research_progress,
            self._run_id,
            progress_percent=self._progress_percent,
            current_stage=stage,
            completed_units=self._completed_units,
            progress_message=STAGE_MESSAGES.get(stage),
        )

    def record_stage_started(self, stage: str) -> None:
        """Record a stage as current without claiming that it completed."""
        marker = f"started:{stage}"
        if marker in self._reached or stage not in STAGE_MESSAGES:
            return
        self._reached.add(marker)
        self._write_current_stage(stage)

    def record_analyst_started(self, public_analyst: str) -> None:
        """Switch the current stage to a selected analyst without advancing units."""
        if public_analyst not in self._analysts:
            return
        marker = f"started:analyst:{public_analyst}"
        if marker in self._reached:
            return
        self._reached.add(marker)
        self._write_current_stage(
            ANALYST_STAGES[public_analyst],
            percent=ANALYST_WINDOW[0],
        )

    def record_analyst_completed(self, public_analyst: str) -> None:
        """One selected analyst's report genuinely finished for the first
        time. Duplicate completions of the same analyst never advance
        anything."""
        if public_analyst not in self._analysts:
            return
        marker = f"analyst:{public_analyst}"
        if marker in self._reached:
            return
        self._reached.add(marker)
        self._completed_units = min(self._completed_units + 1, self._total_units)
        completed_analysts = sum(1 for a in self._analysts if f"analyst:{a}" in self._reached)
        percent = analyst_progress_percent(completed_analysts, len(self._analysts))
        if completed_analysts < len(self._analysts):
            next_analyst = next(
                analyst
                for analyst in self._analysts
                if f"analyst:{analyst}" not in self._reached
            )
            next_stage = ANALYST_STAGES[next_analyst]
        else:
            next_stage = "research_debate"
        self._write_current_stage(next_stage, percent=percent)

    def record_stage_completed(self, stage: str) -> None:
        """Advance a completed post-analysis milestone to its next stage."""
        if stage not in POST_STAGE_TRANSITIONS or stage in self._reached:
            return
        self._reached.add(stage)
        self._completed_units = min(self._completed_units + 1, self._total_units)
        self._write_current_stage(POST_STAGE_TRANSITIONS[stage], percent=STAGE_PERCENT[stage])

    def record_stage(self, stage: str) -> None:
        """Compatibility wrapper for existing milestone call sites."""
        if stage == "initializing":
            self.record_stage_started(stage)
            return
        self.record_stage_completed(stage)

    def record_terminal(self, status: str, *, message: str | None = None) -> None:
        """Mirror the lifecycle terminal outcome into the progress row:
        completed/partial reach 100 with their own distinct stage; failed
        preserves the last real percentage."""
        if status == "completed":
            self._guarded(
                "completed", self._repository.mark_research_progress_completed, self._run_id
            )
        elif status == "partial":
            self._guarded(
                "completed_partial",
                self._repository.mark_research_progress_completed,
                self._run_id,
                partial=True,
            )
        else:
            self._guarded(
                "failed",
                self._repository.mark_research_progress_failed,
                self._run_id,
                progress_message=message,
            )


__all__ = [
    "PUBLIC_ANALYST_ORDER",
    "ANALYST_STAGES",
    "STAGE_PERCENT",
    "ANALYST_WINDOW",
    "UNIT_STAGES",
    "STAGE_MESSAGES",
    "POST_STAGE_TRANSITIONS",
    "OFFLINE_PROFILE_ID",
    "canonical_public_analysts",
    "normalize_public_analysts",
    "compute_total_units",
    "analyst_progress_percent",
    "ResearchProgressReporter",
]
