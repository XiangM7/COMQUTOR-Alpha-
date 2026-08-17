"""Build the single-file Development-Plan LLM boundary audit report.

This is a documentation-only builder. It reads the existing audit report and
artifacts, runs the read-only boundary verification, and writes one portable
Markdown snapshot under ``docs/``. It does not import production modules or
write to production/output directories.
"""

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "docs/development_plan_llm_boundary_audit_consolidated.md"
MAIN_REPORT = Path("docs/development_plan_llm_boundary_audit.md")
VERIFICATION_SCRIPT = Path("scripts/audit_llm_boundary.py")


@dataclass(frozen=True)
class Artifact:
    title: str
    path: Path
    kind: str
    purpose: str


ARTIFACTS = (
    Artifact(
        "Development Plan Source Inventory",
        Path("docs/audit_artifacts/development_plan_source_inventory.json"),
        "json",
        "Canonical-source search record and corroborating repository references.",
    ),
    Artifact(
        "Semantic Pipeline Call Graph",
        Path("docs/audit_artifacts/semantic_pipeline_call_graph.json"),
        "json",
        "Live, historical-read, replay, and test/fake execution paths.",
    ),
    Artifact(
        "LLM Call-Site Inventory",
        Path("docs/audit_artifacts/llm_call_site_inventory.json"),
        "json",
        "Confirmed COMQUTOR LLM call sites and their boundary properties.",
    ),
    Artifact(
        "LLM Prompt Inventory",
        Path("docs/audit_artifacts/llm_prompt_inventory.csv"),
        "csv",
        "Prompt families, contracts, validation, retries, and reachability.",
    ),
    Artifact(
        "Provider-Call Baseline",
        Path("docs/audit_artifacts/provider_call_baseline.json"),
        "json",
        "Provider-call granularity, budgets, replay behavior, cache, and unknowns.",
    ),
    Artifact(
        "Structured Adapter Gap Matrix",
        Path("docs/audit_artifacts/structured_adapter_gap_matrix.csv"),
        "csv",
        "Field-level comparison for Development Plan section 5.1.",
    ),
    Artifact(
        "Alpha Mapper Gap Matrix",
        Path("docs/audit_artifacts/alpha_mapper_gap_matrix.csv"),
        "csv",
        "Tier-by-tier comparison for Development Plan section 5.2.",
    ),
    Artifact(
        "Structure Extractor Gap Matrix",
        Path("docs/audit_artifacts/structure_extractor_gap_matrix.csv"),
        "csv",
        "Edge-source and fallback comparison for Development Plan section 5.3.",
    ),
    Artifact(
        "TradingAgents Modification Audit",
        Path("docs/audit_artifacts/tradingagents_modification_audit.csv"),
        "csv",
        "On-disk hooks, runtime prompt changes, and added-call assessment.",
    ),
    Artifact(
        "Deterministic Core Boundary Audit",
        Path("docs/audit_artifacts/deterministic_core_boundary_audit.json"),
        "json",
        "Module-by-module LLM import and free-text boundary findings.",
    ),
    Artifact(
        "Replay Semantic Reproducibility",
        Path("docs/audit_artifacts/replay_semantic_reproducibility.json"),
        "json",
        "Zero-Provider guarantees and LLM-tier replay limitations.",
    ),
    Artifact(
        "Development Plan Compliance Matrix",
        Path("docs/audit_artifacts/development_plan_compliance_matrix.csv"),
        "csv",
        "Requirement-level status, severity, evidence, and recommended phase.",
    ),
    Artifact(
        "Proposed Phase 1-3 Migration Plan",
        Path("docs/audit_artifacts/proposed_phase_1_3_plan.json"),
        "json",
        "Gap remediation, compatibility, tests, cutover, and product decisions.",
    ),
)


def _read(relative_path: Path) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _sha256(relative_path: Path) -> str:
    return hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()


