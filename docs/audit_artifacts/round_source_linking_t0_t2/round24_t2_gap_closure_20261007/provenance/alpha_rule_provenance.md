# Provenance of the Gold contract rules the unified entry executes

Every rule below is the record in John's frozen contract (`docs/audit_artifacts/v0_2_gold_operational_contract.json`, sha256 `e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f`, equal to the
freeze manifest's), together with the John decision text it implements. The file's own `approval_status: APPROVED` is NOT cited (see N1).

| Rule | Ticker / tier | Blocking | Type | Alpha / allowed pairs | Frozen trigger (bound run) | Conflict that would pause it |
|---|---|---|---|---|---|---|
| NVDA-A101-AI-GROWTH | NVDA / FORMAL_GOLD | yes | must_detect_if_evidence_present / ALPHA_HIT | A101 | PRESENT/STRONG (run 57d7b4c4) | none |
| NVDA-A304-VALUATION-RISK | NVDA / FORMAL_GOLD | yes | must_detect_if_evidence_present / ALPHA_HIT | A304 | PRESENT/STRONG (run 57d7b4c4) | none |
| MSFT-A102-DIRECT-INFERENCE-TRIGGER | MSFT / SILVER_DIAGNOSTIC | no | must_detect_if_evidence_present / ALPHA_HIT | A102 | PRESENT/STRONG (run 43472ace) | none |
| NVDA-GROWTH-VS-VALUATION-CONFLICT | NVDA / FORMAL_GOLD | yes | conditional_only / COMPOSITE_STRUCTURE_HIT | A101, A301, A304 / A101__A304, A301__A304 | PRESENT/STRONG (run 57d7b4c4) | none |
| AMD-AI-GROWTH-VS-VALUATION | AMD / SILVER_DIAGNOSTIC | no | conditional_only / COMPOSITE_STRUCTURE_HIT | A101, A201, A301, A304 / A101__A304, A301__A304 | PRESENT/STRONG (run 949f685a) | none |

## NVDA-A101-AI-GROWTH

- Contract `evidence_condition`: Current NVDA-specific evidence (ticker-specific, qualified, Primary/Secondary-role-aware, deduplicated fact groups) materially describes AI training / AI compute / GPU accelerator demand growth relevant to NVDA's role as an AI accelerator supplier.
- Contract `required_behavior`: If the evidence condition is present, the system must detect A101 at an official detected level (active, dominant, or regime_level).
- Contract `not_triggered_behavior`: If no material NVDA-specific AI/GPU demand evidence exists in a given run, A101 is NOT_TRIGGERED -- no forced detection.
- Frozen trigger: **PRESENT / STRONG** for run `57d7b4c4-dbb9-4134-b962-ee2a873941cc` only — Multiple independent agents (sentiment_agent, news_agent) report concrete, dated, NVDA-attributed AI-demand evidence with no contrary signal found.

John's decision text that this rule implements:

**Step 2 -- John's final decisions and the freeze** — transcript line 72630, recorded 2026-09-10T21:02:57.563Z, section 4 (NVDA policy, core mappings):

```text
==================================================
4. IMPORTANT NVDA POLICY
==================================================

NVDA Gold thesis remains:

AI leader growth-vs-valuation conflict.

Core mappings:

A101:
must_detect_if_evidence_present

A301:
should_detect_if_supported + conditional_only

A304:
must_detect_if_evidence_present

Growth-vs-Valuation Composite:

allowed canonical pairs:

A101__A304
A301__A304

only when both relevant evidence sides are present.

Do not force a conflict if only one side is supported.

A103 / A201 / A601 remain supporting/non-mandatory.
```

**Step 2 -- John's final decisions and the freeze** — transcript line 72630, recorded 2026-09-10T21:02:57.563Z, section 2 (blocking):

```text
==================================================
2. PRESERVE ALL OTHER DRAFT RULES
==================================================

Do not otherwise broaden or narrow the Step-1 contract.

Formal Gold remains:

NVDA
QQQ
SNDK

blocking = true

Silver remains:

MSFT
TSM
AMD

blocking = false

Hit types remain:

ALPHA_HIT
COMPOSITE_STRUCTURE_HIT
NEGATIVE_CONTROL_HIT
CONDITIONAL_ACCEPTANCE_HIT

No new production Alpha IDs.
```

