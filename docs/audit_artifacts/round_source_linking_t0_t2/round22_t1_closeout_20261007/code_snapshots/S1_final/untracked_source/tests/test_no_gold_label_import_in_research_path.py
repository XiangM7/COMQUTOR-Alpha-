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
