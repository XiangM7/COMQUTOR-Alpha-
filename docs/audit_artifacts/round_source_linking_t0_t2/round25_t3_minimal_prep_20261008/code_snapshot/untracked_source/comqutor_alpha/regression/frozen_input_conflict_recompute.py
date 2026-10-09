"""T2 (2026-10-07): FROZEN-INPUT conflict recompute (COMQUTOR Alpha next-round task sheet, T0 "冻结输入重算" execution type; T2 first item).

Why this exists. T2 made ``A102__A304`` and ``A201__A304`` evaluable by declaring them reciprocally in the taxonomy. A Type A re-evaluation (the six-ticker
formal verdicts) reads each saved run's OWN ``conflicts.json``, which was written before the taxonomy declared those two pairs, so on every historical
run they show ``not_reached`` - the new pairs had never been looked at against real inputs. This module re-runs ONLY the deterministic conflict
detector on a saved run's own saved ``alpha_activations.json`` + ``alpha_matches.json`` (nothing else: no model, no search, no fetch, no replay of the
research) under the CURRENT taxonomy and sets the result next to what the run saved.

It writes nothing into the run directory. ``detect_alpha_conflicts`` is a pure function (no filesystem / network / clock / randomness), so the result is
a function of the saved inputs and the taxonomy alone.

Evidence gate: these runs predate source linking, so their claims carry no source-link or content-support fields. The recompute therefore runs with
``require_verified_evidence_gate=False`` (the same setting that produced the saved files); the document says so. It is not evidence about the
verified-support standard.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts

SCHEMA_VERSION = "comqutor.frozen_input_conflict_recompute.v1"
EXECUTION_TYPE = "FROZEN_INPUT_RECOMPUTE"
NEWLY_EVALUABLE_PAIRS = ("A102__A304", "A201__A304")  # declared reciprocally by the T2 taxonomy change (content_version 1.1.0)
DOCUMENT_FILENAME = "frozen_input_conflict_recompute.json"
TABLE_FILENAME = "frozen_input_conflict_recompute.md"


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pair_id(alpha_a: Any, alpha_b: Any) -> str | None:
    if not alpha_a or not alpha_b:
        return None
    left, right = sorted((str(alpha_a), str(alpha_b)))
    return f"{left}__{right}"


def _pairs(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """pair id -> the admissibility facts the payload itself recorded for it (outcome, status, reason codes, supporting-fact counts, scores)."""
    pairs: dict[str, dict[str, Any]] = {}
    for entry in (payload.get("arbitration") or {}).get("candidate_evaluations") or ():
        if not isinstance(entry, Mapping):
            continue
        pair = _pair_id(entry.get("alpha_a"), entry.get("alpha_b"))
        if pair is None:
            continue
        admissibility = entry.get("admissibility") or {}
        pairs[pair] = {
            "status": admissibility.get("status"),
            "outcome": entry.get("outcome"),
            "reason_codes": list(admissibility.get("reason_codes") or ()),
            "bull_supporting_evidence_count": admissibility.get("bull_supporting_evidence_count"),
            "bear_supporting_evidence_count": admissibility.get("bear_supporting_evidence_count"),
            "bull_score": admissibility.get("bull_score"),
            "bear_score": admissibility.get("bear_score"),
        }
    return pairs


def _admitted(payload: Mapping[str, Any]) -> list[str]:
    return sorted({c["conflict_id"] for c in (payload.get("conflicts") or ()) if isinstance(c, Mapping) and c.get("conflict_id")})


def _main(payload: Mapping[str, Any]) -> str | None:
    main = payload.get("main_conflict")
    return main.get("conflict_id") if isinstance(main, Mapping) else None


def recompute_saved_run(*, ticker: str, run_id: str, runs_root: str | Path, taxonomy_path: str | Path | None = None) -> dict[str, Any]:
    run_dir = Path(runs_root) / run_id
    activation = (_read_json(run_dir / "alpha_activations.json") or {}).get("activation")
    matches = (_read_json(run_dir / "alpha_matches.json") or {}).get("matches")
    metadata = _read_json(run_dir / "metadata.json") or {}
    saved = _read_json(run_dir / "conflicts.json")
    if activation is None or matches is None or saved is None:
        return {"ticker": ticker, "run_id": run_id, "status": "SAVED_INPUTS_NOT_FOUND", "missing": [
            name for name, value in (("alpha_activations.json", activation), ("alpha_matches.json", matches), ("conflicts.json", saved)) if value is None
        ]}
    try:
        taxonomy = load_alpha_taxonomy(taxonomy_path) if taxonomy_path is not None else None
        recomputed = detect_alpha_conflicts(
            run_id=str(metadata.get("run_id") or run_id),
            ticker=str(metadata.get("ticker") or ticker),
            activation_payload=activation,
            alpha_matches=matches,
            taxonomy=taxonomy,
        )
    except Exception as exc:  # reported in the document, never hidden and never turned into a result
        return {"ticker": ticker, "run_id": run_id, "status": "RECOMPUTE_ERROR", "error": f"{type(exc).__name__}: {exc}"[:400]}

    saved_pairs, new_pairs = _pairs(saved), _pairs(recomputed)
    saved_admitted, new_admitted = _admitted(saved), _admitted(recomputed)
    pairs = {}
    for pair in sorted(set(saved_pairs) | set(new_pairs) | set(NEWLY_EVALUABLE_PAIRS)):
        new = new_pairs.get(pair)
        pairs[pair] = {
            "saved_status": (saved_pairs.get(pair) or {}).get("status") or ("admitted" if pair in saved_admitted else "not_reached"),
            "recomputed_status": (new or {}).get("status") or "not_reached",
            "recomputed": new,
        }
    return {
        "ticker": ticker,
        "run_id": run_id,
        "status": "RECOMPUTED",
        "execution_type": EXECUTION_TYPE,
        "provider_calls": 0,
        "model_calls": 0,
        "analysis_date": metadata.get("analysis_date"),
        "inputs": ["alpha_activations.json", "alpha_matches.json"],
        "require_verified_evidence_gate": False,
        "saved": {"admitted": saved_admitted, "main_conflict": _main(saved)},
        "recomputed": {"admitted": new_admitted, "main_conflict": _main(recomputed)},
        "changed": {
            "admitted_added": sorted(set(new_admitted) - set(saved_admitted)),
            "admitted_removed": sorted(set(saved_admitted) - set(new_admitted)),
            "main_conflict_changed": _main(saved) != _main(recomputed),
        },
        "pairs": pairs,
        "newly_evaluable_pairs": {pair: pairs[pair] for pair in NEWLY_EVALUABLE_PAIRS},
    }


def recompute_saved_runs(
    runs: Mapping[str, str], *, runs_root: str | Path, execution_id: str, taxonomy_path: str | Path | None = None, generated_at: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_id": execution_id,
        "execution_type": EXECUTION_TYPE,
        "generated_at": generated_at,
        "provider_calls": 0,
        "model_calls": 0,
        "note": (
            "Only the deterministic conflict detector is re-run, on each saved run's own saved alpha_activations.json and alpha_matches.json, under the "
            "current taxonomy. Nothing is written into the run directories. The runs predate source linking, so the verified-evidence gate is off, exactly "
            "as when their conflicts.json was written: this says what the evidence-driven admissibility gate does with the new pairs on real saved "
            "inputs, not whether that evidence is verified."
        ),
        "newly_evaluable_pairs": list(NEWLY_EVALUABLE_PAIRS),
        "tickers": {
            ticker: recompute_saved_run(ticker=ticker, run_id=run_id, runs_root=runs_root, taxonomy_path=taxonomy_path)
            for ticker, run_id in runs.items()
        },
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def render_markdown(document: Mapping[str, Any]) -> str:
    """Built from ``document`` alone."""
    out = [
        f"# Frozen-input conflict recompute — {document.get('execution_id')}",
        "",
        f"- Execution type: **{document.get('execution_type')}** | Provider calls: **{document.get('provider_calls')}** | Model calls: **{document.get('model_calls')}** | Generated: {document.get('generated_at')}",
        f"- {document.get('note')}",
        "",
        "## 1. Admitted conflicts: what the run saved vs what the current taxonomy yields on the same saved inputs",
        "",
        "| Ticker | Run | Status | Saved admitted | Recomputed admitted | Added | Main conflict (saved → recomputed) |",
        "|---|---|---|---|---|---|---|",
    ]
    tickers = document.get("tickers") or {}
    for ticker, entry in tickers.items():
        if entry.get("status") != "RECOMPUTED":
            out.append(f"| {ticker} | {(entry.get('run_id') or '')[:8]} | {entry.get('status')} {_cell(entry.get('error') or entry.get('missing') or '')} | | | | |")
            continue
        out.append(
            "| " + " | ".join(
                _cell(c)
                for c in (
                    ticker,
                    entry["run_id"][:8],
                    entry["status"],
                    ", ".join(entry["saved"]["admitted"]) or "—",
                    ", ".join(entry["recomputed"]["admitted"]) or "—",
                    ", ".join(entry["changed"]["admitted_added"]) or "—",
                    f"{entry['saved']['main_conflict']} → {entry['recomputed']['main_conflict']}",
                )
            ) + " |"
        )
    out += ["", "## 2. The two pairs T2 made evaluable (A102__A304, A201__A304)", "",
            "| Ticker | Pair | Saved | Recomputed | Reason codes (recomputed) | Supporting facts bull / bear | Scores bull / bear |", "|---|---|---|---|---|---|---|"]
    for ticker, entry in tickers.items():
        if entry.get("status") != "RECOMPUTED":
            continue
        for pair, info in entry["newly_evaluable_pairs"].items():
            new = info.get("recomputed") or {}
            out.append(
                "| " + " | ".join(
                    _cell(c)
                    for c in (
                        ticker,
                        pair,
                        info["saved_status"],
                        info["recomputed_status"],
                        ", ".join(new.get("reason_codes") or ()) or ("—" if new else "(pair never reached arbitration: an Alpha side is not active enough)"),
                        f"{new.get('bull_supporting_evidence_count')} / {new.get('bear_supporting_evidence_count')}" if new else "",
                        f"{new.get('bull_score')} / {new.get('bear_score')}" if new else "",
                    )
                ) + " |"
            )
    out.append("")
    return "\n".join(out) + "\n"


def write_outputs(document: Mapping[str, Any], out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} already holds files; choose a new --out-dir")
    out.mkdir(parents=True, exist_ok=True)
    paths = {"document": out / DOCUMENT_FILENAME, "table": out / TABLE_FILENAME}
    paths["document"].write_text(json.dumps(document, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    paths["table"].write_text(render_markdown(document), encoding="utf-8")
    return paths


__all__ = ["NEWLY_EVALUABLE_PAIRS", "recompute_saved_run", "recompute_saved_runs", "render_markdown", "write_outputs"]
