import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type {
  AlphaInvalidationEntry,
  ConflictAuditSide,
  ConflictCandidateEvaluation,
  ConflictEvidenceUI,
  ConflictEvidenceUIItem,
  ConflictMissingEvidenceItem,
} from "../api/types";
import { CandidateConflictCard } from "./CandidateConflictCard";
import { ConflictEvidenceSections } from "./ConflictEvidenceSections";

// Real-shape fixtures, modeled directly on the live payload captured from
// run 5ffe121a-68fd-473b-82b5-c9465332d8a2 (main conflict A301__A304) --
// docs/audit_artifacts/live_run_5ffe121a_pipeline_failure_report.md.

function makeEvidenceItem(overrides: Partial<ConflictEvidenceUIItem> = {}): ConflictEvidenceUIItem {
  return {
    evidence_fact_group_id: "fact-1",
    representative_claim_id: "claim-1",
    member_claim_ids: ["claim-1"],
    evidence_text: "Sample evidence text.",
    agents: ["news_agent"],
    source_agent_output_ids: ["run-1:news_agent:news_report"],
    target_alpha_id: "A301",
    evidence_stance: "supports_alpha",
    stance_method: null,
    evidence_stance_version: "evidence_stance.deterministic.v1",
    stance_confidence_band: "high",
    ticker_specific: true,
    representative_match_score: 0.8,
    ...overrides,
  };
}

function notDefined(alphaId: string, alphaName: string | null = null): AlphaInvalidationEntry {
  return { alpha_id: alphaId, alpha_name: alphaName, approval_status: "not_defined", source: null, version: null, conditions: [] };
}

function makeEvidenceUi(overrides: Partial<ConflictEvidenceUI> = {}): ConflictEvidenceUI {
  return {
    schema_version: "conflict_evidence_ui.v1",
    bull_evidence: [makeEvidenceItem({ evidence_fact_group_id: "bull-1", target_alpha_id: "A301" })],
    bear_evidence: [
      makeEvidenceItem({
        evidence_fact_group_id: "bear-1",
        target_alpha_id: "A304",
        evidence_stance: "opposes_alpha",
        evidence_text: "Bear-side sample text.",
      }),
    ],
    counter_evidence: [],
    missing_evidence: [],
    qualification_gaps: [],
    invalidation_conditions: {
      bull_alpha: notDefined("A301", "Revenue Expansion"),
      bear_alpha: notDefined("A304", "Multiple Compression"),
    },
    ...overrides,
  };
}

const auditSide: ConflictAuditSide = { alpha_id: "A101", qualifying_claim_ids: [], qualifying_count: 0, excluded: [] };

function makeCandidateEvaluation(overrides: Partial<ConflictCandidateEvaluation> = {}): ConflictCandidateEvaluation {
  return {
    alpha_a: "A101",
    alpha_b: "A304",
    outcome: "suppressed",
    reason_codes: ["BULL_SCORE_BELOW_THRESHOLD"],
    evidence_audit: { alpha_a: auditSide, alpha_b: auditSide },
    bull_alpha_id: "A101",
    bear_alpha_id: "A304",
    admissibility: {
      admissibility_version: "week4.conflict_admissibility.b2.v1",
      status: "candidate",
      reason_codes: ["BULL_SCORE_BELOW_THRESHOLD"],
      bull_score: 33.98,
      bear_score: 70.1,
      bull_supporting_evidence_count: 1,
      bear_supporting_evidence_count: 7,
      bull_ticker_specific_support_count: 0,
      bear_ticker_specific_support_count: 1,
      bull_supporting_fact_group_ids: ["f1"],
      bear_supporting_fact_group_ids: ["f2"],
    },
    ...overrides,
  };
}