**Step 1 -- operationalize John's Gold labels v0.2** — transcript line 72541, recorded 2026-09-10T20:43:46.251Z, section 8.A (AI growth):

```text
A. AI growth

Preferred existing Alpha mapping:

A101 — AI Expansion

Rule type:

must_detect_if_evidence_present

Condition conceptually:

current NVDA-specific evidence materially supports AI training /
AI compute / GPU demand expansion.

Do NOT force A101 when such evidence is absent.

--------------------------------------------------
```


## NVDA-A304-VALUATION-RISK

- Contract `evidence_condition`: Current NVDA-specific evidence materially supports valuation compression, rich valuation, or multiple downside risk.
- Contract `required_behavior`: If the evidence condition is present, the system must detect A304 at an official detected level.
- Contract `not_triggered_behavior`: If no material valuation-risk evidence exists, A304 is NOT_TRIGGERED.
- Frozen trigger: **PRESENT / STRONG** for run `57d7b4c4-dbb9-4134-b962-ee2a873941cc` only — Direct NVDA-attributed valuation-concentration framing plus closely analogous peer precedent explicitly linked to NVDA's own risk profile.

John's decision text that this rule implements:

**Step 2 -- John's final decisions and the freeze** — transcript line 72630, recorded 2026-09-10T21:02:57.563Z, section 4 (NVDA policy, core mappings):

```text
==================================================
4. IMPORTANT NVDA POLICY
==================================================

NVDA Gold thesis remains:

AI leader growth-vs-valuation conflict.

Core mappings:

A101:
must_detect_if_evidence_present

A301:
should_detect_if_supported + conditional_only

A304:
must_detect_if_evidence_present

Growth-vs-Valuation Composite:

allowed canonical pairs:

A101__A304
A301__A304

only when both relevant evidence sides are present.

Do not force a conflict if only one side is supported.

A103 / A201 / A601 remain supporting/non-mandatory.
```

**Step 1 -- operationalize John's Gold labels v0.2** — transcript line 72541, recorded 2026-09-10T20:43:46.251Z, section 8.C (valuation downside):

```text
C. Valuation downside

Existing mapping:

A304 — Multiple Compression

Rule type:

must_detect_if_evidence_present

Condition:

current evidence materially supports valuation compression /
rich valuation / multiple downside risk.

--------------------------------------------------
```


## MSFT-A102-DIRECT-INFERENCE-TRIGGER

- Contract `evidence_condition`: Current MSFT-specific evidence explicitly describes: inference workloads, inference compute demand, serving AI applications/models, agent/application inference, or inference-side compute consumption.
- Contract `required_behavior`: If the evidence condition is present, the system must detect A102 at an official detected level (active/dominant/regime_level).
- Contract `not_triggered_behavior`: If evidence does not explicitly engage the inference mechanism, this rule is NOT_TRIGGERED -- see MSFT-A102-INDIRECT-INFERENCE-SUPPORT instead.
- Frozen trigger: **PRESENT / STRONG** for run `43472ace-454f-4c69-892c-adca91c25be7` only — Multiple claims (fundamental_agent Primary source, bull_researcher, bear_researcher) explicitly name 'inference demand' as the mechanism, directly tied to named MSFT products (Copilot, Azure AI services) -- satisfies the DIRECT trigger's explicit-mechanism requirement.

John's decision text that this rule implements:

**Step 2 -- John's final decisions and the freeze** — transcript line 72630, recorded 2026-09-10T21:02:57.563Z, section 1.G (final decision):

```text
G. MSFT A102

FINAL:

split evidence strength behavior.

DIRECT_INFERENCE_TRIGGER:

If current MSFT-specific evidence explicitly describes:

- inference workloads
- inference compute demand
- serving AI applications/models
- agent/application inference
- inference-side compute consumption

then:

must_detect_if_evidence_present
→ A102

INDIRECT_INFERENCE_SUPPORT:

If evidence only describes broader:

- enterprise AI adoption
- Copilot usage
- AI application adoption
- generic AI demand

without clearly engaging the inference mechanism:

should_detect_if_supported

Do not force A102 from generic AI adoption alone.

MSFT remains SILVER / NON-BLOCKING.

--------------------------------------------------
```

