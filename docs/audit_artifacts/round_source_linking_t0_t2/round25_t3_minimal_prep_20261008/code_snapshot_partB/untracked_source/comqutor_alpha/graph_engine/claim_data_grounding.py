"""T1 closure: deterministic grounding of a claim's numbers to the SAVED data cells of the sources it links to.

Two narrow jobs, both read-only over material the run already saved (no Provider, no network, no model):

1. :func:`ground_claim` -- which saved observations (source, line item, period, value) the numbers a claim states
   actually are. A number is matched at the precision the claim itself states it (``$10.3B`` is a one-decimal-billion
   statement, ``$10,253M`` a whole-million one), and a number that matches more than one distinct observation is
   AMBIGUOUS and creates no data point -- a missing edge is always safer than a wrong one.
2. :func:`derive_calculations` -- re-computation of a few named metrics the claim states as percentages (gross /
   operating / net margin, and the percent change between two observations the claim itself quotes) from the cells
   of the same sources. A reproduced calculation proves the ARITHMETIC only; it never says the surrounding
   statement is true, and it never changes verified-support eligibility.

On top of that, :func:`dependency_anchors` records which claims are derived expressions of the SAME saved
observations: claim B depends on claim A when every observation B uses is also one A uses. Sharing a source, or
sharing only some observations, is NOT dependency -- one financial snapshot backs many different facts.

Scope (deliberately small, per the T1 closure instruction): this is not a general semantic de-duplication system.
It never reads claim wording beyond its numbers, never calls a model, and only fires for claims that carry a
VALID source link to a source whose own saved data contains the stated numbers.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

CLAIM_DATA_GROUNDING_VERSION = "claim_data_points.v1"
DERIVED_CALCULATION_VERSION = "derived_calculation.v1"
# The run-metadata value that switches the dependency pass on (absent -> legacy grouping, byte-identical).
FACT_DEPENDENCY_CONTRACT = "claim_data_points.v1"
# Written on each alpha_matches record (in memory only) by :func:`annotate_matches_with_data_points`.
MATCH_DATA_POINTS_KEY = "grounded_data_points"

SCOPE_NOTE_ARITHMETIC_ONLY = (
    "Arithmetic reproduced from the saved rows only; this does not verify the rest of the statement."
)

# ---------------------------------------------------------------------------
# Number tokens in claim text
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(r"\[\s*fragment_?id\s*:[^\]]*\]|\[\s*source_?id\s*:[^\]]*\]", re.IGNORECASE)
_SOURCE_ID_RE = re.compile(r"\bsrc_?[0-9a-f]{16}(?::frag:\d+)?", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_PERIOD_LABEL_RE = re.compile(r"\b(?:Q[1-4]|FY|H[12])\s*'?\d{2,4}\b|\bQ[1-4]\b", re.IGNORECASE)
_NUMBER_RE = re.compile(
    r"(?P<sign>[+\-−–])?\s*[$€£]?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>%|[MBKT](?![A-Za-z])|(?i:bn|billion|million)(?![A-Za-z])|x(?![A-Za-z]))?"
)
# "swung from negative $134M": the sign is stated as a word. Only the word immediately before the number counts; the
# hyphen / en-dash are NOT read as a minus sign (an en-dash is far more often a range, "$7,685M–$11,536M").
_NEGATIVE_WORD_RE = re.compile(r"\b(?:negative|minus)\s*$", re.IGNORECASE)
_UNIT_SCALE = {"m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "k": 1e3, "t": 1e12}
_DECLINE_CUES = re.compile(r"\b(?:fell|fall|falls|declin\w*|drop\w*|decreas\w*|down|lower|contract\w*|slid\w*|shrank|shrink\w*)\b", re.IGNORECASE)


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: float
    decimals: int
    unit: str  # "", "%", "m", "b", "k", "t", "x" (normalized lower-case; M/B/K/T kept distinct from words)
    explicit_sign: str  # "", "+", "-"
    candidates: tuple[tuple[float, float], ...]  # (scaled value, absolute tolerance)

    @property
    def is_percent(self) -> bool:
        return self.unit == "%"


def _clean_text(text: str) -> str:
    for pattern in (_MARKER_RE, _SOURCE_ID_RE, _DATE_RE, _PERIOD_LABEL_RE):
        text = pattern.sub(" ", text)
    return text


def _informative(unit: str, decimals: int, digits: int, value: float) -> bool:
    """Small bare integers (``3``, ``26``) and years carry no locating information; everything else may."""
    if unit in ("m", "b", "k", "t", "million", "billion", "bn"):
        return True
    if unit == "%":
        return decimals >= 1
    if unit == "x":
        return decimals >= 1 or value >= 100
    if decimals > 0:
        return digits >= 3
    return value >= 100 and not 1990 <= value <= 2100


def extract_number_tokens(text: str) -> list[NumberToken]:
    """Number tokens a claim states, each with the scaled values (and half-unit tolerances) it can denote."""
    tokens: list[NumberToken] = []
    cleaned = _clean_text(str(text or ""))
    for match in _NUMBER_RE.finditer(cleaned):
        num_str = match.group("num")
        try:
            value = float(num_str.replace(",", ""))
        except ValueError:
            continue
        decimals = len(num_str.split(".")[1]) if "." in num_str else 0
        unit_raw = match.group("unit") or ""
        unit = unit_raw.lower() if unit_raw not in ("%",) else "%"
        if unit in ("million",):
            unit = "m"
        elif unit in ("billion", "bn"):
            unit = "b"
        digits = len(re.sub(r"\D", "", num_str))
        if not _informative(unit, decimals, digits, value):
            continue
        half = 0.5 * 10 ** (-decimals)
        if unit == "%":
            candidates = ((value / 100.0, half / 100.0),)
        elif unit in _UNIT_SCALE:
            scale = _UNIT_SCALE[unit]
            candidates = ((value * scale, half * scale),)
        elif unit == "x":
            candidates = ((value, half),)
        else:
            candidate_list = [(value, half)]
            if decimals == 0 and value >= 100:
                # a bare "11,536" next to a "$" or "vs" is conventionally $ millions in these reports
                candidate_list += [(value * 1e6, half * 1e6), (value * 1e3, half * 1e3), (value * 1e9, half * 1e9)]
            candidates = tuple(candidate_list)
        sign = match.group("sign") or ""
        explicit = "-" if sign in ("-", "−", "–") else ("+" if sign == "+" else "")
        raw = match.group(0).strip()
        if not sign and _NEGATIVE_WORD_RE.search(cleaned[max(0, match.start() - 16):match.start()]):
            explicit, raw = "-", "negative " + raw
            candidates = tuple((-scaled, tolerance) for scaled, tolerance in candidates)
        tokens.append(
            NumberToken(raw=raw, value=value, decimals=decimals, unit=unit,
                        explicit_sign=explicit, candidates=candidates)
        )
    return tokens


# ---------------------------------------------------------------------------
# Saved data cells of a source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataCell:
    source_id: str
    label: str
    period: str | None
    value: float
    unit: str | None
    kind: str  # statement_row | scalar_field | market_value
    fragment_id: str | None = None
    content_hash: str | None = None

    @property
    def observation_key(self) -> str:
        """Label-independent identity: the same value stored under several labels for the same source and period
        (e.g. Total Revenue and Operating Revenue) is ONE observation."""
        return f"{self.source_id}|{self.period or ''}|{self.value!r}"


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def iter_source_cells(source: Mapping[str, Any]) -> list[DataCell]:
    """Every numeric cell this source's own saved ``data_snapshot`` carries. Never invents a cell."""
    snapshot = source.get("data_snapshot")
    if not isinstance(snapshot, Mapping):
        return []
    source_id = str(source.get("source_id") or "")
    fragment_id = source.get("fragment_id")
    content_hash = source.get("content_hash")
    cells: list[DataCell] = []
    rows: dict[str, Mapping[str, Any]] = {}
    all_items = snapshot.get("all_line_items")
    if isinstance(all_items, Mapping):
        rows.update({str(k): v for k, v in all_items.items() if isinstance(v, Mapping)})
    primary, periods = snapshot.get("line_item"), snapshot.get("periods")
    if isinstance(primary, str) and isinstance(periods, Mapping) and primary not in rows:
        rows[primary] = periods
    units = snapshot.get("line_item_units") if isinstance(snapshot.get("line_item_units"), Mapping) else {}
    for label, per_period in rows.items():
        for period, raw_value in per_period.items():
            number = _as_number(raw_value)
            if number is None:
                continue
            cells.append(DataCell(source_id, label, str(period), number, units.get(label) or source.get("unit"),
                                  "statement_row", fragment_id, content_hash))
    if rows:
        return cells
    field_units = snapshot.get("field_units") if isinstance(snapshot.get("field_units"), Mapping) else {}
    for key, raw_value in snapshot.items():
        if key in ("field_units", "currency", "requested_analysis_date"):
            continue
        if isinstance(raw_value, Mapping):  # market snapshot: ohlcv / indicators
            for sub_key, sub_value in raw_value.items():
                number = _as_number(sub_value)
                if number is not None:
                    cells.append(DataCell(source_id, f"{key}.{sub_key}", source.get("observation_date"), number,
                                          source.get("unit"), "market_value", fragment_id, content_hash))
            continue
        number = _as_number(raw_value)
        if number is not None and not isinstance(raw_value, str):
            cells.append(DataCell(source_id, str(key), source.get("observation_date"), number,
                                  field_units.get(key) or source.get("unit"), "scalar_field", fragment_id, content_hash))
    return cells


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataPoint:
    observation_key: str
    source_id: str
    label: str
    aliases: tuple[str, ...]
    period: str | None
    value: float
    unit: str | None
    token: str
    kind: str
    fragment_id: str | None
    content_hash: str | None
    role: str = "stated"  # stated | derived_input

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_key": self.observation_key, "source_id": self.source_id, "label": self.label,
            "aliases": list(self.aliases), "period": self.period, "value": self.value, "unit": self.unit,
            "token": self.token, "kind": self.kind, "fragment_id": self.fragment_id,
            "content_hash": self.content_hash, "role": self.role,
        }