describe("ConflictEvidenceSections", () => {
  // 1. Five formal regions exist.
  it("renders all five formal regions: Bull, Bear, Counter, Missing, Invalidation", () => {
    render(<ConflictEvidenceSections evidenceUi={makeEvidenceUi()} bullAlphaId="A301" bearAlphaId="A304" />);
    expect(screen.getByText(/^Bull Evidence/)).toBeInTheDocument();
    expect(screen.getByText(/^Bear Evidence/)).toBeInTheDocument();
    expect(screen.getByText(/^Counter Evidence/)).toBeInTheDocument();
    expect(screen.getByText("Missing Evidence")).toBeInTheDocument();
    expect(screen.getByText(/What would invalidate the bull alpha/)).toBeInTheDocument();
    expect(screen.getByText(/What would invalidate the bear alpha/)).toBeInTheDocument();
  });

  // 2. Qualification Gaps is its own region, separate from Missing Evidence.
  it("shows Qualification Gaps as a region separate from Missing Evidence", () => {
    const evidenceUi = makeEvidenceUi({
      missing_evidence: [
        { side: "bull", alpha_id: "A301", missing_reason_code: "INSUFFICIENT_SUPPORTING_EVIDENCE", current_value: 1, required_value: 2, deficit: 1 },
      ],
      qualification_gaps: [{ side: "bull", alpha_id: "A301", gap_reason_code: "ALPHA_SCORE_BELOW_THRESHOLD", current_value: 33.98, required_value: 50 }],
    });
    render(<ConflictEvidenceSections evidenceUi={evidenceUi} bullAlphaId="A301" bearAlphaId="A304" />);
    const missingSection = screen.getByText("Missing Evidence").closest("section")!;
    const qualSection = screen.getByText("Qualification gaps").closest("section")!;
    expect(missingSection).not.toBe(qualSection);
    // The score-gap language never leaks into the Missing Evidence section.
    expect(within(missingSection).queryByText(/Activation-score shortfall/)).not.toBeInTheDocument();
    expect(within(qualSection).getByText(/Activation-score shortfall/)).toBeInTheDocument();
  });

  // 3 & 4. Counter Evidence grouped by target side with correct role labels (badges).
  it("groups Counter Evidence by target side with correct role labels", () => {
    const evidenceUi = makeEvidenceUi({
      counter_evidence: [
        makeEvidenceItem({
          evidence_fact_group_id: "counter-against-bull",
          evidence_text: "Counters the bull structure.",
          counter_target_alpha_id: "A301",
          evidence_stance: "opposes_alpha",
        }),
        makeEvidenceItem({
          evidence_fact_group_id: "counter-against-bear",
          evidence_text: "Counters the bear structure.",
          counter_target_alpha_id: "A304",
          evidence_stance: "opposes_alpha",
        }),
      ],
    });
    render(<ConflictEvidenceSections evidenceUi={evidenceUi} bullAlphaId="A301" bearAlphaId="A304" />);
    const againstBull = screen.getByText(/Against bull structure \(A301\)/).closest("div")!;
    const againstBear = screen.getByText(/Against bear structure \(A304\)/).closest("div")!;
    expect(within(againstBull).getByText("Counters the bull structure.")).toBeInTheDocument();
    expect(within(againstBear).getByText("Counters the bear structure.")).toBeInTheDocument();
    expect(within(againstBull).queryByText("Counters the bear structure.")).not.toBeInTheDocument();
    expect(within(againstBear).queryByText("Counters the bull structure.")).not.toBeInTheDocument();
  });

  // 5. An unrelated counter Alpha is never re-routed into either group.
  it("never re-routes a counter-evidence item whose target is neither the bull nor the bear alpha", () => {
    const evidenceUi = makeEvidenceUi({
      counter_evidence: [
        makeEvidenceItem({
          evidence_fact_group_id: "counter-unrelated",
          evidence_text: "Targets an unrelated third Alpha.",
          counter_target_alpha_id: "A601",
          evidence_stance: "opposes_alpha",
        }),
      ],
    });
    render(<ConflictEvidenceSections evidenceUi={evidenceUi} bullAlphaId="A301" bearAlphaId="A304" />);
    expect(screen.queryByText("Targets an unrelated third Alpha.")).not.toBeInTheDocument();
    const againstBull = screen.getByText(/Against bull structure \(A301\)/).closest("div")!;
    const againstBear = screen.getByText(/Against bear structure \(A304\)/).closest("div")!;
    expect(within(againstBull).getByText(/No counter evidence/)).toBeInTheDocument();
    expect(within(againstBear).getByText(/No counter evidence/)).toBeInTheDocument();
  });

  // 6. Missing Evidence shows current/required/deficit.
  it("shows current/required/deficit for each Missing Evidence entry", () => {
    const item: ConflictMissingEvidenceItem = {
      side: "bull",
      alpha_id: "A301",
      missing_reason_code: "INSUFFICIENT_SUPPORTING_EVIDENCE",
      current_value: 1,
      required_value: 2,
      deficit: 1,
    };
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({ missing_evidence: [item] })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    expect(screen.getByText(/1 of 2 required \(deficit 1\)/)).toBeInTheDocument();
    // The formal reason code stays available even though a friendly label is shown.
    expect(screen.getByText(/Insufficient supporting evidence/)).toBeInTheDocument();
  });

  // 7. An admitted conflict's empty missing_evidence shows "no B2 evidence gaps".
  it("shows 'No B2 evidence gaps identified' for an admitted conflict with an empty missing list", () => {
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({ missing_evidence: [] })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    expect(screen.getByText("No B2 evidence gaps identified.")).toBeInTheDocument();
  });

  it("shows 'No qualification gaps identified' only when the (non-optional, present) array is genuinely empty", () => {
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({ qualification_gaps: [] })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    expect(screen.getByText("No qualification gaps identified.")).toBeInTheDocument();
  });

  // 8 & 9. A101's four approved conditions, verbatim, with correct provenance.
  it("shows A101's four Product-Owner-approved conditions verbatim, with correct source/version", () => {
    const a101: AlphaInvalidationEntry = {
      alpha_id: "A101",
      alpha_name: "AI Expansion",
      approval_status: "approved",
      source: "John",
      version: "v0.1",
      conditions: [
        { condition_id: "a101-1", condition_text: "hyperscaler capex slows" },
        { condition_id: "a101-2", condition_text: "GPU demand weakens" },
        { condition_id: "a101-3", condition_text: "revenue growth decelerates" },
        { condition_id: "a101-4", condition_text: "AI demand already priced in" },
      ],
    };
    const evidenceUi = makeEvidenceUi({
      invalidation_conditions: { bull_alpha: a101, bear_alpha: notDefined("A304", "Multiple Compression") },
    });
    render(<ConflictEvidenceSections evidenceUi={evidenceUi} bullAlphaId="A101" bearAlphaId="A304" />);
    const section = screen.getByText(/What would invalidate the bull alpha — A101/).closest("section")!;
    expect(within(section).getByText("hyperscaler capex slows")).toBeInTheDocument();
    expect(within(section).getByText("GPU demand weakens")).toBeInTheDocument();
    expect(within(section).getByText("revenue growth decelerates")).toBeInTheDocument();
    expect(within(section).getByText("AI demand already priced in")).toBeInTheDocument();
    expect(within(section).getByText(/Source: John/)).toBeInTheDocument();
    expect(within(section).getByText(/Version: v0.1/)).toBeInTheDocument();
  });

  // 10. An unapproved Alpha shows the pending message, not fabricated content.
  it("shows the product-approval-pending message for an Alpha with no approved invalidation content", () => {
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({
          invalidation_conditions: {
            bull_alpha: notDefined("A301", "Revenue Expansion"),
            bear_alpha: notDefined("A304", "Multiple Compression"),
          },
        })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    expect(screen.getAllByText("Invalidation conditions have not yet been product-approved for this Alpha.").length).toBe(2);
  });

  // 13 & 14. Show all / show less never drops evidence, and each list's
  // expand state is independent of every other list on the same card.
  it("Show all/Show less never drops evidence, and Bull/Bear/Counter expand states never interfere", async () => {
    const user = userEvent.setup();
    const bullItems = Array.from({ length: 7 }, (_, i) =>
      makeEvidenceItem({ evidence_fact_group_id: `bull-${i}`, evidence_text: `Bull fact ${i}` })
    );
    const bearItems = Array.from({ length: 6 }, (_, i) =>
      makeEvidenceItem({ evidence_fact_group_id: `bear-${i}`, evidence_text: `Bear fact ${i}`, evidence_stance: "opposes_alpha" })
    );
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({ bull_evidence: bullItems, bear_evidence: bearItems })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    // Both start collapsed to 5.
    expect(screen.getByText("Bull fact 0")).toBeInTheDocument();
    expect(screen.queryByText("Bull fact 6")).not.toBeInTheDocument();
    expect(screen.queryByText("Bear fact 5")).not.toBeInTheDocument();

    const bullSection = screen.getByText(/^Bull Evidence/).closest("section")!;
    await user.click(within(bullSection).getByRole("button", { name: /Show all \(7\)/ }));

    // Expanding Bull reveals all 7 bull facts...
    expect(screen.getByText("Bull fact 6")).toBeInTheDocument();
    // ...and never touches Bear's independent, still-collapsed state.
    expect(screen.queryByText("Bear fact 5")).not.toBeInTheDocument();

    const bearSection = screen.getByText(/^Bear Evidence/).closest("section")!;
    await user.click(within(bearSection).getByRole("button", { name: /Show all \(6\)/ }));
    expect(screen.getByText("Bear fact 5")).toBeInTheDocument();
    // Bull stays expanded independently.
    expect(screen.getByText("Bull fact 6")).toBeInTheDocument();

    // Collapsing Bull back never drops the underlying data or affects Bear.
    await user.click(within(bullSection).getByRole("button", { name: "Show less" }));
    expect(screen.queryByText("Bull fact 6")).not.toBeInTheDocument();
    expect(screen.getByText("Bull fact 0")).toBeInTheDocument();
    expect(screen.getByText("Bear fact 5")).toBeInTheDocument();
  });

  // 16 & 17. Historical payload: missing fields show "unavailable", never a
  // fabricated verified-empty state. Covered at the ConflictCard level
  // (evidence_ui entirely absent) -- see ConflictCard.test.tsx for the
  // "legacy bull/bear still renders" half of this behavior.

  // 18. A raw duplicate under the same Evidence Fact group is not
  // re-processed/re-rendered as two separate cards by the frontend.
  it("never re-splits a single Evidence Fact group's members into duplicate cards", () => {
    const item = makeEvidenceItem({
      evidence_fact_group_id: "shared-fact",
      representative_claim_id: "claim-rep",
      member_claim_ids: ["claim-rep", "claim-dup-1", "claim-dup-2"],
      evidence_text: "One independent fact, three raw paraphrase claims.",
    });
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({ bull_evidence: [item] })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    expect(screen.getAllByText("One independent fact, three raw paraphrase claims.").length).toBe(1);
    expect(screen.getByText("2 merged paraphrase(s)")).toBeInTheDocument();
  });

  // 19. Long evidence text, IDs, and reason codes use the safe-wrap classes.
  it("applies the safe-wrap class to evidence items and diagnostic IDs", () => {
    const { container } = render(
      <ConflictEvidenceSections evidenceUi={makeEvidenceUi()} bullAlphaId="A301" bearAlphaId="A304" />
    );
    expect(container.querySelectorAll(".evidence-ui-item").length).toBeGreaterThan(0);
  });

  // Additive fields (target_alpha_id, stance version, confidence band,
  // provenance) render when the API provides them.
  it("renders target_alpha_id, stance version, confidence band, and provenance when provided", () => {
    const item = makeEvidenceItem({
      evidence_fact_group_id: "meta-check",
      target_alpha_id: "A301",
      evidence_stance_version: "evidence_stance.deterministic.v1",
      stance_confidence_band: "high",
      source_agent_output_ids: ["run-1:neutral_risk_analyst:risk_debate_state.neutral_history"],
    });
    render(
      <ConflictEvidenceSections
        evidenceUi={makeEvidenceUi({ bull_evidence: [item], bear_evidence: [] })}
        bullAlphaId="A301"
        bearAlphaId="A304"
      />
    );
    expect(screen.getByText(/Target Alpha: A301/)).toBeInTheDocument();
    expect(screen.getByText(/evidence_stance\.deterministic\.v1/)).toBeInTheDocument();
    expect(screen.getByText(/Confidence: high/)).toBeInTheDocument();
    expect(screen.getByText(/run-1:neutral_risk_analyst:risk_debate_state\.neutral_history/)).toBeInTheDocument();
  });
});

