"""Round 5 (2026-10-04), T2 closing gap: John's own requirement -- "Gold
标签不能作为目标答案输入研究Agent，也不能为了符合允许列表而改写研究输出"
(Gold labels must never be fed into the research Agent as a target answer,
and must never be used to rewrite research output to match an allowed
list) -- was previously enforced only by code convention/docstring
(comqutor_alpha/regression/labels.py:7-9), with no automated check that
would fail CI the moment a future change introduced a Gold import into the
research/scoring path. This is that automated check.

Mirrors the existing established pattern
(tests/test_factor_normalizer.py::test_structure_extractor_does_not_import_
alpha_mapper): reads each guarded module's own source text and asserts it
never references the Gold label modules, rather than trying to introspect
the live import graph (which could miss a late/conditional import).

The ONE deliberate, reviewed exception is comqutor_alpha.api.
formal_acceptance_artifact -- the POST-HOC acceptance/grading layer John's
own T2 section explicitly requires to read Gold's allowed-conflict/
expected-alpha declarations AFTER research is complete, to check the
already-produced output. That module's own docstring explains the
exception; this test asserts the exception is exactly that one module,
never silently widened."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

_GOLD_LABEL_MODULE_MARKERS = ("regression.labels", "regression import labels")

# Modules that sit on the real-time research/scoring path -- the Agent's
# own prompt construction, Alpha/Structure mapping, and Activation scoring
# -- and must NEVER see Gold label data, since any of them doing so could
# let a label answer the question it is supposed to be graded against.
_FORBIDDEN_MODULES = (
    "comqutor_alpha.structure_engine.week2_llm",
    "comqutor_alpha.structure_engine.alpha_mapper",
    "comqutor_alpha.graph_engine.activation_scorer_v2",
    "comqutor_alpha.api.agent_output_reader",
)

# Every comqutor_alpha/api/*.py module, EXCEPT the one deliberate, reviewed
# post-hoc acceptance-layer exception -- see this file's own docstring.
_API_DIR = Path(__file__).resolve().parents[1] / "comqutor_alpha" / "api"
_API_GOLD_IMPORT_EXCEPTION = "formal_acceptance_artifact.py"


def _source_mentions_gold_labels(source: str) -> bool:
    return any(marker in source for marker in _GOLD_LABEL_MODULE_MARKERS)


def test_research_and_scoring_modules_never_import_gold_labels():
    import importlib

    for module_name in _FORBIDDEN_MODULES:
        module = importlib.import_module(module_name)
        source = inspect.getsource(module)
        assert not _source_mentions_gold_labels(source), (
            f"{module_name} must never import comqutor_alpha.regression.labels/labels_v2 -- "
            "Gold labels are a post-hoc grading input, never a research/scoring-time input"
        )


def test_the_only_api_module_allowed_to_import_gold_labels_is_the_reviewed_acceptance_layer():
    offenders = []
    for path in sorted(_API_DIR.glob("*.py")):
        if path.name == _API_GOLD_IMPORT_EXCEPTION:
            continue
        source = path.read_text(encoding="utf-8")
        if _source_mentions_gold_labels(source):
            offenders.append(path.name)
    assert offenders == [], (
        f"unexpected Gold-label import(s) in comqutor_alpha/api/: {offenders} -- only "
        f"{_API_GOLD_IMPORT_EXCEPTION} (the reviewed, post-hoc formal-acceptance artifact writer) "
        "is permitted to import Gold label data"
    )


def test_the_reviewed_exception_module_still_exists_and_still_imports_gold_labels():
    """Guards against the exception list going silently stale (e.g. the
    module gets renamed and this test's exclusion keyword starts matching
    nothing, making the test above vacuously pass)."""
    exception_path = _API_DIR / _API_GOLD_IMPORT_EXCEPTION
    assert exception_path.exists(), f"{_API_GOLD_IMPORT_EXCEPTION} was expected to exist under comqutor_alpha/api/"
    assert _source_mentions_gold_labels(exception_path.read_text(encoding="utf-8")), (
        f"{_API_GOLD_IMPORT_EXCEPTION} no longer imports Gold labels -- if this is deliberate, "
        "remove it from _API_GOLD_IMPORT_EXCEPTION instead of leaving a stale exception"
    )


# ---------------------------------------------------------------------------
# T2 (2026-10-07): the guard above names four modules and the api/ directory. That left the rest of the research / scoring path
# (graph_engine, conflict_engine, structure_engine's other modules, llm_runtime, adapters, runners, storage, ...) and the research Agents
# themselves (tradingagents/) unprotected. John: "Gold 标签不能作为目标答案输入研究 Agent，也不能为了符合允许列表而改写研究输出". These tests
# protect the whole path, with the AST (so `from comqutor_alpha import regression`, aliases and relative imports are caught too).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ACCEPTANCE_LAYER = "comqutor_alpha.regression"
_ACCEPTANCE_LAYER_DIR = _REPO_ROOT / "comqutor_alpha" / "regression"
_REVIEWED_EXCEPTION = _REPO_ROOT / "comqutor_alpha" / "api" / _API_GOLD_IMPORT_EXCEPTION


def _python_files(root: Path):
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _package_of(path: Path) -> list[str]:
    """The dotted package a file lives in (for pkg/mod.py and for pkg/__init__.py alike: ["pkg"])."""
    return list(path.relative_to(_REPO_ROOT).with_suffix("").parts)[:-1]


def _imported_names(source: str, package: list[str]) -> list[str]:
    """Absolute dotted name of every module / name the source imports; relative imports are resolved against ``package``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - (node.level - 1)] if node.level else []
            module = ".".join(base + (node.module.split(".") if node.module else []))
            found.append(module)
            found += [f"{module}.{alias.name}" for alias in node.names]
    return found


