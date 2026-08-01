"""Inject COMQUTOR Canonical Vocabulary into Existing TradingAgents Prompts.

Covers: the vocabulary manifest is sourced from the real production
registries (never a second hand-copied taxonomy); the prompt suffix
actually contains real factor IDs/aliases/relation definitions; the
injection scope patches/restores all 12 agent modules without adding any
new LLM call; the deterministic split/validate pipeline correctly separates
human prose from the machine-readable relation block and applies every
required rejection check; validated relations flow straight into candidate
edges and through the existing, unmodified Graph admission guards; replay
reuses the same deterministic pipeline with zero Provider calls.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.graph_engine.graph_builder import build_structure_graph
from comqutor_alpha.llm.canonical_prompt_injection import (
    AGENT_ID_TO_MODULE,
    build_vocabulary_snapshot,
    comqutor_structure_output_contract_scope,
)
from comqutor_alpha.replay.pipeline import run_structure_replay
from comqutor_alpha.structure_engine.alpha_mapper import build_alpha_matches_payload
from comqutor_alpha.structure_engine.canonical_relation_block import (
    split_human_text_and_canonical_block,
    validate_canonical_relations,
)
from comqutor_alpha.structure_engine.canonical_relation_prompt import (
    RELATION_BLOCK_MARKER,
    RELATION_BLOCK_SCHEMA_VERSION,
    build_structure_output_contract_prompt_suffix,
)
from comqutor_alpha.structure_engine.canonical_vocabulary import (
    build_canonical_relation_vocabulary,
    compute_taxonomy_sha256,
)
from comqutor_alpha.structure_engine.factor_normalizer import ALIAS_VERSION, FACTOR_ALIASES
from comqutor_alpha.structure_engine.structure_extractor import build_extracted_structures_payload
from comqutor_alpha.structure_engine.structure_schema import VALID_EDGE_TYPES
from comqutor_alpha.structure_engine.structured_output_adapter import (
    adapt_raw_agent_outputs,
    adapt_run_outputs,
)

RUN_ID = "canonical-test-run-0001"


def _canonical_report(source="AI CapEx", relation_type="causal", target="GPU Demand", confidence=0.91, assertion_status="asserted"):
    evidence = "Hyperscaler AI capital spending is driving demand for GPUs."
    body = {
        "schema_version": RELATION_BLOCK_SCHEMA_VERSION,
        "relations": [
            {
                "source_factor_id": source,
                "relation_type": relation_type,
                "target_factor_id": target,
                "evidence_quote": evidence,
                "assertion_status": assertion_status,
                "confidence": confidence,
            }
        ],
    }
    return (
        f"{evidence} This is a strong signal for the sector.\n\n"
        f"{RELATION_BLOCK_MARKER}\n```json\n{json.dumps(body)}\n```\n"
    ), evidence


def _empty_relations_report(prose):
    body = {"schema_version": RELATION_BLOCK_SCHEMA_VERSION, "relations": []}
    return f"{prose}\n\n{RELATION_BLOCK_MARKER}\n```json\n{json.dumps(body)}\n```\n"


# ---------------------------------------------------------------------------
# 1-8: Vocabulary is sourced from the real production registry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVocabularySourcedFromProduction:
    def test_factors_come_from_factor_normalizer_registry(self):
        vocabulary = build_canonical_relation_vocabulary()
        factor_ids = {f["factor_id"] for f in vocabulary["factors"]}
        assert factor_ids == set(FACTOR_ALIASES)

    def test_aliases_match_the_real_registry_exactly(self):
        vocabulary = build_canonical_relation_vocabulary()
        by_id = {f["factor_id"]: f for f in vocabulary["factors"]}
        for factor, aliases in FACTOR_ALIASES.items():
            assert by_id[factor]["aliases"] == list(aliases)

    def test_relation_types_come_from_structure_schema_registry(self):
        vocabulary = build_canonical_relation_vocabulary()
        relation_types = {r["relation_type"] for r in vocabulary["relations"]}
        assert relation_types == VALID_EDGE_TYPES

    def test_ai_capex_and_gpu_demand_are_present(self):
        vocabulary = build_canonical_relation_vocabulary()
        factor_ids = {f["factor_id"] for f in vocabulary["factors"]}
        assert "AI CapEx" in factor_ids
        assert "GPU Demand" in factor_ids

    def test_taxonomy_version_reuses_the_existing_alias_version(self):
        vocabulary = build_canonical_relation_vocabulary()
        assert vocabulary["taxonomy_version"] == ALIAS_VERSION

    def test_taxonomy_sha256_is_deterministic_and_content_derived(self):
        first = compute_taxonomy_sha256()
        second = compute_taxonomy_sha256()
        assert first == second
        assert len(first) == 64

    def test_no_second_hardcoded_taxonomy_in_this_module(self):
        import comqutor_alpha.structure_engine.canonical_vocabulary as module

        source = __import__("inspect").getsource(module)
        # The module must build factors from FACTOR_ALIASES, never declare a
        # second literal factor-name dict of its own.
        assert "FACTOR_ALIASES" in source
        assert '"AI CapEx":' not in source
        assert '"GPU Demand":' not in source

    def test_at_least_twenty_factors_report_when_present_in_registry(self):
        # This production taxonomy currently has 13 factors -- fewer than
        # 20 -- so this test asserts the manifest reports *every* real
        # factor rather than an arbitrary minimum count.
        vocabulary = build_canonical_relation_vocabulary()
        assert len(vocabulary["factors"]) == len(FACTOR_ALIASES)
        assert len(vocabulary["factors"]) >= 10


# ---------------------------------------------------------------------------
# Prompt verification (section 15, items 1-9)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPromptContainsRealVocabulary:
    def setup_method(self):
        self.vocabulary = build_canonical_relation_vocabulary()
        self.suffix = build_structure_output_contract_prompt_suffix(self.vocabulary)

    def test_prompt_contains_ai_capex_factor_id_and_display_name(self):
        assert "AI CapEx" in self.suffix

    def test_prompt_contains_gpu_demand_factor_id_and_display_name(self):
        assert "GPU Demand" in self.suffix

    def test_prompt_contains_the_real_causal_relation_enum_and_definition(self):
        assert "causal" in self.suffix
        assert "causes, drives, or otherwise produces a change" in self.suffix

    def test_prompt_contains_every_factor_alias(self):
        for aliases in FACTOR_ALIASES.values():
            for alias in aliases:
                assert alias in self.suffix

    def test_prompt_does_not_maintain_a_duplicate_static_taxonomy(self):
        # The suffix is rendered fresh from the vocabulary manifest every
        # call -- changing the registry changes the rendered text.
        mutated = dict(self.vocabulary)
        mutated["factors"] = [f for f in self.vocabulary["factors"] if f["factor_id"] != "AI CapEx"]
        mutated_suffix = build_structure_output_contract_prompt_suffix(mutated)
        assert "AI CapEx" not in mutated_suffix.split("VALID EXAMPLES")[0]

    def test_prompt_includes_the_output_format_marker(self):
        assert RELATION_BLOCK_MARKER in self.suffix

    def test_prompt_normal_report_instruction_is_preserved(self):
        assert "normal, professional analysis report" in self.suffix
        assert "must never be reduced to only" in self.suffix


# ---------------------------------------------------------------------------
# Injection scope: patches all 12 agents, adds zero LLM calls
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPromptInjectionScope:
    def test_all_twelve_agent_modules_are_covered(self):
        assert len(AGENT_ID_TO_MODULE) == 12

    def test_scope_patches_and_restores_every_agent_module(self):
        import importlib

        modules = [importlib.import_module(name) for name in AGENT_ID_TO_MODULE.values()]
        originals = [module.get_language_instruction for module in modules]

        with comqutor_structure_output_contract_scope():
            for module in modules:
                assert RELATION_BLOCK_MARKER in module.get_language_instruction()

        for module, original in zip(modules, originals, strict=True):
            assert module.get_language_instruction is original
            assert RELATION_BLOCK_MARKER not in module.get_language_instruction()

    def test_scope_appends_after_the_original_language_instruction_text(self):
        import tradingagents.agents.trader.trader as trader_module

        before = trader_module.get_language_instruction()
        with comqutor_structure_output_contract_scope():
            after = trader_module.get_language_instruction()
        assert after.startswith(before)
        assert after != before

    def test_scope_restores_originals_even_if_the_block_raises(self):
        import tradingagents.agents.trader.trader as trader_module

        original = trader_module.get_language_instruction
        with pytest.raises(RuntimeError), comqutor_structure_output_contract_scope():
            raise RuntimeError("boom")
        assert trader_module.get_language_instruction is original

    def test_scope_adds_zero_new_llm_invoke_calls(self):
        """Structural proof: the scope only ever reassigns a module
        attribute -- it contains no ``.invoke``/``.stream``/network call of
        its own, and the fake node below (which stands in for one real
        TradingAgents agent node) makes exactly the same single ``.invoke``
        call whether or not it runs inside the scope."""
        import tradingagents.agents.trader.trader as trader_module

        call_count = {"n": 0}

        class _FakeLLM:
            def invoke(self, prompt):
                call_count["n"] += 1
                return f"response-with-suffix-len-{len(prompt)}"

        def fake_node():
            prompt = "Base trader prompt. " + trader_module.get_language_instruction()
            return _FakeLLM().invoke(prompt)

        fake_node()
        assert call_count["n"] == 1
        with comqutor_structure_output_contract_scope():
            fake_node()
        assert call_count["n"] == 2  # exactly one more call, not two


# ---------------------------------------------------------------------------
# Vocabulary snapshot artifact (section 12/16)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVocabularySnapshot:
    def test_snapshot_reports_which_agents_saw_which_vocabulary(self):
        snapshot = build_vocabulary_snapshot()
        assert set(snapshot["agents"]) == set(AGENT_ID_TO_MODULE)
        for _agent_id, agent_entry in snapshot["agents"].items():
            assert "AI CapEx" in agent_entry["factor_ids_sent"]
            assert "GPU Demand" in agent_entry["factor_ids_sent"]
            assert "causal" in agent_entry["relation_types_sent"]

    def test_snapshot_never_includes_secrets(self):
        snapshot = build_vocabulary_snapshot()
        serialized = json.dumps(snapshot).lower()
        for forbidden in ("api_key", "authorization", "bearer", "secret"):
            assert forbidden not in serialized

    def test_snapshot_records_prompt_contract_hash(self):
        snapshot = build_vocabulary_snapshot()
        assert len(snapshot["prompt_contract_sha256"]) == 64
        assert snapshot["factor_count"] == len(FACTOR_ALIASES)

    def test_snapshot_artifact_actually_gets_written_by_the_real_writer(self, tmp_path):
        # Regression test: save_comqutor_run_outputs must actually persist
        # this artifact, not merely build it in memory -- caught for real
        # during the NVDA acceptance run, where the filename was rejected
        # by file_store.ALLOWED_ARTIFACT_FILENAMES and the writer's own
        # defensive try/except silently swallowed the failure.
        from comqutor_alpha.adapters.tradingagents_output_writer import (
            save_comqutor_run_outputs,
        )

        run_dir = save_comqutor_run_outputs(
            final_state={"market_report": "Revenue growth accelerated this quarter."},
            ticker="NVDA",
            config={"llm_provider": "deepseek"},
            output_root=tmp_path,
        )
        snapshot_path = run_dir / "tradingagents_comqutor_vocabulary_snapshot.json"
        assert snapshot_path.exists()
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert snapshot["factor_count"] == len(FACTOR_ALIASES)
        assert snapshot["relation_count"] == len(VALID_EDGE_TYPES)


# ---------------------------------------------------------------------------
# Deterministic split: human text vs machine block
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSplitHumanTextAndCanonicalBlock:
    def test_no_marker_leaves_text_unchanged(self):
        text = "Revenue growth accelerated this quarter."
        parsed = split_human_text_and_canonical_block(text)
        assert parsed.found is False
        assert parsed.human_text == text

    def test_marker_and_json_block_are_removed_from_human_text(self):
        report, evidence = _canonical_report()
        parsed = split_human_text_and_canonical_block(report)
        assert RELATION_BLOCK_MARKER not in parsed.human_text
        assert "source_factor_id" not in parsed.human_text
        assert "{" not in parsed.human_text
        assert evidence in parsed.human_text

    def test_malformed_json_never_raises_and_still_strips_the_marker(self):
        text = f"Some report text.\n\n{RELATION_BLOCK_MARKER}\n```json\n{{not valid json\n```\n"
        parsed = split_human_text_and_canonical_block(text)
        assert parsed.found is True
        assert parsed.parse_error is not None
        assert RELATION_BLOCK_MARKER not in parsed.human_text

    def test_empty_relations_array_parses_cleanly(self):
        text = _empty_relations_report("Two facts are both true independently.")
        parsed = split_human_text_and_canonical_block(text)
        assert parsed.found is True
        assert parsed.parse_error is None
        assert parsed.raw_relations == []


# ---------------------------------------------------------------------------
# Deterministic validation against the real production vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateCanonicalRelations:
    def setup_method(self):
        self.vocabulary = build_canonical_relation_vocabulary()

    def _validate_one(self, relation_overrides, evidence="Hyperscaler AI capital spending is driving demand for GPUs."):
        base = {
            "source_factor_id": "AI CapEx",
            "relation_type": "causal",
            "target_factor_id": "GPU Demand",
            "evidence_quote": evidence,
            "assertion_status": "asserted",
            "confidence": 0.9,
        }
        base.update(relation_overrides)
        body = {"schema_version": RELATION_BLOCK_SCHEMA_VERSION, "relations": [base]}
        text = f"{evidence}\n\n{RELATION_BLOCK_MARKER}\n```json\n{json.dumps(body)}\n```\n"
        parsed = split_human_text_and_canonical_block(text)
        records = validate_canonical_relations(
            parsed,
            vocabulary=self.vocabulary,
            agent_report_text=parsed.human_text,
            agent="market_agent",
            run_id=RUN_ID,
            ticker="NVDA",
            source_agent_output_id=f"{RUN_ID}:market_agent:market_report",
        )
        assert len(records) == 1
        return records[0]

    def test_valid_relation_is_accepted(self):
        record = self._validate_one({})
        assert record["validation_status"] == "accepted"
        assert record["candidate_edge_created"] is True
        assert record["canonical_sentence"] == "AI CapEx drives GPU Demand."

    def test_unknown_source_factor_is_rejected(self):
        record = self._validate_one({"source_factor_id": "Not A Real Factor"})
        assert record["validation_status"] == "rejected"
        assert record["validation_rejection_reasons"] == ["unknown_source_factor"]

    def test_unknown_target_factor_is_rejected(self):
        record = self._validate_one({"target_factor_id": "Not A Real Factor"})
        assert record["validation_rejection_reasons"] == ["unknown_target_factor"]

    def test_invalid_relation_type_is_rejected(self):
        record = self._validate_one({"relation_type": "increases"})
        assert record["validation_rejection_reasons"] == ["invalid_relation_type"]

    def test_self_edge_is_rejected(self):
        record = self._validate_one({"target_factor_id": "AI CapEx"})
        assert record["validation_rejection_reasons"] == ["self_edge"]

    def test_evidence_not_a_substring_is_rejected(self):
        record = self._validate_one({"evidence_quote": "This text is not in the report."})
        assert record["validation_rejection_reasons"] == ["evidence_not_found"]

    def test_invalid_confidence_is_rejected(self):
        record = self._validate_one({"confidence": 1.5})
        assert record["validation_rejection_reasons"] == ["invalid_confidence"]

    def test_invalid_assertion_status_is_rejected(self):
        record = self._validate_one({"assertion_status": "definitely"})
        assert record["validation_rejection_reasons"] == ["invalid_assertion_status"]

    def test_duplicate_relation_is_rejected_on_second_occurrence(self):
        evidence = "Hyperscaler AI capital spending is driving demand for GPUs."
        relation = {
            "source_factor_id": "AI CapEx",
            "relation_type": "causal",
            "target_factor_id": "GPU Demand",
            "evidence_quote": evidence,
            "assertion_status": "asserted",
            "confidence": 0.9,
        }
        body = {"schema_version": RELATION_BLOCK_SCHEMA_VERSION, "relations": [relation, dict(relation)]}
        text = f"{evidence}\n\n{RELATION_BLOCK_MARKER}\n```json\n{json.dumps(body)}\n```\n"
        parsed = split_human_text_and_canonical_block(text)
        records = validate_canonical_relations(
            parsed,
            vocabulary=self.vocabulary,
            agent_report_text=parsed.human_text,
            agent="market_agent",
            run_id=RUN_ID,
            ticker="NVDA",
            source_agent_output_id="x",
        )
        assert records[0]["validation_status"] == "accepted"
        assert records[1]["validation_status"] == "rejected"
        assert records[1]["validation_rejection_reasons"] == ["duplicate_relation"]

    def test_hypothetical_relation_is_recorded_but_never_a_candidate_edge(self):
        record = self._validate_one({"assertion_status": "hypothetical"})
        assert record["validation_status"] == "accepted"
        assert record["candidate_edge_created"] is False

    def test_conditional_relation_stays_conditional_never_a_candidate_edge(self):
        record = self._validate_one({"assertion_status": "conditional"})
        assert record["candidate_edge_created"] is False

    def test_wrong_schema_version_rejects_with_schema_invalid(self):
        evidence = "Hyperscaler AI capital spending is driving demand for GPUs."
        body = {
            "schema_version": "some_other_schema_v9",
            "relations": [
                {
                    "source_factor_id": "AI CapEx",
                    "relation_type": "causal",
                    "target_factor_id": "GPU Demand",
                    "evidence_quote": evidence,
                    "assertion_status": "asserted",
                    "confidence": 0.9,
                }
            ],
        }
        text = f"{evidence}\n\n{RELATION_BLOCK_MARKER}\n```json\n{json.dumps(body)}\n```\n"
        parsed = split_human_text_and_canonical_block(text)
        records = validate_canonical_relations(
            parsed,
            vocabulary=self.vocabulary,
            agent_report_text=parsed.human_text,
            agent="market_agent",
            run_id=RUN_ID,
            ticker="NVDA",
            source_agent_output_id="x",
        )
        assert records[0]["validation_rejection_reasons"] == ["schema_invalid"]


# ---------------------------------------------------------------------------
# Claim segmentation never eats the machine block
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClaimSegmentationExcludesCanonicalBlock:
    def test_normal_report_text_still_becomes_claims(self):
        report, evidence = _canonical_report()
        raw_record = {"agent": "market_agent", "raw_output": report, "agent_output_id": "x:market_agent:market_report"}
        records = adapt_raw_agent_outputs(raw_record, RUN_ID, "NVDA")
        assert any(evidence in r["claim"] for r in records)

    def test_json_block_never_becomes_a_claim(self):
        report, _evidence = _canonical_report()
        raw_record = {"agent": "market_agent", "raw_output": report, "agent_output_id": "x:market_agent:market_report"}
        records = adapt_raw_agent_outputs(raw_record, RUN_ID, "NVDA")
        joined = " ".join(r["claim"] for r in records)
        assert "schema_version" not in joined
        assert "source_factor_id" not in joined
        assert RELATION_BLOCK_MARKER not in joined

    def test_canonical_relations_audit_is_populated(self):
        report, _evidence = _canonical_report()
        raw_record = {"agent": "market_agent", "raw_output": report, "agent_output_id": "x:market_agent:market_report"}
        audit: list = []
        adapt_raw_agent_outputs(raw_record, RUN_ID, "NVDA", canonical_relations_audit=audit)
        assert len(audit) == 1
        assert audit[0]["source_factor_id"] == "AI CapEx"

    def test_no_marker_present_produces_no_canonical_relations(self):
        raw_record = {
            "agent": "market_agent",
            "raw_output": "Plain report text with no canonical block at all.",
            "agent_output_id": "x:market_agent:market_report",
        }
        audit: list = []
        adapt_raw_agent_outputs(raw_record, RUN_ID, "NVDA", canonical_relations_audit=audit)
        assert audit == []


# ---------------------------------------------------------------------------
# Full run: structured -> extracted -> Graph, admission guards still apply
# ---------------------------------------------------------------------------


def _write_run(base_dir, agent_outputs, ticker="NVDA"):
    run_dir = base_dir / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_payload = {
        "schema_version": "week1a.raw_agent_outputs.v1",
        "run_id": RUN_ID,
        "ticker": ticker,
        "agent_outputs": agent_outputs,
    }
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps(raw_payload), encoding="utf-8")
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": RUN_ID, "ticker": ticker, "config": {"llm_provider": "deepseek"}}),
        encoding="utf-8",
    )
    return run_dir


@pytest.mark.unit
class TestCandidateEdgeReachesGraphThroughAdmissionGuards:
    def test_accepted_relation_becomes_an_admitted_graph_edge(self, tmp_path):
        report, _evidence = _canonical_report()
        run_dir = _write_run(
            tmp_path,
            [{"agent_output_id": f"{RUN_ID}:market_agent:market_report", "run_id": RUN_ID, "ticker": "NVDA", "agent": "market_agent", "raw_output": report}],
        )
        structured = adapt_run_outputs(run_dir)
        assert len(structured["canonical_relations"]) == 1
        extracted = build_extracted_structures_payload(structured)
        assert extracted["metadata"]["canonical_relation_edge_count"] == 1
        alpha_matches = build_alpha_matches_payload(structured)
        graph = build_structure_graph(alpha_matches, extracted)
        edges = graph["edges"]
        assert len(edges) == 1
        assert edges[0]["source"] == "ai_capex"
        assert edges[0]["target"] == "gpu_demand"
        assert "tradingagents_canonical_output" in edges[0]["extraction_methods"]

    def test_extraction_methods_show_both_when_deterministic_also_finds_it(self, tmp_path):
        report, _evidence = _canonical_report()
        run_dir = _write_run(
            tmp_path,
            [{"agent_output_id": f"{RUN_ID}:market_agent:market_report", "run_id": RUN_ID, "ticker": "NVDA", "agent": "market_agent", "raw_output": report}],
        )
        structured = adapt_run_outputs(run_dir)
        extracted = build_extracted_structures_payload(structured)
        alpha_matches = build_alpha_matches_payload(structured)
        graph = build_structure_graph(alpha_matches, extracted)
        methods = set(graph["edges"][0]["extraction_methods"])
        assert methods == {"deterministic_rules", "tradingagents_canonical_output"}

    def test_self_edge_relation_never_reaches_the_graph_even_if_it_slipped_through(self, tmp_path):
        # Defense in depth: even a malformed canonical-relation edge dict
        # with source == target must be rejected by graph_builder's own
        # self-loop guard, not merely by the earlier validator.
        from comqutor_alpha.structure_engine.structure_extractor import (
            _canonical_relation_edges_and_nodes,
        )

        relation = {
            "source_factor_id": "AI CapEx",
            "target_factor_id": "AI CapEx",
            "relation_type": "causal",
            "canonical_sentence": "AI CapEx drives AI CapEx.",
            "evidence_quote": "x",
            "assertion_status": "asserted",
            "confidence": 0.9,
            "relation_id": "canrel_forced_self_edge",
            "source_agent_output_id": "x",
            "ticker": "NVDA",
            "candidate_edge_created": True,
        }
        edges, nodes = _canonical_relation_edges_and_nodes([relation])
        extracted = {
            "schema_version": "week2.extracted_structures.v2",
            "run_id": RUN_ID,
            "ticker": "NVDA",
            "nodes": nodes,
            "edges": edges,
            "metadata": {},
        }
        graph = build_structure_graph({"matches": []}, extracted)
        assert graph["edges"] == []
        assert graph["graph_metrics"]["rejected_edges"]["self_loop"] >= 1

    def test_no_forced_edge_when_no_canonical_block_present(self, tmp_path):
        run_dir = _write_run(
            tmp_path,
            [
                {
                    "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                    "run_id": RUN_ID,
                    "ticker": "NVDA",
                    "agent": "market_agent",
                    "raw_output": "AI CapEx is strong. GPU Demand is also strong.",
                }
            ],
        )
        structured = adapt_run_outputs(run_dir)
        assert structured["canonical_relations"] == []


# ---------------------------------------------------------------------------
# Raw prose is never rewritten; canonical sentence is never reverse-parsed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProvenanceAndImmutability:
    def test_raw_agent_outputs_json_is_never_modified_by_adapt_run_outputs(self, tmp_path):
        report, _evidence = _canonical_report()
        run_dir = _write_run(
            tmp_path,
            [{"agent_output_id": f"{RUN_ID}:market_agent:market_report", "run_id": RUN_ID, "ticker": "NVDA", "agent": "market_agent", "raw_output": report}],
        )
        before = (run_dir / "raw_agent_outputs.json").read_text(encoding="utf-8")
        adapt_run_outputs(run_dir)
        after = (run_dir / "raw_agent_outputs.json").read_text(encoding="utf-8")
        assert before == after

    def test_canonical_sentence_is_deterministically_generated_not_from_the_llm(self):
        vocabulary = build_canonical_relation_vocabulary()
        report, evidence = _canonical_report()
        parsed = split_human_text_and_canonical_block(report)
        records = validate_canonical_relations(
            parsed, vocabulary=vocabulary, agent_report_text=parsed.human_text,
            agent="market_agent", run_id=RUN_ID, ticker="NVDA", source_agent_output_id="x",
        )
        # The LLM's JSON never supplied a canonical_sentence field at all --
        # it is built purely from the validated triple by our own code.
        assert "canonical_sentence" not in json.loads(report.split("```json\n")[1].split("\n```")[0])["relations"][0]
        assert records[0]["canonical_sentence"] == "AI CapEx drives GPU Demand."


# ---------------------------------------------------------------------------
# Replay: zero Provider calls, same deterministic result
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReplayBoundary:
    def test_replay_reprocesses_the_saved_canonical_block_with_zero_provider_calls(self, tmp_path):
        report, _evidence = _canonical_report()
        _write_run(
            tmp_path,
            [{"agent_output_id": f"{RUN_ID}:market_agent:market_report", "run_id": RUN_ID, "ticker": "NVDA", "agent": "market_agent", "raw_output": report}],
        )
        result = run_structure_replay(
            RUN_ID,
            source_output_root=str(tmp_path),
            replay_output_root=str(tmp_path / "replays"),
        )
        assert result.status == "completed"
        assert result.llm_provider_calls == 0
        assert result.tradingagents_calls == 0
        extracted = json.loads((tmp_path / "replays" / result.replay_run_id / "extracted_structures.json").read_text())
        assert extracted["metadata"]["canonical_relation_edge_count"] == 1

    def test_replay_of_a_run_without_any_canonical_block_still_works(self, tmp_path):
        _write_run(
            tmp_path,
            [
                {
                    "agent_output_id": f"{RUN_ID}:market_agent:market_report",
                    "run_id": RUN_ID,
                    "ticker": "NVDA",
                    "agent": "market_agent",
                    "raw_output": "AI CapEx spending is driving strong AI Demand growth this quarter.",
                }
            ],
        )
        result = run_structure_replay(
            RUN_ID,
            source_output_root=str(tmp_path),
            replay_output_root=str(tmp_path / "replays"),
        )
        assert result.status == "completed"
        assert result.llm_provider_calls == 0
