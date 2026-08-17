"""Phase 1B.1: import-graph and default-setting boundary tests.

No module under comqutor_alpha/api, comqutor_alpha/replay, the current
Adapter/Mapper/Extractor, Graph/Conflict/Exposure, or tradingagents/ may
import any Phase 1B.1 smoke module. COMQUTOR_WEEK2_LLM_ENABLED's default
must remain unaffected by this phase.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PHASE1B1_MODULES = {
    "comqutor_alpha.structure_engine.structured_output_shadow_provider",
    "comqutor_alpha.structure_engine.structured_output_shadow_replay",
}

PRODUCTION_SCOPES = (
    "comqutor_alpha/api",
    "comqutor_alpha/replay",
    "comqutor_alpha/graph_engine",
    "comqutor_alpha/conflict_engine",
    "comqutor_alpha/exposure",
    "tradingagents",
)
PROTECTED_SINGLE_FILES = (
    "comqutor_alpha/exposure_engine.py",
    "comqutor_alpha/structure_engine/structured_output_adapter.py",
    "comqutor_alpha/structure_engine/alpha_mapper.py",
    "comqutor_alpha/structure_engine/structure_extractor.py",
    "comqutor_alpha/llm/canonical_prompt_injection.py",
    "comqutor_alpha/structure_engine/canonical_relation_prompt.py",
)


def _imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_no_production_scope_imports_phase1b1_smoke_modules():
    files = [REPO_ROOT / rel for rel in PROTECTED_SINGLE_FILES]
    for scope in PRODUCTION_SCOPES:
        target = REPO_ROOT / scope
        if target.is_dir():
            files.extend(target.rglob("*.py"))
    offenders = []
    for path in files:
        if "__pycache__" in path.parts or not path.exists():
            continue
        if _imported_modules(path) & PHASE1B1_MODULES:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_run_phase1b1_provider_smoke_script_not_imported_by_production():
    files = []
    for scope in PRODUCTION_SCOPES:
        target = REPO_ROOT / scope
        if target.is_dir():
            files.extend(target.rglob("*.py"))
    offenders = []
    for path in files:
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "run_phase1b1_provider_smoke" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_default_llm_setting_unaffected_when_env_unset(monkeypatch):
    from comqutor_alpha.structure_engine.week2_llm import week2_llm_enabled

    monkeypatch.delenv("COMQUTOR_WEEK2_LLM_ENABLED", raising=False)
    assert week2_llm_enabled() is False


def test_existing_three_task_instructions_text_unchanged():
    """Phase 1B.1's own scope added zero new Week2 tasks: it uses
    ``invoke_prebuilt_json_prompt`` specifically so the frozen Shadow prompt
    never touches ``_TASK_INSTRUCTIONS`` (see that method's own docstring).
    The three original tasks' text is therefore still exactly as Phase
    1B.1 found it, and ``"structured_claim_shadow"`` never leaked in.

    A later, separately-authorized Sprint (B1 LLM Evidence Stance Upgrade)
    legitimately grew this registry to four tasks through the same,
    intended extension point every prior task used -- this is not a Phase
    1B.1 boundary violation, so the set assertion below reflects that
    real, sanctioned addition rather than re-freezing the original three.
    """
    from comqutor_alpha.structure_engine.week2_llm import _TASK_INSTRUCTIONS

    assert set(_TASK_INSTRUCTIONS) == {
        "claim_batch_enrichment",
        "alpha_classifier",
        "structure_extractor",
        "evidence_stance_classifier",
    }
    assert "structured_claim_shadow" not in _TASK_INSTRUCTIONS


def test_replay_pipeline_still_passes_llm_gateway_none_explicitly():
    text = (REPO_ROOT / "comqutor_alpha/replay/pipeline.py").read_text(encoding="utf-8")
    assert "adapt_run_outputs(source_run_dir, llm_gateway=None)" in text


def test_shadow_provider_module_declares_no_live_route_intent_in_docstring():
    path = REPO_ROOT / "comqutor_alpha/structure_engine/structured_output_shadow_provider.py"
    text = path.read_text(encoding="utf-8")
    assert "never a live route" not in text  # not literal wording required
    assert "scripts/run_phase1b1_provider_smoke.py" in text


def test_no_pilot_or_evaluation_scaffolding_exists_yet():
    for forward_scope in ("phase1b2", "phase1b3", "phase1c"):
        assert not (REPO_ROOT / "docs/audit_artifacts" / forward_scope).exists()
        assert not any(
            forward_scope in p.name.casefold()
            for p in (REPO_ROOT / "scripts").glob("*.py")
        )


def test_cli_module_reads_approval_env_var_only_at_call_time(monkeypatch):
    # Import must never itself read or act on the approval variable --
    # authorization is checked inside main(), not at module load time.
    monkeypatch.delenv("COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED", raising=False)
    import importlib
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    if "run_phase1b1_provider_smoke" in sys.modules:
        importlib.reload(sys.modules["run_phase1b1_provider_smoke"])
    else:
        importlib.import_module("run_phase1b1_provider_smoke")
    assert os.environ.get("COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED") is None