@dataclass(frozen=True)
class DerivedCalculation:
    calc_id: str
    metric: str
    formula: str
    inputs: tuple[DataPoint, ...]
    computed: float
    stated: float
    stated_token: str
    precision_decimals: int
    unit: str
    comparison: str | None
    status: str = "REPRODUCED"
    scope_note: str = SCOPE_NOTE_ARITHMETIC_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "calc_id": self.calc_id, "version": DERIVED_CALCULATION_VERSION, "metric": self.metric,
            "formula": self.formula, "inputs": [p.to_dict() for p in self.inputs], "computed": self.computed,
            "stated": self.stated, "stated_token": self.stated_token, "precision_decimals": self.precision_decimals,
            "unit": self.unit, "comparison": self.comparison, "status": self.status, "scope_note": self.scope_note,
        }


@dataclass
class ClaimGrounding:
    claim_id: str
    source_ids: tuple[str, ...]
    data_points: list[DataPoint] = field(default_factory=list)
    ambiguous_tokens: list[dict[str, Any]] = field(default_factory=list)
    unmatched_tokens: list[str] = field(default_factory=list)
    derived_calculations: list[DerivedCalculation] = field(default_factory=list)
    unreproduced_percent_tokens: list[str] = field(default_factory=list)

    @property
    def stated_keys(self) -> tuple[str, ...]:
        """Observations the claim literally states (its numbers, matched to saved cells)."""
        return tuple(sorted({p.observation_key for p in self.data_points if p.role == "stated"}))

    @property
    def input_keys(self) -> tuple[str, ...]:
        """Observations the claim relies on: what it states plus the inputs of any calculation reproduced for it."""
        return tuple(sorted({p.observation_key for p in self.data_points}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CLAIM_DATA_GROUNDING_VERSION, "claim_id": self.claim_id, "source_ids": list(self.source_ids),
            "data_points": [p.to_dict() for p in self.data_points],
            "ambiguous_tokens": self.ambiguous_tokens, "unmatched_tokens": self.unmatched_tokens,
            "derived_calculations": [c.to_dict() for c in self.derived_calculations],
            "unreproduced_percent_tokens": self.unreproduced_percent_tokens,
        }


def _claim_source_ids(record: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    if record.get("source_link_status") == "VALID":
        for candidate in [record.get("linked_source_id"), *(record.get("linked_source_ids") or [])]:
            if isinstance(candidate, str) and candidate and candidate not in ids:
                ids.append(candidate)
    return ids


def _matches(cell_value: float, candidate: float, tolerance: float) -> bool:
    return abs(cell_value - candidate) <= tolerance + 1e-9 * max(1.0, abs(candidate))


def _point_from_cells(cells: Sequence[DataCell], token: str, primary_labels: Mapping[str, str | None]) -> DataPoint:
    labels = sorted({c.label for c in cells})
    preferred = [lab for lab in labels if lab == primary_labels.get(cells[0].source_id)]
    label = preferred[0] if preferred else labels[0]
    chosen = next(c for c in cells if c.label == label)
    return DataPoint(
        observation_key=chosen.observation_key, source_id=chosen.source_id, label=label,
        aliases=tuple(lab for lab in labels if lab != label), period=chosen.period, value=chosen.value,
        unit=chosen.unit, token=token, kind=chosen.kind, fragment_id=chosen.fragment_id,
        content_hash=chosen.content_hash,
    )


def _period_gap_label(older: str | None, newer: str | None) -> str | None:
    from datetime import date

    try:
        d_old, d_new = date.fromisoformat(str(older)[:10]), date.fromisoformat(str(newer)[:10])
    except ValueError:
        return None
    days = (d_new - d_old).days
    if 350 <= days <= 380:
        return "YoY"
    if 80 <= days <= 100:
        return "QoQ"
    return f"{days}d"


# metric keyword -> (metric id, numerator labels, denominator labels). Labels are the yfinance statement row names.
_MARGIN_METRICS = (
    (re.compile(r"gross\s+margin", re.IGNORECASE), "gross_margin", ("Gross Profit",), ("Total Revenue", "Operating Revenue")),
    (re.compile(r"operating\s+margin", re.IGNORECASE), "operating_margin", ("Operating Income",), ("Total Revenue", "Operating Revenue")),
    (re.compile(r"(?:net|profit)\s+margin", re.IGNORECASE), "net_margin", ("Net Income", "Net Income Common Stockholders"), ("Total Revenue", "Operating Revenue")),
)


def _row(cells_by_source: Mapping[str, Sequence[DataCell]], source_id: str, labels: Iterable[str]) -> dict[str, DataCell]:
    for label in labels:
        row = {c.period: c for c in cells_by_source.get(source_id, ()) if c.label == label and c.period}
        if row:
            return row
    return {}


def derive_calculations(
    claim_text: str,
    tokens: Sequence[NumberToken],
    data_points: Sequence[DataPoint],
    cells_by_source: Mapping[str, Sequence[DataCell]],
    source_ids: Sequence[str],
    claim_id: str,
) -> tuple[list[DerivedCalculation], list[str]]:
    """Reproduce, from the saved cells only, the percentages ``claim_text`` states. Returns ``(calculations,
    percent tokens that could not be reproduced)``. Only REPRODUCED calculations are recorded."""
    calculations: list[DerivedCalculation] = []
    unreproduced: list[str] = []
    percent_tokens = [t for t in tokens if t.is_percent]
    if not percent_tokens:
        return calculations, unreproduced
    decline_cue = bool(_DECLINE_CUES.search(claim_text))
    for index, token in enumerate(percent_tokens):
        stated_fraction = token.value / 100.0
        tol = 0.5 * 10 ** (-token.decimals) / 100.0
        found: DerivedCalculation | None = None

        # (1) named margin metrics, only when the claim itself names the metric
        for pattern, metric, numerators, denominators in _MARGIN_METRICS:
            if not pattern.search(claim_text):
                continue
            for source_id in source_ids:
                numerator = _row(cells_by_source, source_id, numerators)
                denominator = _row(cells_by_source, source_id, denominators)
                hits = [
                    p for p in sorted(set(numerator) & set(denominator))
                    if denominator[p].value and _matches(numerator[p].value / denominator[p].value, stated_fraction, tol)
                ]
                if len(hits) != 1:
                    continue
                period = hits[0]
                inputs = tuple(
                    DataPoint(c.observation_key, c.source_id, c.label, (), c.period, c.value, c.unit,
                              token.raw, c.kind, c.fragment_id, c.content_hash, role="derived_input")
                    for c in (numerator[period], denominator[period])
                )
                found = DerivedCalculation(
                    calc_id=f"{claim_id}#calc{len(calculations) + 1}", metric=metric,
                    formula=f"{inputs[0].label} / {inputs[1].label} @ {period}", inputs=inputs,
                    computed=round(numerator[period].value / denominator[period].value * 100.0, 4),
                    stated=token.value, stated_token=token.raw, precision_decimals=token.decimals,
                    unit="percent", comparison=None,
                )
                break
            if found:
                break

        # (2) percent change between two observations of the same row that the claim itself quotes
        if found is None:
            by_label: dict[tuple[str, str], list[DataPoint]] = {}
            for point in data_points:
                if point.kind == "statement_row" and point.period and point.role == "stated":
                    by_label.setdefault((point.source_id, point.label), []).append(point)
            for (_source_id, _label), points in sorted(by_label.items()):
                ordered = sorted({p.period: p for p in points}.values(), key=lambda p: p.period or "")
                for i, older in enumerate(ordered):
                    for newer in ordered[i + 1:]:
                        if not older.value:
                            continue
                        change = (newer.value - older.value) / abs(older.value)
                        explicit_negative = token.explicit_sign == "-"
                        direction_ok = (change >= 0 and not explicit_negative) or (change < 0 and (explicit_negative or decline_cue))
                        if direction_ok and _matches(abs(change), stated_fraction, tol):
                            found = DerivedCalculation(
                                calc_id=f"{claim_id}#calc{len(calculations) + 1}", metric="percent_change",
                                formula=f"({newer.label} @ {newer.period} - {older.label} @ {older.period}) / {older.label} @ {older.period}",
                                inputs=(
                                    DataPoint(**{**older.__dict__, "role": "derived_input", "token": token.raw}),
                                    DataPoint(**{**newer.__dict__, "role": "derived_input", "token": token.raw}),
                                ),
                                computed=round(change * 100.0, 4), stated=-token.value if change < 0 else token.value,
                                stated_token=token.raw, precision_decimals=token.decimals, unit="percent",
                                comparison=_period_gap_label(older.period, newer.period),
                            )
                            break
                    if found:
                        break
                if found:
                    break

        if found is not None:
            calculations.append(found)
        else:
            unreproduced.append(token.raw)
    return calculations, unreproduced


def ground_claim(
    record: Mapping[str, Any],
    sources_by_id: Mapping[str, Mapping[str, Any]],
    *,
    cells_cache: dict[str, list[DataCell]] | None = None,
) -> ClaimGrounding:
    """Ground one structured record. A record without a VALID source link, or whose sources carry no saved data
    cells, simply grounds to nothing (never an error)."""
    claim_id = str(record.get("claim_id") or "")
    source_ids = [sid for sid in _claim_source_ids(record) if sid in sources_by_id]
    grounding = ClaimGrounding(claim_id=claim_id, source_ids=tuple(source_ids))
    if not source_ids:
        return grounding
    cache = cells_cache if cells_cache is not None else {}
    cells_by_source: dict[str, list[DataCell]] = {}
    primary_labels: dict[str, str | None] = {}
    for sid in source_ids:
        if sid not in cache:
            cache[sid] = iter_source_cells(sources_by_id[sid])
        cells_by_source[sid] = cache[sid]
        snapshot = sources_by_id[sid].get("data_snapshot")
        primary_labels[sid] = snapshot.get("line_item") if isinstance(snapshot, Mapping) else None
    all_cells = [cell for sid in source_ids for cell in cells_by_source[sid]]
    if not all_cells:
        return grounding

    claim_text = str(record.get("claim") or record.get("evidence") or "")
    tokens = extract_number_tokens(claim_text)
    seen: dict[str, DataPoint] = {}
    for token in tokens:
        hit_cells: list[DataCell] = []
        for candidate, tolerance in token.candidates:
            hit_cells.extend(c for c in all_cells if _matches(c.value, candidate, tolerance))
        keys = {c.observation_key for c in hit_cells}
        if not keys:
            grounding.unmatched_tokens.append(token.raw)
        elif len(keys) > 1:
            grounding.ambiguous_tokens.append({"token": token.raw, "candidate_observations": sorted(keys)[:6]})
        else:
            point = _point_from_cells([c for c in hit_cells if c.observation_key in keys], token.raw, primary_labels)
            seen.setdefault(point.observation_key, point)
    grounding.data_points = list(seen.values())
    calculations, unreproduced = derive_calculations(
        claim_text, tokens, grounding.data_points, cells_by_source, source_ids, claim_id
    )
    grounding.derived_calculations = calculations
    grounding.unreproduced_percent_tokens = unreproduced
    # a number the claim states that no saved cell holds is reported as such -- except the ones a reproduced calculation
    # (or the "could not be reproduced" list) already accounts for
    accounted = Counter([c.stated_token for c in calculations] + list(unreproduced))
    not_found: list[str] = []
    for raw in grounding.unmatched_tokens:
        if accounted[raw] > 0:
            accounted[raw] -= 1
        else:
            not_found.append(raw)
    grounding.unmatched_tokens = not_found
    # inputs of a reproduced calculation are observations the claim relies on as well
    for calc in calculations:
        for point in calc.inputs:
            seen.setdefault(point.observation_key, point)
    grounding.data_points = list(seen.values())
    return grounding


def ground_records(
    records: Iterable[Mapping[str, Any]], sources: Sequence[Mapping[str, Any]] | None
) -> dict[str, ClaimGrounding]:
    """Ground every record that has a VALID link; ``{claim_id: ClaimGrounding}``."""
    sources_by_id = {str(s.get("source_id")): s for s in (sources or []) if isinstance(s, Mapping) and s.get("source_id")}
    cache: dict[str, list[DataCell]] = {}
    out: dict[str, ClaimGrounding] = {}
    for record in records:
        if not isinstance(record, Mapping) or record.get("source_link_status") != "VALID":
            continue
        grounding = ground_claim(record, sources_by_id, cells_cache=cache)
        if grounding.data_points or grounding.ambiguous_tokens or grounding.derived_calculations:
            out[grounding.claim_id] = grounding
    return out


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def dependency_anchors(
    inputs_by_claim: Mapping[str, Iterable[str]], stated_by_claim: Mapping[str, Iterable[str]]
) -> dict[str, str]:
    """``{claim_id: anchor_claim_id}`` for every claim that is a derived expression of ANOTHER claim's saved
    observations: all the observations B relies on (``inputs_by_claim``) are among those A literally states
    (``stated_by_claim``). Only what a claim states can anchor others -- a claim that merely used an observation as
    the input of a ratio it quotes does not "contain" it. The anchor is the CLOSEST such claim (fewest stated
    observations; ties -> smallest claim id), so two unrelated claims that both contain a third claim's
    observations are never chained together through it. Mutual restatements (each one's inputs equal the other's
    statement) anchor on the smaller claim id.

    Three guards keep "shares some data" from becoming "is the same fact":

    * a claim that relies on a SINGLE observation never anchors on another claim. Two statements that merely quote
      the same number (a forward EPS, a price) can assert entirely different things about it; only a claim built on
      SEVERAL of another claim's observations -- a comparison, a change or an interpretation of the same series, e.g.
      claim 33 on claim 31 -- is a derived expression of it;
    * a claim derived from the statements of SEVERAL different claims (e.g. a margin quoted from one claim's
      revenue and another's gross profit) has no single anchor and is left alone: attaching it to either would
      merge two facts that are not the same fact;
    * two claims that each state the very same set of several observations are restatements of each other, and the
      smaller claim id anchors (never both ways).
    """
    inputs = {cid: frozenset(obs) for cid, obs in inputs_by_claim.items() if obs}
    stated = {cid: frozenset(obs) for cid, obs in stated_by_claim.items() if obs}
    anchors: dict[str, str] = {}
    for claim_id, needed in sorted(inputs.items()):
        if len(needed) < 2:
            continue
        best: tuple[int, str] | None = None
        for other_id, other_stated in stated.items():
            if other_id == claim_id or not needed <= other_stated:
                continue
            mutual = needed == other_stated and inputs.get(other_id) == stated.get(claim_id) == needed
            if mutual and other_id > claim_id:
                continue
            key = (len(other_stated), other_id)
            if best is None or key < best:
                best = key
        if best is not None:
            anchors[claim_id] = best[1]
    return anchors


def shared_input_claims(
    inputs_by_claim: Mapping[str, Iterable[str]], claim_id: str
) -> list[str]:
    """Claims that share at least one saved observation with ``claim_id`` but are neither anchors nor dependents
    of it. Recorded for display only -- shared data is not the same fact."""
    sets = {cid: frozenset(obs) for cid, obs in inputs_by_claim.items() if obs}
    mine = sets.get(claim_id)
    if not mine:
        return []
    return sorted(
        other for other, theirs in sets.items()
        if other != claim_id and mine & theirs and not (mine <= theirs or theirs <= mine)
    )


def grounded_points(record: Mapping[str, Any], which: str) -> tuple[str, ...]:
    """The observation keys stamped on a match record by :func:`annotate_matches_with_data_points`
    (``which`` = ``"stated"`` or ``"inputs"``); ``()`` when the run did not opt in."""
    value = record.get(MATCH_DATA_POINTS_KEY) if isinstance(record, Mapping) else None
    items = value.get(which) if isinstance(value, Mapping) else None
    return tuple(str(item) for item in items) if isinstance(items, list) else ()


def annotate_matches_with_data_points(
    alpha_matches_payload: Any, records: Sequence[Mapping[str, Any]] | None, sources: Sequence[Mapping[str, Any]] | None
) -> int:
    """In-memory only: stamps ``grounded_data_points`` (``{"stated": [...], "inputs": [...]}``, sorted observation
    keys) on each matched record whose claim grounds to at least one saved observation, so the three grouping
    callers can hand them to the shared Evidence Fact Index. Returns the number of records annotated. Never
    persisted by this function; absent -> legacy grouping."""
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    if not isinstance(matches, list) or not records or not sources:
        return 0
    groundings = ground_records(records, sources)
    annotated = 0
    for match in matches:
        if not isinstance(match, dict):
            continue
        grounding = groundings.get(str(match.get("claim_id") or ""))
        if grounding and grounding.input_keys:
            match[MATCH_DATA_POINTS_KEY] = {"stated": list(grounding.stated_keys), "inputs": list(grounding.input_keys)}
            annotated += 1
    return annotated


__all__ = [
    "CLAIM_DATA_GROUNDING_VERSION",
    "DERIVED_CALCULATION_VERSION",
    "FACT_DEPENDENCY_CONTRACT",
    "MATCH_DATA_POINTS_KEY",
    "ClaimGrounding",
    "DataCell",
    "DataPoint",
    "DerivedCalculation",
    "NumberToken",
    "annotate_matches_with_data_points",
    "dependency_anchors",
    "derive_calculations",
    "extract_number_tokens",
    "ground_claim",
    "ground_records",
    "grounded_points",
    "iter_source_cells",
    "shared_input_claims",
]
