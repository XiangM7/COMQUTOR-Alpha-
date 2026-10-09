# T3 offline prep, item 5(b): root-cause analysis of A304/A101/A103's original errors

Source data: `docs/audit_artifacts/v0_2_candidate3_final_predictions.json` (the frozen, already-paid-for Candidate-3 Alpha-classification predictions behind the 82.67% score) cross-referenced against each claim's own real text in its original run's `structured_agent_outputs.json` (`outputs/runs/<run_id>/`). Every quote below is real, unedited claim text from an already-persisted run; nothing here is invented or paraphrased for effect. 27 real samples touch A304/A101/A103 as gold label or prediction (16 errors, 11 correct) out of the 150-sample Final Gold set — see item 5(c) for why this is the honest total, not 40.

## A304 (Multiple Compression) — dominant failure mode: NONE → A304 false positives (8 of 16 errors)

A304's own core thesis: *"Rich valuation and high multiples create downside risk despite strong fundamentals."*

Eight real gold=NONE claims were predicted A304. Reading them side by side, they share a single, consistent pattern: **the claim's own net assertion is a rebuttal, a hedge, or a balanced verdict — never an independent bearish valuation assertion — but it uses A304-adjacent vocabulary (P/E, multiple, repricing, "above average") along the way.** Concretely:

- *"The bull's PEG argument is mathematically flawed and should be dismissed outright."* — a rebuttal of someone else's argument, not itself a valuation claim.
- *"Factor: Valuation; Bear View: 120x trailing P/E; Bull Counter: 30.4x forward P/E, PEG 1.03; Verdict: Fairly valued"* — presents both sides and explicitly concludes "fairly valued"; the model appears to have keyed on the "Bear View: 120x trailing P/E" fragment and ignored the claim's own stated verdict.
- *"You can't simultaneously argue the multiple is dangerously rich and that the forward multiple already embeds aggressive growth expectations."* — again a rebuttal/consistency challenge, not an assertion.
- *"On 'Forward EPS Assumes 95% Growth Continues' ... let me challenge that assumption"* — explicit rebuttal framing.
- *"The Trefis headline ... is not 'clickbait'; it is the central question"* — meta-commentary about whether a headline is legitimate, not a valuation assertion about the company itself.
- *"The market isn't rewarding visibility; it's setting a trap."* and *"The question is not whether TSM is a great company; it is whether the current price offers a favorable risk-reward."* — generic, rhetorical risk-framing with no concrete valuation figure or mechanism.
- *"QQQ ... is the most exposed index product to this repricing."* — an index-exposure framing, one causal step removed from a direct per-security valuation thesis.

**This is precisely the failure category the CURRENT production prompt already carries explicit guidance for** (`week2_llm.py`'s `_TASK_INSTRUCTIONS["alpha_classifier"]`, current version `v6`): *"A hypothetical, conditional-downside, rebuttal, or skepticism framing ... must be judged by what it actually asserts is true now, never treated as affirmative evidence for the thesis whose surface vocabulary it happens to use."* The historical Candidate-3 evaluation was run against `claude-sonnet-4-6` under whatever prompt version was current at the time (not independently reconstructible from the frozen hash alone) — **it is plausible, but NOT verified here, that the current `v6` prompt's rebuttal-framing guidance already mitigates most of this specific failure mode.** This is exactly the kind of claim that must be tested against the actual production model, not assumed — see the diagnostic sample in item 5(c).

Two real, genuine A304 misses (false negatives) also exist and are informative in the opposite direction — the model can also be too CONSERVATIVE when a real A304 assertion is phrased abstractly rather than tied to a specific ticker's own numbers:

- *"When rates rise, the discount rate rises, and the multiple compresses."* — a near-textbook statement of A304's own causal mechanism, missed entirely (predicted NONE).
- *"Rate environment: 89% probability of no Fed cuts in 2026, with 19-year-high yields — a headwind for high-multiple growth stocks."* — also missed; framed as a rate/probability statistic rather than an explicit valuation-risk statement.

## A101 (AI Expansion) ↔ A103 (AI Infrastructure) — a genuine, close thematic boundary

A101: *"AI training and adoption increase demand for accelerators and AI-related equities."* A103: *"AI buildout drives datacenter, power, cooling, networking, and server demand."*

Two real gold=A101 claims were predicted A103:

- *"CoreWeave's CEO says they are 'struggling to keep up with demand for Nvidia chips.' Every single one of these demand signals flows through TSM's foundry and CoWoS advanced packaging."* — this claim genuinely mentions BOTH chip demand (A101) AND foundry/advanced-packaging capacity (A103's own keyword territory). **The current production prompt's own explicit rule — "When the Evidence names concrete datacenter, power, cooling, networking, server, or advanced-packaging/foundry capacity, prefer A103 over A101 even when AI demand is the stated cause" — would have produced the SAME wrong answer the historical evaluation got here**, since this claim explicitly names foundry/CoWoS capacity. This is a genuine finding worth flagging for human review: the current rule may not universally hold, at least not against this specific gold-labeled example.
- *"When hyperscalers get squeezed by investors to justify their AI capex spending, they do not stop spending."* — no concrete foundry/infrastructure mention at all here; a less clear case of why A103 was chosen over A101.

One real gold=A101 claim was missed entirely (predicted NONE): *"The hawkish Fed and rising yields are a real headwind, but the low recession probability supports continued AI capex."* — a hedged, "but"-contrasted statement; the same class of mixed/contrastive framing this session's own work on the deterministic classifier (`structured_output_adapter.analyze_claim_semantics`) found collapses to a neutral/no-match outcome when a claim mixes a concession with its own real assertion. Whether the LLM classifier is equally sensitive to this exact pattern is untested here.

## Honest, load-bearing caveat

Every finding above is a **pattern observed in frozen historical output from a different model (`claude-sonnet-4-6`)**, not a measured property of the actual production model (`deepseek-v4-flash`) or its current `v6` prompt. This document identifies *hypotheses worth testing* — it does not, and cannot, prove the current production model makes or avoids these same errors without a real (paid, T3-scope) evaluation run, which this round does not execute. The diagnostic sample in item 5(c) is built specifically so that evaluation, whenever authorized, has ready-made, real, already-labeled test material rather than starting from zero.