def _imported_modules(path: Path) -> list[str]:
    return _imported_names(path.read_text(encoding="utf-8"), _package_of(path))


def _touches_acceptance_layer(imported: str) -> bool:
    return imported == _ACCEPTANCE_LAYER or imported.startswith(_ACCEPTANCE_LAYER + ".")


def test_nothing_on_the_research_path_imports_the_acceptance_layer_at_all():
    offenders = []
    for root in (_REPO_ROOT / "comqutor_alpha", _REPO_ROOT / "tradingagents"):
        for path in _python_files(root):
            if _ACCEPTANCE_LAYER_DIR in path.parents or path == _REVIEWED_EXCEPTION:
                continue
            hits = sorted({m for m in _imported_modules(path) if _touches_acceptance_layer(m)})
            if hits:
                offenders.append(f"{path.relative_to(_REPO_ROOT)} -> {hits}")
    assert offenders == [], (
        "modules outside comqutor_alpha/regression/ import the Gold / acceptance layer; only the reviewed post-hoc writer may: "
        + "; ".join(offenders)
    )


def test_the_import_scan_really_sees_the_reviewed_exception():
    """If the AST walker silently saw nothing, the test above would pass vacuously."""
    hits = {m for m in _imported_modules(_REVIEWED_EXCEPTION) if _touches_acceptance_layer(m)}
    assert "comqutor_alpha.regression.labels" in hits
    assert "comqutor_alpha.regression.acceptance_engine" in hits


def test_the_walker_catches_aliased_package_and_relative_forms_of_the_same_import():
    api_package = ["comqutor_alpha", "api"]
    forms = {
        "from comqutor_alpha import regression": "comqutor_alpha.regression",
        "import comqutor_alpha.regression.labels as gold": "comqutor_alpha.regression.labels",
        "from comqutor_alpha.regression import labels_v2": "comqutor_alpha.regression.labels_v2",
        "from ..regression import labels": "comqutor_alpha.regression.labels",
        "from ..regression.labels_v2 import load_j2_labels_v2": "comqutor_alpha.regression.labels_v2",
    }
    for source, expected in forms.items():
        names = _imported_names(source, api_package)
        assert expected in names, (source, names)
        assert any(_touches_acceptance_layer(name) for name in names), source
    # and does not cry wolf about an unrelated sibling
    assert not any(_touches_acceptance_layer(n) for n in _imported_names("from .routes_research import router", api_package))
    assert not any(_touches_acceptance_layer(n) for n in _imported_names("from comqutor_alpha.graph_engine import pipeline", api_package))


def test_only_the_reviewed_writer_and_the_run_completion_call_site_know_the_verdict_artifact():
    """Nothing may READ the verdict back into the research path: the only files outside the acceptance layer that mention it are the writer, the
    one call site that invokes the writer, and the artifact allow-list (file name only)."""
    mentioning = []
    for path in _python_files(_REPO_ROOT / "comqutor_alpha"):
        if _ACCEPTANCE_LAYER_DIR in path.parents:
            continue
        if "formal_acceptance" in path.read_text(encoding="utf-8"):
            mentioning.append(str(path.relative_to(_REPO_ROOT)))
    assert mentioning == [
        "comqutor_alpha/api/formal_acceptance_artifact.py",
        "comqutor_alpha/api/routes_research.py",
        "comqutor_alpha/storage/file_store.py",
    ]
    routes = (_REPO_ROOT / "comqutor_alpha" / "api" / "routes_research.py").read_text(encoding="utf-8")
    assert "formal_acceptance.json" not in routes, "the run completion path must only WRITE the verdict, never read it back"


# ---------------------------------------------------------------------------
# Round 24 (2026-10-07): John's frozen Gold contract and trigger matrix are Gold too. They are read only by the acceptance layer, AFTER the research is
# complete; no research / scoring / Agent module may name those files, and nothing outside comqutor_alpha/regression/ may import the module that
# executes them (the import scan above already refuses any import of comqutor_alpha.regression.* from outside the layer).
# ---------------------------------------------------------------------------

_GOLD_CONTRACT_FILE_MARKERS = ("v0_2_gold_operational_contract", "v0_2_evidence_trigger_matrix", "v0_2_gold_freeze_manifest")


def test_nothing_on_the_research_path_names_the_gold_contract_files():
    offenders = []
    for root in (_REPO_ROOT / "comqutor_alpha", _REPO_ROOT / "tradingagents"):
        for path in _python_files(root):
            if _ACCEPTANCE_LAYER_DIR in path.parents:
                continue
            text = path.read_text(encoding="utf-8")
            hits = [marker for marker in _GOLD_CONTRACT_FILE_MARKERS if marker in text]
            if hits:
                offenders.append(f"{path.relative_to(_REPO_ROOT)} -> {hits}")
    assert offenders == [], "modules outside the acceptance layer name the Gold contract / trigger matrix files: " + "; ".join(offenders)


def test_the_contract_scan_is_not_vacuous_the_acceptance_layer_does_name_the_files():
    text = (_ACCEPTANCE_LAYER_DIR / "gold_contract_rules.py").read_text(encoding="utf-8")
    assert all(marker in text for marker in _GOLD_CONTRACT_FILE_MARKERS)
    importers = [
        str(path.relative_to(_REPO_ROOT))
        for path in _python_files(_REPO_ROOT / "comqutor_alpha")
        if any(m.endswith("gold_contract_rules") for m in _imported_modules(path))
    ]
    assert importers == ["comqutor_alpha/regression/acceptance_engine.py"], importers