**Step 2 -- John's final decisions and the freeze** — transcript line 72630, recorded 2026-09-10T21:02:57.563Z, section 2 (blocking):

```text
==================================================
2. PRESERVE ALL OTHER DRAFT RULES
==================================================

Do not otherwise broaden or narrow the Step-1 contract.

Formal Gold remains:

NVDA
QQQ
SNDK

blocking = true

Silver remains:

MSFT
TSM
AMD

blocking = false

Hit types remain:

ALPHA_HIT
COMPOSITE_STRUCTURE_HIT
NEGATIVE_CONTROL_HIT
CONDITIONAL_ACCEPTANCE_HIT

No new production Alpha IDs.
```

**Step 1 -- operationalize John's Gold labels v0.2** — transcript line 72541, recorded 2026-09-10T20:43:46.251Z, section 11.B (the 'must/should' wording that decision G resolved):

```text
B. Inference

Existing mapping:

A102 — Inference Explosion

Rule:

must/should_detect_if_evidence_present

Condition:

current MSFT-specific evidence supports inference-side compute demand
from AI applications/agents.

--------------------------------------------------
```


## NVDA-GROWTH-VS-VALUATION-CONFLICT

- Contract `evidence_condition`: Both a supported growth side (A101 and/or A301 reaching a qualified/detected level) and a supported valuation-risk side (A304 reaching a qualified/detected level) are present in the same run.
- Contract `required_behavior`: When both sides coexist, an admissible growth-vs-valuation conflict (one of the allowed pairs) should be surfaced via the existing, unmodified conflict admissibility (B2) authority -- this rule does not itself define or alter B2's admission logic.
- Contract `not_triggered_behavior`: If only one side is present (growth without valuation-risk evidence, or vice versa), the system must NOT force a conflict.
- Frozen trigger: **PRESENT / STRONG** for run `57d7b4c4-dbb9-4134-b962-ee2a873941cc` only — Growth side triggered by BOTH AI growth (A101) and fundamental growth (A301) independently; valuation-risk side (A304) also independently present. This evidence-side finding does NOT inspect or assert anything about the actual admitted conflict -- that is Step 4.

John's decision text that this rule implements:

**Step 2 -- John's final decisions and the freeze** — transcript line 72630, recorded 2026-09-10T21:02:57.563Z, section 4 (composite):

```text
==================================================
4. IMPORTANT NVDA POLICY
==================================================

NVDA Gold thesis remains:

AI leader growth-vs-valuation conflict.

Core mappings:

A101:
must_detect_if_evidence_present

A301:
should_detect_if_supported + conditional_only

A304:
must_detect_if_evidence_present

Growth-vs-Valuation Composite:

allowed canonical pairs:

A101__A304
A301__A304

only when both relevant evidence sides are present.

Do not force a conflict if only one side is supported.

A103 / A201 / A601 remain supporting/non-mandatory.
```

**Step 4 -- compare frozen Gold + frozen triggers against the six runs** — transcript line 72837, recorded 2026-09-10T21:52:47.071Z, section 13 (composite evaluation):

```text
==================================================
13. COMPOSITE STRUCTURE RULE
==================================================

If frozen composite trigger = ABSENT:

→ NOT_TRIGGERED

If frozen composite trigger = UNCERTAIN:

→ REVIEW

If frozen composite trigger = PRESENT:

inspect:

- relevant actual Alpha states
- persisted conflict candidates
- admitted main conflict
- canonical allowed conflict family

If an allowed evidence-supported conflict is actually admitted:

→ PASS

If actual admitted conflict is clearly outside the frozen allowed family:

→ FAIL or REVIEW if admissibility/root-cause analysis is required.

If no conflict is admitted even though composite trigger = PRESENT:

DO NOT immediately call it a system error.

Record:

REVIEW

requires_step5_adjudication = true

unless the existing persisted artifact already proves a deterministic
violation of the frozen contract.

Step 5 will specifically adjudicate conflict/gating mismatches.
```

**Step 4 -- compare frozen Gold + frozen triggers against the six runs** — transcript line 72837, recorded 2026-09-10T21:52:47.071Z, section 15 (NVDA frozen trigger states):

