"""Phase 0 -- Development-Plan LLM Boundary Audit: read-only verification.

Never imported by any production module. Performs zero network/LLM/DB
calls and never writes under ``outputs/``. Re-derives, from the current
repository state, the small set of structural facts the Phase 0 audit
report (``docs/development_plan_llm_boundary_audit.md``) depends on, so
they can be re-checked mechanically instead of only by prose claim:

- Architecture Replay (``comqutor_alpha/replay/pipeline.py``) never passes
  a live ``llm_gateway`` into the adapter/mapper/extractor builders.
- The deterministic core (graph_engine, conflict_engine, exposure*,
  structure_engine/evidence_stance.py) imports no LLM gateway module.
- The three real Week 2 LLM call sites (claim_batch_enrichment,
  alpha_classifier, structure_extractor) still route through the single
  ``Week2LLMGateway.invoke_json`` chokepoint.

Run: ``python scripts/audit_llm_boundary.py`` from the repo root.
Exit code 0 means every check passed; 1 means at least one did not
(printed per-check below) -- this script only reports; it changes nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DETERMINISTIC_CORE_DIRS = (
    "comqutor_alpha/graph_engine",
    "comqutor_alpha/conflict_engine",
    "comqutor_alpha/exposure",
)
DETERMINISTIC_CORE_FILES = (
    "comqutor_alpha/exposure_engine.py",
    "comqutor_alpha/structure_engine/evidence_stance.py",
)
LLM_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+comqutor_alpha\.(?:llm|structure_engine\.week2_llm)\s+import|"
    r"import\s+comqutor_alpha\.(?:llm|structure_engine\.week2_llm))",
    re.MULTILINE,
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def check_replay_never_passes_live_gateway() -> tuple[bool, str]:
    text = _read("comqutor_alpha/replay/pipeline.py")
    adapter_call_ok = "adapt_run_outputs(source_run_dir, llm_gateway=None)" in text
    mapper_call = re.search(r"build_alpha_matches_payload\(structured\)", text)
    extractor_call = re.search(r"build_extracted_structures_payload\(structured\)", text)
    ok = bool(adapter_call_ok and mapper_call and extractor_call)
    detail = (
        f"adapt_run_outputs explicit llm_gateway=None: {adapter_call_ok}; "
        f"build_alpha_matches_payload called with no llm_gateway kwarg "
        f"(defaults None): {bool(mapper_call)}; "
        f"build_extracted_structures_payload called with no llm_gateway kwarg "
        f"(defaults None): {bool(extractor_call)}"
    )
    return ok, detail


def check_deterministic_core_no_llm_import() -> tuple[bool, str]:
    offenders: list[str] = []
    py_files: list[Path] = []
    for rel_dir in DETERMINISTIC_CORE_DIRS:
        directory = REPO_ROOT / rel_dir
        if directory.is_dir():
            py_files.extend(sorted(directory.rglob("*.py")))
    for rel_file in DETERMINISTIC_CORE_FILES:
        py_files.append(REPO_ROOT / rel_file)

    for path in py_files:
        if "__pycache__" in path.parts or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if LLM_IMPORT_PATTERN.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    ok = not offenders
    detail = "no offenders" if ok else f"offenders: {offenders}"
    return ok, detail


def check_three_llm_tasks_share_one_gateway_chokepoint() -> tuple[bool, str]:
    gateway_text = _read("comqutor_alpha/structure_engine/week2_llm.py")
    tasks_present = all(
        f'"{task}"' in gateway_text
        for task in ("claim_batch_enrichment", "alpha_classifier", "structure_extractor")
    )
    invoke_json_def = "def invoke_json(" in gateway_text

    adapter_text = _read("comqutor_alpha/structure_engine/structured_output_adapter.py")
    mapper_text = _read("comqutor_alpha/structure_engine/alpha_mapper.py")
    extractor_text = _read("comqutor_alpha/structure_engine/structure_extractor.py")
    adapter_calls = 'llm_gateway.invoke_json(\n        "claim_batch_enrichment"' in adapter_text
    mapper_calls = '"alpha_classifier"' in mapper_text and "llm_gateway.invoke_json(" in mapper_text
    extractor_calls = '"structure_extractor"' in extractor_text and "llm_gateway.invoke_json(" in extractor_text

    ok = bool(tasks_present and invoke_json_def and adapter_calls and mapper_calls and extractor_calls)
    detail = (
        f"gateway defines all 3 task instructions: {tasks_present}; "
        f"adapter calls invoke_json('claim_batch_enrichment', ...): {adapter_calls}; "
        f"mapper calls invoke_json('alpha_classifier', ...): {mapper_calls}; "
        f"extractor calls invoke_json('structure_extractor', ...): {extractor_calls}"
    )
    return ok, detail


def check_gateway_requires_explicit_opt_in() -> tuple[bool, str]:
    text = _read("comqutor_alpha/structure_engine/week2_llm.py")
    ok = 'os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED")' in text and "return None" in text
    return ok, "COMQUTOR_WEEK2_LLM_ENABLED opt-in gate present" if ok else "opt-in gate not found"


CHECKS = (
    ("replay_never_passes_live_llm_gateway", check_replay_never_passes_live_gateway),
    ("deterministic_core_has_zero_llm_imports", check_deterministic_core_no_llm_import),
    ("three_llm_tasks_share_one_gateway_chokepoint", check_three_llm_tasks_share_one_gateway_chokepoint),
    ("live_gateway_requires_explicit_env_opt_in", check_gateway_requires_explicit_opt_in),
)


def main() -> int:
    all_ok = True
    for name, check in CHECKS:
        ok, detail = check()
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
    print("OVERALL:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