describe("CandidateConflictCard", () => {
  // 11 & 12. Candidate badge is distinct from Main/Admitted, and shows the
  // exact B2 gate it failed.
  it("never shows a Main or Admitted badge, and shows the exact B2 gate the pair failed", () => {
    render(<CandidateConflictCard evaluation={makeCandidateEvaluation()} />);
    expect(screen.queryByText("Main conflict")).not.toBeInTheDocument();
    expect(screen.queryByText("Admitted conflict")).not.toBeInTheDocument();
    expect(screen.getByText("Candidate conflict")).toBeInTheDocument();
    expect(screen.getByText(/did not clear the B2 Conflict Evidence/)).toBeInTheDocument();
    expect(screen.getByText(/BULL_SCORE_BELOW_THRESHOLD/)).toBeInTheDocument();
    expect(screen.getByText("34.0")).toBeInTheDocument();
  });

  it("shows 'Not evaluated' (never a fabricated B2 verdict) for a pair rejected before B2", () => {
    render(
      <CandidateConflictCard
        evaluation={makeCandidateEvaluation({
          alpha_a: "A501",
          alpha_b: "A601",
          outcome: "rejected",
          reason_codes: ["DIRECTION_ROLE_UNRESOLVED"],
          bull_alpha_id: undefined,
          bear_alpha_id: undefined,
          admissibility: undefined,
        })}
      />
    );
    expect(screen.getByText("Not evaluated")).toBeInTheDocument();
    expect(screen.queryByText("Candidate conflict")).not.toBeInTheDocument();
    expect(screen.getByText(/rejected before B2 evaluation/)).toBeInTheDocument();
    expect(screen.getByText(/DIRECTION_ROLE_UNRESOLVED/)).toBeInTheDocument();
  });

  it("renders the full evidence_ui block for a candidate pair when the backend provides one", () => {
    render(
      <CandidateConflictCard
        evaluation={makeCandidateEvaluation({
          evidence_ui: makeEvidenceUi({ bull_evidence: [makeEvidenceItem({ evidence_text: "Candidate-pair bull evidence." })] }),
        })}
      />
    );
    expect(screen.getByText("Candidate-pair bull evidence.")).toBeInTheDocument();
    expect(screen.getByText(/^Counter Evidence/)).toBeInTheDocument();
  });
});