```text
==================================================
15. NVDA — FORMAL GOLD
==================================================

Use frozen trigger states:

A101 AI-growth:
PRESENT / STRONG

A301 fundamental-growth:
PRESENT / STRONG

A304 valuation-risk:
PRESENT / STRONG

A103:
PRESENT / MODERATE

A201:
UNCERTAIN

A601:
PRESENT / STRONG

Growth-vs-Valuation composite:
PRESENT

Do NOT reinterpret these states.

Now compare actual system outputs.

Core acceptance questions:

- Was A101 properly detected?
- Was A301 appropriately detected?
- Was A304 properly detected?
- Did the system surface an allowed Growth-vs-Valuation conflict?
- Did any frozen forbidden-dominance rule fail?

A103/A201/A601 remain subject to their frozen non-mandatory semantics.

Do not turn NVDA A201 UNCERTAIN into a release failure unless the frozen rule
explicitly makes it blocking.
```


## AMD-AI-GROWTH-VS-VALUATION

- Contract `evidence_condition`: Current AMD-specific evidence supports AI/semiconductor growth (A101 and/or A301, optionally A201) AND valuation-risk evidence (A304) coexisting in the same run.
- Contract `required_behavior`: When both a supported growth side and a supported valuation-risk side coexist, an admissible conflict (one of the allowed pairs) should be surfaced via the existing, unmodified conflict admissibility (B2) authority. Do not force either pair.
- Contract `not_triggered_behavior`: If only one side is present, the system must NOT force a conflict.
- Frozen trigger: **PRESENT / STRONG** for run `949f685a-3945-4fd0-b7b9-362b37c90721` only — Both composite legs independently present with concrete, TSM-... err AMD-specific quantified evidence (50% revenue growth; 122x trailing earnings). A201 (industry-wide semiconductor cycle) evidence is thinner/mixed (AMD noted as a 'relative laggard' vs NVDA in some claims) but is only an optional element of this rule's acceptable_alphas -- the primary growth trigger (A101+A301) is independently sufficient.

John's decision text that this rule implements:

**Step 1 -- operationalize John's Gold labels v0.2** — transcript line 72541, recorded 2026-09-10T20:43:46.251Z, section 13 (AMD composite):

```text
==================================================
13. AMD — SILVER / NON-BLOCKING
==================================================

John thesis:

AI semiconductor competitor / valuation conflict

Use existing Alpha concepts:

A101 — AI Expansion
A201 — Semiconductor Supercycle
A301 — Revenue Expansion when supported
A304 — Multiple Compression

Rules remain evidence-conditional.

Create a composite:

AMD_AI_GROWTH_VS_VALUATION

Hit type:

COMPOSITE_STRUCTURE_HIT

If current AI/semiconductor growth evidence and valuation-risk evidence
coexist, acceptable canonical conflict should be derived from taxonomy.

Likely:

A101__A304
A301__A304

only if canonical taxonomy confirms.

Do not force either pair.

Silver / non-blocking.
```

**Step 4 -- compare frozen Gold + frozen triggers against the six runs** — transcript line 72837, recorded 2026-09-10T21:52:47.071Z, section 13 (composite evaluation):

```text
==================================================
13. COMPOSITE STRUCTURE RULE
==================================================

If frozen composite trigger = ABSENT:

→ NOT_TRIGGERED

If frozen composite trigger = UNCERTAIN:

→ REVIEW

If frozen composite trigger = PRESENT:

inspect:

- relevant actual Alpha states
- persisted conflict candidates
- admitted main conflict
- canonical allowed conflict family

If an allowed evidence-supported conflict is actually admitted:

→ PASS

If actual admitted conflict is clearly outside the frozen allowed family:

→ FAIL or REVIEW if admissibility/root-cause analysis is required.

If no conflict is admitted even though composite trigger = PRESENT:

DO NOT immediately call it a system error.

Record:

REVIEW

requires_step5_adjudication = true

unless the existing persisted artifact already proves a deterministic
violation of the frozen contract.

Step 5 will specifically adjudicate conflict/gating mismatches.
```

**Step 4 -- compare frozen Gold + frozen triggers against the six runs** — transcript line 72837, recorded 2026-09-10T21:52:47.071Z, section 20 (AMD):

