"""Approved deterministic offline fixtures for the W5 local demo and Golden tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEMO_ANALYSIS_DATE = "2026-06-30"
DEMO_SELECTED_ANALYSTS = ("market", "news", "fundamentals", "sentiment")

_NVDA_OFFLINE_OUTPUTS = (
    {
        "agent": "news_agent",
        "raw_output": (
            "AI training demand is accelerating and cloud providers are increasing AI capex, "
            "which is driving GPU demand higher for NVIDIA. Enterprise AI applications and AI "
            "agents are expanding inference workloads across cloud platforms. Media attention "
            "and theme flows are chasing AI stocks, creating narrative momentum around NVIDIA."
        ),
    },
    {
        "agent": "fundamental_agent",
        "raw_output": (
            "AI training demand keeps accelerating as hyperscaler AI capex remains elevated, "
            "reinforcing GPU demand for NVDA. Datacenter spending is expanding because AI "
            "buildout requires more power, cooling, and networking capacity. Revenue guidance "
            "was raised due to strong customer demand and bookings are strengthening."
        ),
    },
    {
        "agent": "sentiment_agent",
        "raw_output": (
            "NVIDIA should benefit as artificial intelligence demand keeps accelerator supply "
            "tight. AI stocks are rising due to strong investor attention and narrative "
            "momentum around the AI theme."
        ),
    },
    {
        "agent": "technical_agent",
        "raw_output": (
            "The semiconductor chip cycle is turning upward as inventories normalize and "
            "orders recover. NVDA is priced for perfection and rich valuation creates "
            "downside risk that could trigger multiple compression if growth decelerates."
        ),
    },
)

# Synthetic macro claims, not a real market report for QQQ.
_QQQ_OFFLINE_OUTPUTS = (
    {
        "agent": "news_agent",
        "raw_output": (
            "Fed officials are preparing to cut rates as inflation cools, which should help "
            "long-duration technology shares in QQQ. Liquidity conditions are improving as "
            "reserves rise and cash rotates back into risk assets."
        ),
    },
    {
        "agent": "fundamental_agent",
        "raw_output": (
            "Treasury yields are falling and discount rates are easing, so growth multiples "
            "have room to expand across the Nasdaq. Credit spreads are widening and PMIs are "
            "weakening, raising recession risk for high beta equities."
        ),
    },
    {
        "agent": "sentiment_agent",
        "raw_output": (
            "Risk appetite is returning because monetary liquidity is less tight than last "
            "quarter, supporting broad participation in QQQ constituents."
        ),
    },
    {
        "agent": "technical_agent",
        "raw_output": (
            "The easing cycle from the Fed is supporting duration sensitive growth names. "
            "Liquidity expansion is broadening participation beyond mega cap tech."
        ),
    },
)


def approved_demo_outputs(ticker: str) -> list[dict[str, Any]]:
    """Return a mutable copy while keeping one canonical fixture definition."""
    normalized = str(ticker).strip().upper()
    if normalized == "NVDA":
        return deepcopy(list(_NVDA_OFFLINE_OUTPUTS))
    if normalized == "QQQ":
        return deepcopy(list(_QQQ_OFFLINE_OUTPUTS))
    raise ValueError("UNAPPROVED_DEMO_TICKER")


__all__ = [
    "DEMO_ANALYSIS_DATE",
    "DEMO_SELECTED_ANALYSTS",
    "approved_demo_outputs",
]
