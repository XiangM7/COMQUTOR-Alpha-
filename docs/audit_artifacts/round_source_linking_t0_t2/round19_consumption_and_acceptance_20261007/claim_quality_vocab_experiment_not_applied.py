#!/usr/bin/env python3
"""Round 19 -- measures, IN-PROCESS ONLY, how many of the 7 'verified + model-selected but context_only' claims would change class if the change-term vocabulary of
comqutor_alpha.structure_engine.claim_quality also contained 'went from' / 'swung from' / 'swung'. NOT APPLIED: no file is modified; the original pattern is restored.
The 'before' classification is first checked to reproduce the stored class of all 7 claims, so the experiment uses exactly the production inputs."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from comqutor_alpha.structure_engine import claim_quality as cq

recs = {r["claim_id"]: r for r in json.loads((REPO / "outputs/runs/requal-20261007T174744Z-664040d6/structured_agent_outputs.json").read_text())["records"]}
rows = json.loads((HERE / "claims_975_list.json").read_text())["claims"]
blocked = [r["claim_id"] for r in rows if r["scoring"]["not_scored_code"] == "NON_ANALYTICAL_QUALITY"]


def classify(cid):
    r = recs[cid]
    return cq.classify_claim_quality(r["claim"], r["evidence"], entities=r.get("entities"), factors=r.get("factors"), direction=r.get("direction"), assertion_status=r.get("assertion_status")).quality_class


before = {c: classify(c) for c in blocked}
assert before == {c: recs[c]["claim_quality"] for c in blocked}, "the experiment does not reproduce the stored classes"
original = cq._STATE_CHANGE_PATTERN
cq._STATE_CHANGE_PATTERN = cq._terms_pattern(tuple(cq.STATE_OR_CHANGE_TERMS) + ("went from", "swung from", "swung"))
after = {c: classify(c) for c in blocked}
cq._STATE_CHANGE_PATTERN = original
assert classify(blocked[0]) == before[blocked[0]]
out = {"purpose": "effect size of one possible vocabulary change; NOT APPLIED; in-process only", "added_terms": ["went from", "swung from", "swung"], "before_equals_stored_for_all": True,
       "claims": [{"claim_id": c, "claim": recs[c]["claim"], "before": before[c], "with_added_terms": after[c]} for c in blocked],
       "flipped_to_analytical": [c for c in blocked if before[c] != after[c]]}
(HERE / "claim_quality_vocab_experiment_not_applied.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print("flipped:", [c.split(":", 1)[1] for c in out["flipped_to_analytical"]])