```text
==================================================
20. AMD — SILVER
==================================================

Frozen:

growth:
PRESENT / STRONG

valuation:
PRESENT / STRONG

AI-growth-vs-valuation composite:
PRESENT

Inspect actual system outputs and allowed canonical conflicts.

Non-blocking.
```

## Integrity notes (observations; none pauses an executed rule)

**N1 — the 'APPROVED' flag inside the contract file.** contract.authority.approval_status = APPROVED with approval_authority = John is the literal block the Step-1 instruction (section 20) asked the file to contain; it is a template field, not evidence of approval. *Handling:* not cited. Each executed rule cites the John decision it implements (john_decision_text).

**N2 — contract JSON integrity.** sha256 e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f equals frozen_contract_json_sha256 in the freeze manifest (e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f). *Handling:* verified at load time on every run of the entry; a different sha256 is a configuration error.

**N3 — contract markdown companion.** sha256 now efc7a82b33e6f4c5aea5fa9c14d6c62ce97245534ff2b17b568074762d989eca; the freeze manifest recorded 8e184d7ed41cbe253b5aa7e97e150e9c7f4dbfd6852d411e9874dbe299bf9f04. The file was rewritten on John's instruction of 2026-09-15 (final submission cleanup, section 3: a short John-facing definition of the six semantics), which is why it is 1.9 KB and no longer byte-identical. Its six semantics sentences agree with contract.rule_type_semantics. The rule records live in the JSON only. *Handling:* reported in effective_rules (markdown_companion), not read by the executor, not a conflict with any executed rule. The owner may want the freeze manifest to record the post-cleanup hash.

**N4 — trigger matrix integrity and binding.** sha256 3e8e7402803632198b01c2a08a98929031929cc4b909927dc7e475d37b5d22a1 equals the frozen hash recorded in v0_2_final_acceptance_closure.json (authorities_verified.historical_trigger_matrix_json); it was written against the contract sha256 e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f. Its triggers were determined by reading structured_agent_outputs.json of ONE run per ticker: {'NVDA': '57d7b4c4-dbb9-4134-b962-ee2a873941cc', 'QQQ': 'f88c8956-cb62-48aa-9951-89f8e8a95f83', 'MSFT': '43472ace-454f-4c69-892c-adca91c25be7', 'SNDK': 'e8e0f398-7b26-4462-8135-a1410ea5b335', 'TSM': 'dfc7ceb3-3584-4514-bd84-6c371aab3e95', 'AMD': '949f685a-3945-4fd0-b7b9-362b37c90721'}. It records the run id and the input artifact name but no hash of that input, so the binding is by run id. *Handling:* the trigger is used only when the evaluated run id equals the bound run id; every other run is NOT_EVALUABLE. No approved executable method determines the trigger for another run.

**N5 — AMD allowed pairs.** the contract's AMD composite lists A101__A304 and A301__A304; John's later written baseline (authority hierarchy level 1, which supersedes the contract for acceptance purposes) lists A101__A304, A201__A304 and A301__A304 for AMD. *Handling:* the allowed family is the baseline-controlled set the label already carries, plus the contract's own pairs. No executed rule's verdict on the six pinned runs depends on it (AMD's pinned run is not bound).

**N6 — NVDA composite: contract wording versus matrix method.** the contract's evidence_condition for the NVDA composite is written in terms of the component Alphas reaching a qualified / detected level; the matrix (and John's Step-4 protocol: 'do not use actual Alpha output to change a trigger') fixes the trigger from evidence, independent of the system's output. *Handling:* the executor uses only the matrix trigger, for the bound run. Whether a level-based trigger is approved for other runs is an OWNER DECISION; none is assumed.

**N7 — QQQ run identity.** the matrix binds QQQ to f88c8956; John's final submission table (2026-09-15) uses the later QQQ run f239a53f. No executed rule belongs to QQQ. *Handling:* no effect now; recorded for the day a QQQ rule is executed.

**N8 — label v0.2 structural_expectations versus the Gold must_detect rules.** the provisional label file says a missing structural Alpha never fails a run; the Gold contract's must_detect rules say a missed Alpha with the evidence present is a FAIL. *Handling:* not a conflict that pauses a rule: the baseline's authority hierarchy ranks John's Gold contract above the repository label files ('implementation sources only'). The two do not collide in the executor (structural_expectations are never executed).

