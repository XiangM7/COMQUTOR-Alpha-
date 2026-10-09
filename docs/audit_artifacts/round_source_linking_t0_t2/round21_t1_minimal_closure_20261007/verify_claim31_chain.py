#!/usr/bin/env python3
"""Round 21 item 1 -- verify, link by link, the positive sample claim 31 of the AMD requalification chain on the FINAL
offline execution: saved material -> claim -> Evidence Fact -> Alpha -> API -> UI -> Export.

Read-only: it reads the execution's saved artifacts, issues GET requests to the read-only viewer API (:8001) and reads the
browser walkthrough's own result file and the zip the browser downloaded. It writes only ``claim31_chain_verification.json``.
Zero Provider / search / data-fetch calls (production helper functions used here are pure).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from comqutor_alpha.source_provenance import compute_verified_support_eligibility  # noqa: E402

EXEC = sys.argv[1] if len(sys.argv) > 1 else "dependency-20261007T220450Z-33128621"
ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1:"
CLAIM = ROOT + "fundamental_agent:fundamentals_report:claim:31"
RUN = REPO / "outputs" / "runs" / EXEC
API = "http://127.0.0.1:8001"
jload = lambda p: json.loads(Path(p).read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()

links: list[dict] = []

# Round 22: the live trace route gained ADDITIVE keys after this execution's evidence_trace.json was written (its code predates them). The
# comparison therefore ignores exactly these keys (listed in the evidence) and still requires every pre-existing field to be identical.
ADDITIVE_TOP_LEVEL = ("conflict_adoption", "run_basis")


def without_additive(item: dict) -> tuple[dict, list[str]]:
    clean = json.loads(json.dumps(item))
    present = [k for k in ADDITIVE_TOP_LEVEL if clean.pop(k, None) is not None or False]
    for source in clean.get("sources", []):
        if "derived_inputs" in source:
            source.pop("derived_inputs")
            present.append("sources[].derived_inputs")
    if isinstance(clean.get("source_support"), dict) and "reason_code" in clean["source_support"]:
        clean["source_support"].pop("reason_code")
        present.append("source_support.reason_code")
    return clean, sorted(set(present))


def link(name: str, ok: bool, **evidence):
    links.append({"link": name, "ok": bool(ok), **evidence})


# 1. saved material --------------------------------------------------------------------------------------------------
registry = jload(RUN / "source_registry.json")
records = {r["claim_id"]: r for r in jload(RUN / "structured_agent_outputs.json")["records"]}
record = records[CLAIM]
source = next(s for s in registry["sources"] if s["source_id"] == record["linked_source_id"])
periods = source["data_snapshot"]["periods"]
claim_numbers = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)M", record["claim"])]
saved_millions = [round(periods[p] / 1e6) for p in sorted(periods)]
link("1_material_saved_in_this_run", source["source_type"] == "financial" and bool(source.get("excerpt")) and bool(source.get("data_snapshot")),
     source_id=source["source_id"], title=source["title"], provider=source["provider"], instrument=source["instrument"], observation_date=source["observation_date"],
     retrieved_at=source["retrieved_at"], time_basis="registry write time = upper bound of the capture time (the per-call fetch time was not saved)",
     fragment_id=source["fragment_id"], content_hash=source["content_hash"], excerpt_length=len(source["excerpt"]))
link("1b_content_hash_is_sha256_of_the_saved_excerpt", sha(source["excerpt"].encode("utf-8")) == source["content_hash"], sha256_of_excerpt=sha(source["excerpt"].encode("utf-8")))
link("1c_claim_numbers_equal_saved_data_cells", claim_numbers == saved_millions == [7685, 9246, 10270, 10253, 11536],
     claim_numbers_in_USD_millions=claim_numbers, saved_total_revenue_by_period=periods, location="source_registry.json -> sources[src_582ac24bf4319648].data_snapshot.periods (and the excerpt line 'Total Revenue')")

# 2. claim -------------------------------------------------------------------------------------------------------------
review = record["content_support_review"]
detail = record["content_support_llm_detail"]
eligibility = compute_verified_support_eligibility(record, registry["sources"])
link("2_claim_linked_to_that_material_by_the_system", record["source_link_status"] == "VALID" and record["source_link_method"] == "NORMALIZED_FIELD_MATCH_CANDIDATE" and record["linked_source_id"] == source["source_id"],
     claim=record["claim"], source_link_status=record["source_link_status"], source_link_method=record["source_link_method"], linked_source_id=record["linked_source_id"],
     note="the claim carries no Agent-written source marker (source_refs is the agent output only); the link was established by the T1 normalized-field matcher and re-validated against the registry")
link("2b_content_support_verified_and_bound_to_the_same_content_version",
     (record["content_support_status"], record["content_support_method"]) == ("SUPPORTS", "LLM_CONTENT_SUPPORT_VERIFIED")
     and review["claim_id"] == CLAIM and review["linked_source_id"] == source["source_id"] and review["content_hash"] == source["content_hash"],
     review_content_hash=review["content_hash"], source_content_hash=source["content_hash"], support_basis=detail["support_basis"], used_location=detail["used_location"],
     supporting_quote_or_data=detail["supporting_quote_or_data"], quote_is_a_substring_of_the_saved_excerpt=detail["supporting_quote_or_data"] in source["excerpt"])
link("2c_production_eligibility_function_agrees", eligibility["eligible"] is True and eligibility["reason_code"] == "ELIGIBLE", eligibility={k: eligibility[k] for k in ("eligible", "reason_code")})

# 3. Evidence Fact -----------------------------------------------------------------------------------------------------
matches = {m["claim_id"]: m for m in jload(RUN / "alpha_matches.json")["matches"]}
match = matches[CLAIM]
graph = jload(RUN / "structure_graph.json")
activations = jload(RUN / "alpha_activations.json")
a301_graph = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == "A301")
a301_file = next(a for a in activations["activation"]["alphas"] if a["alpha_id"] == "A301")
groups = [sorted(c.split(":claim:")[1] for c in g["member_claim_ids"]) for g in a301_graph["evidence_fact_groups"]]
facts = jload(RUN / "evidence_facts.json")
fact_group = next(g for g in facts["groups"] if CLAIM in g["member_claim_ids"])
link("3_evidence_fact_group_of_claim_31_under_A301", ["31", "33"] in groups and ["36"] in groups and len(groups) == 2,
     official_A301_fact_groups=groups, run_level_evidence_facts_group_members=[c.split(":claim:")[1] for c in fact_group["member_claim_ids"]],
     reading="31 and 33 state the same saved Total Revenue observations (33 uses two of 31's five), so they are ONE independent fact; each keeps its own claim, citation and wording")

# 4. Alpha ---------------------------------------------------------------------------------------------------------------
link("4_alpha_match_and_official_activation",
     match["matched_alpha"] == "A301" and match["alpha_match_method"] == "llm" and a301_graph["activation_score"] == a301_file["activation_score"] == 21.3056
     and a301_graph["status"] == "candidate" and CLAIM in a301_graph["claim_ids"],
     matched_alpha=match["matched_alpha"], alpha_match_method=match["alpha_match_method"], rule_match_score=match.get("score"),
     A301_activation_score=a301_graph["activation_score"], status=a301_graph["status"], independent_facts=a301_graph["unique_evidence_fact_count"], raw_supporting_claims=a301_graph["raw_supporting_claim_count"],
     structure_graph_equals_alpha_activations_file=a301_graph["activation_score"] == a301_file["activation_score"])

# 5. API ------------------------------------------------------------------------------------------------------------------
def get(path):
    with urllib.request.urlopen(API + path, timeout=60) as r:  # GET only
        return json.loads(r.read())


api = get(f"/api/research/{EXEC}/evidence-trace?claim_id=" + urllib.parse.quote(CLAIM, safe=""))
artifact = jload(RUN / "evidence_trace.json")
item = api["item"]
live_clean, additive_present = without_additive(item)
link("5_api_trace_equals_the_saved_export_artifact", live_clean == artifact["items"][CLAIM],
     api_status=api["status"], summary=item["summary"], statuses_are_separate=sorted(item["summary"]),
     additive_keys_in_the_live_item_not_in_the_saved_artifact=additive_present,
     reading="every pre-existing field is identical; the keys listed (added after this execution was written) are ignored by the comparison and only by it",
     api_source_content_hash_equals_registry=item["sources"][0]["content_hash"] == source["content_hash"],
     api_used_location=item["source_support"]["content_support"]["used_location"])

# 6. UI (from the browser walkthrough's own result) ---------------------------------------------------------------------
walk = jload(HERE / "browser_walkthrough_round21_result.json")
ui = walk["steps"]["structure_page_A301_evidence_trace"]["items"]["claim_31"]
shot = HERE / "browser_walkthrough_round21" / "02_A301_claim_31_basis_open.png"
link("6_ui_shows_material_location_and_verification_not_just_an_id",
     walk["execution"] == EXEC and ui["shows_only_internal_id_before_opening"] is True and not ui["missing_expected_strings"] and not ui["api_vs_ui"]["missing_on_screen"]
     and not walk["blocked_non_get_requests"] and not walk["console_errors"] and shot.exists(),
     browser=walk["browser"], page="/runs/<exec>/structure -> A301 card -> evidence -> 'View basis'",
     before_clicking="the evidence line shows the claim wording and its internal id only", strings_the_saved_data_requires_on_screen=ui["api_vs_ui"]["strings_the_saved_data_requires_on_screen"],
     missing_on_screen=ui["api_vs_ui"]["missing_on_screen"], screenshot=str(shot.relative_to(REPO)), screenshot_sha256=sha(shot.read_bytes()))

# 7. Export -------------------------------------------------------------------------------------------------------------
zip_path = HERE / "browser_walkthrough_round21" / "exported_from_browser.zip"
with zipfile.ZipFile(zip_path) as z:
    names = z.namelist()
    exported_trace = json.loads(z.read("evidence_trace.json"))
    exported_registry = json.loads(z.read("source_registry.json"))
    exported_records = {r["claim_id"]: r for r in json.loads(z.read("structured_agent_outputs.json"))["records"]}
exported_source = next(s for s in exported_registry["sources"] if s["source_id"] == source["source_id"])
link("7_formal_export_carries_the_same_chain",
     exported_trace["items"][CLAIM] == live_clean and exported_source["content_hash"] == source["content_hash"] and exported_source["excerpt"] == source["excerpt"]
     and exported_records[CLAIM]["source_link_status"] == "VALID" and exported_records[CLAIM]["content_support_status"] == "SUPPORTS",
     zip_members_with_the_chain=[n for n in names if n in ("evidence_trace.json", "source_registry.json", "structured_agent_outputs.json", "alpha_matches.json", "evidence_facts.json", "alpha_activations.json", "structure_graph.json")],
     exported_zip_sha256=sha(zip_path.read_bytes()), downloaded_by="the browser's 'Export research' button during the walkthrough")

result = {"execution": EXEC, "claim_id": CLAIM, "chain": "saved material -> claim -> Evidence Fact -> Alpha -> API -> UI -> Export",
          "all_links_pass": all(l["ok"] for l in links), "links": links,
          "scope_note": "This proves the positive sample's chain is consistent end to end. It does not declare T1 accepted and says nothing about the 975 other claims."}
(HERE / "claim31_chain_verification.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
print(json.dumps({l["link"]: l["ok"] for l in links}, indent=1), "\nall_links_pass:", result["all_links_pass"])
sys.exit(0 if result["all_links_pass"] else 2)