def _fenced_block(language: str, content: str) -> str:
    longest_run = max((len(match.group(0)) for match in re.finditer(r"`+", content)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}{language}\n{content.rstrip()}\n{fence}"


def _demote_headings(markdown: str) -> str:
    """Demote ATX headings by one level without touching fenced code."""

    output: list[str] = []
    active_fence: str | None = None
    for line in markdown.splitlines():
        stripped = line.lstrip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if active_fence is None:
                active_fence = marker[0]
            elif marker[0] == active_fence:
                active_fence = None
            output.append(line)
            continue
        if active_fence is None and re.match(r"^#{1,5}\s", line):
            line = "#" + line
        output.append(line)
    return "\n".join(output)


def _markdown_cell(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\r", "<br>")
        .replace("\n", "<br>")
    )


def _csv_as_markdown(relative_path: Path) -> str:
    with (REPO_ROOT / relative_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return "_Empty CSV artifact._"

    width = len(rows[0])
    ragged_rows = [index for index, row in enumerate(rows, start=1) if len(row) != width]
    if ragged_rows:
        row_list = ", ".join(str(index) for index in ragged_rows)
        return (
            "> **Source-format note:** this artifact contains unquoted delimiter "
            f"commas, producing non-uniform column counts on source row(s) {row_list}. "
            "It is embedded verbatim below instead of being heuristically repaired "
            "or rendered as a potentially misleading Markdown table.\n\n"
            + _fenced_block("csv", _read(relative_path))
        )

    rendered = [
        "| " + " | ".join(_markdown_cell(cell) for cell in rows[0]) + " |",
        "| " + " | ".join("---" for _ in rows[0]) + " |",
    ]
    rendered.extend(
        "| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows[1:]
    )
    return "\n".join(rendered)


def _run_verification() -> str:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / VERIFICATION_SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    pass_count = sum(line.startswith("[PASS]") for line in output.splitlines())
    if result.returncode != 0 or pass_count != 4 or "OVERALL: PASS" not in output:
        raise RuntimeError(f"Boundary verification did not pass 4/4 checks:\n{output}")
    return output


def build() -> str:
    required_paths = (MAIN_REPORT, VERIFICATION_SCRIPT, *(artifact.path for artifact in ARTIFACTS))
    missing = [str(path) for path in required_paths if not (REPO_ROOT / path).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing audit source files: {', '.join(missing)}")

    verification_output = _run_verification()
    manifest_rows = []
    for label, path in (
        ("Main report", MAIN_REPORT),
        *((artifact.title, artifact.path) for artifact in ARTIFACTS),
        ("Verification script", VERIFICATION_SCRIPT),
    ):
        size = (REPO_ROOT / path).stat().st_size
        manifest_rows.append(f"| {label} | `{path}` | {size} | `{_sha256(path)}` |")

    parts = [
        "# Phase 0 — Development-Plan LLM Boundary Audit (Consolidated)",
        "",
        "> Portable single-file snapshot of the main audit report, all requested "
        "inventories/matrices/plans, and the read-only verification evidence. The "
        "source files remain unchanged.",
        "",
        "## Reading Guide",
        "",
        "- **Part I** is the human-readable audit report.",
        "- **Part II** contains every requested JSON/CSV audit artifact. JSON is "
        "embedded verbatim; well-formed CSV is rendered as Markdown with row/column "
        "order and cell content preserved. A malformed CSV is embedded verbatim "
        "with its affected source rows identified.",
        "- **Part III** records a fresh 4/4 verification run and embeds the exact "
        "read-only script used to produce it.",
        "- The manifest below records source byte sizes and SHA-256 hashes for "
        "snapshot verification.",
        "",
        "## Source Manifest",
        "",
        "| Component | Repository source | Bytes | SHA-256 |",
        "| --- | --- | ---: | --- |",
        *manifest_rows,
        "",
        "## Part I — Main Audit Report",
        "",
        f"Source: `{MAIN_REPORT}`",
        "",
        _demote_headings(_read(MAIN_REPORT)).rstrip(),
        "",
        "## Part II — Complete Audit Artifacts",
        "",
    ]

    for index, artifact in enumerate(ARTIFACTS, start=1):
        source = _read(artifact.path)
        rendered = _csv_as_markdown(artifact.path) if artifact.kind == "csv" else _fenced_block("json", source)
        parts.extend(
            (
                f"### Appendix {index} — {artifact.title}",
                "",
                f"Source: `{artifact.path}`",
                "",
                f"Purpose: {artifact.purpose}",
                "",
                rendered,
                "",
            )
        )

    parts.extend(
        (
            "## Part III — Read-Only Verification",
            "",
            "### Fresh Verification Result",
            "",
            "The builder reran the verification script before producing this "
            "snapshot. All four checks passed:",
            "",
            _fenced_block("text", verification_output),
            "",
            "### Verification Script",
            "",
            f"Source: `{VERIFICATION_SCRIPT}`",
            "",
            "Properties: read-only; not imported by production; zero network, "
            "LLM/Provider, or database calls.",
            "",
            _fenced_block("python", _read(VERIFICATION_SCRIPT)),
            "",
        )
    )
    return "\n".join(parts)


def main() -> int:
    report = build()
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} ({len(report.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
